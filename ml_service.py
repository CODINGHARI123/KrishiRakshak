"""
Inference + continual learning for the crop disease classifier.

The model is MobileNetV2 (frozen backbone) + a small dense head.  Keeping the two
apart means a new head can be trained from expert-confirmed field images in
seconds (retrain) without touching the backbone.
"""
import json
import os
import threading
import time

import numpy as np
from PIL import Image, ImageOps

BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE, "ml", "model")
FEEDBACK_DIR = os.path.join(BASE, "ml", "feedback")
FEATURES = os.path.join(BASE, "ml", "features.npz")
IMG_SIZE = 224

os.makedirs(FEEDBACK_DIR, exist_ok=True)

_lock = threading.Lock()
_state = {"backbone": None, "head": None, "labels": None, "version": None}
retrain_status = {"running": False, "message": "", "last": None}


def available():
    return os.path.exists(os.path.join(MODEL_DIR, "krishi_model.keras"))


def _tf():
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf
    return tf


def active_version():
    p = os.path.join(MODEL_DIR, "active.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)["version"]
    return 1


def load(force=False):
    with _lock:
        if _state["backbone"] is not None and not force:
            return _state
        tf = _tf()
        if _state["backbone"] is None:
            full = tf.keras.models.load_model(os.path.join(MODEL_DIR, "krishi_model.keras"), compile=False)
            _state["backbone"] = next(l for l in full.layers if "mobilenet" in l.name.lower())
        v = active_version()
        _state["head"] = tf.keras.models.load_model(os.path.join(MODEL_DIR, f"head_v{v}.keras"), compile=False)
        _state["version"] = v
        with open(os.path.join(MODEL_DIR, "labels.json")) as f:
            _state["labels"] = json.load(f)
        return _state


def _prep(img):
    img = ImageOps.exif_transpose(img).convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    x = np.asarray(img, dtype=np.float32)
    return x / 127.5 - 1.0   # MobileNetV2 preprocess_input


def quality_check(img):
    """Simple image quality gate: blur (Laplacian variance) and exposure."""
    g = np.asarray(ImageOps.exif_transpose(img).convert("L").resize((256, 256)), dtype=np.float32)
    lap = (g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g[1:-1, 1:-1])
    issues = []
    if lap.var() < 60:
        issues.append("blurry")
    m = g.mean()
    if m < 45:
        issues.append("dark")
    elif m > 225:
        issues.append("bright")
    return issues


def embed(img):
    st = load()
    x = _prep(img)[None]
    return st["backbone"](x, training=False).numpy()[0]


def predict(img, crop=None):
    """
    Returns dict(label, conf, top3, feature, version, crop_mismatch).
    If the farmer selected a crop, probabilities are re-normalised over that crop's
    classes (+ background) — the unrestricted top-1 is kept to flag mismatches.
    """
    st = load()
    feat = embed(img)
    probs = st["head"](feat[None], training=False).numpy()[0]
    labels = st["labels"]
    raw_top = int(probs.argmax())
    p = probs.copy()
    mismatch = None
    if crop:
        from kb import DISEASES
        allowed = [i for i, l in enumerate(labels)
                   if DISEASES.get(l, {}).get("crop") == crop or l == "Background_without_leaves"]
        if allowed:
            mask = np.zeros_like(p)
            mask[allowed] = 1
            p = p * mask
            p = p / p.sum() if p.sum() > 0 else probs
            if raw_top not in allowed and probs[raw_top] > 0.6:
                mismatch = labels[raw_top]
    order = np.argsort(p)[::-1][:3]
    return {
        "label": labels[order[0]], "conf": float(p[order[0]]),
        "top3": [{"label": labels[i], "conf": round(float(p[i]), 4)} for i in order],
        "feature": feat, "version": st["version"], "crop_mismatch": mismatch,
    }


def save_feedback(report_id, feature, label):
    np.save(os.path.join(FEEDBACK_DIR, f"r{report_id}.npy"), feature.astype(np.float32))
    with open(os.path.join(FEEDBACK_DIR, f"r{report_id}.json"), "w") as f:
        json.dump({"label": label}, f)


def feedback_items():
    out = []
    for fn in os.listdir(FEEDBACK_DIR):
        if fn.endswith(".json"):
            rid = fn[:-5]
            npy = os.path.join(FEEDBACK_DIR, rid + ".npy")
            if os.path.exists(npy):
                with open(os.path.join(FEEDBACK_DIR, fn)) as f:
                    out.append((npy, json.load(f)["label"]))
    return out


def retrain(on_done=None):
    """
    Continual learning: fine-tune the current head on the original training features
    plus expert-confirmed field images (up-weighted x5).  The new head is activated
    only if accuracy on the untouched PlantVillage test split does not drop by more
    than 0.5 percentage points (guards against bad labels).
    """
    if retrain_status["running"]:
        return False
    if not os.path.exists(FEATURES):
        retrain_status["message"] = ("Retraining needs ml/features.npz (not stored in git because it is 189 MB). "
                                     "Run: python ml/train.py")
        return False

    def job():
        retrain_status.update(running=True, message="Loading data…")
        try:
            tf = _tf()
            st = load()
            labels = st["labels"]
            data = np.load(FEATURES)
            X, y = data["X"], data["y"]
            tr, te = data["train"], data["test"]
            items = feedback_items()
            idx = {l: i for i, l in enumerate(labels)}
            fx = np.array([np.load(p) for p, l in items if l in idx], dtype=np.float32).reshape(-1, X.shape[1])
            fy = np.array([idx[l] for p, l in items if l in idx], dtype=np.int64)

            old_acc = float((st["head"](X[te], training=False).numpy().argmax(1) == y[te]).mean())
            retrain_status["message"] = f"Training on {len(tr)} + {len(fy)} field images…"
            head = tf.keras.models.clone_model(st["head"])
            head.set_weights(st["head"].get_weights())
            head.compile(optimizer=tf.keras.optimizers.Adam(2e-4),
                         loss="sparse_categorical_crossentropy", metrics=["accuracy"])
            Xt = np.concatenate([X[tr], fx]) if len(fy) else X[tr]
            yt = np.concatenate([y[tr], fy]) if len(fy) else y[tr]
            w = np.concatenate([np.ones(len(tr)), np.full(len(fy), 5.0)]) if len(fy) else np.ones(len(tr))
            head.fit(Xt, yt, sample_weight=w, epochs=6, batch_size=128, verbose=0, shuffle=True)

            new_acc = float((head(X[te], training=False).numpy().argmax(1) == y[te]).mean())
            fb_acc = float((head(fx, training=False).numpy().argmax(1) == fy).mean()) if len(fy) else None
            new_v = max(int(f[6:-6]) for f in os.listdir(MODEL_DIR) if f.startswith("head_v")) + 1
            head.save(os.path.join(MODEL_DIR, f"head_v{new_v}.keras"))
            accepted = new_acc >= old_acc - 0.005
            if accepted:
                with open(os.path.join(MODEL_DIR, "active.json"), "w") as f:
                    json.dump({"version": new_v}, f)
                load(force=True)
            result = {"version": new_v, "test_accuracy": new_acc, "previous_accuracy": old_acc,
                      "feedback_accuracy": fb_acc, "n_feedback": int(len(fy)), "accepted": accepted,
                      "time": time.strftime("%Y-%m-%d %H:%M")}
            retrain_status.update(message=("Model v%d activated" if accepted else "Model v%d rejected (accuracy dropped)") % new_v,
                                  last=result)
            if on_done:
                on_done(result)
        except Exception as e:  # surfaced on the admin page
            retrain_status["message"] = f"Retraining failed: {e}"
        finally:
            retrain_status["running"] = False

    threading.Thread(target=job, daemon=True).start()
    return True
