"""
KrishiRakshak - crop disease classifier training.

Transfer learning with MobileNetV2 (ImageNet) on the PlantVillage dataset
(39 classes = 38 crop/disease classes + background).

Because training runs on a CPU-only laptop, it is done in two stages:
  1. The frozen MobileNetV2 backbone converts every image into a 1280-d
     feature vector once (cached to features.npz).
  2. A small classification head is trained on the cached features.
The backbone + head are then joined into one Keras model for inference.
The cached features are also reused by retrain.py to learn from
expert-confirmed field images.

Usage:  python train.py
"""
import json
import os
import random
import time

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import numpy as np
import tensorflow as tf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data", "plantvillage")
OUT_DIR = os.path.join(HERE, "model")
PLOT_DIR = os.path.join(HERE, "plots")
IMG_SIZE = 224
BATCH = 64
SEED = 42

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)
random.seed(SEED)
np.random.seed(SEED)
tf.random.set_seed(SEED)


def list_images():
    labels = sorted(d for d in os.listdir(DATA_DIR) if os.path.isdir(os.path.join(DATA_DIR, d)))
    paths, ys = [], []
    for i, lab in enumerate(labels):
        folder = os.path.join(DATA_DIR, lab)
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                paths.append(os.path.join(folder, f))
                ys.append(i)
    return labels, np.array(paths), np.array(ys)


def load_image(path):
    img = tf.io.decode_image(tf.io.read_file(path), channels=3, expand_animations=False)
    img = tf.image.resize(img, (IMG_SIZE, IMG_SIZE))
    return tf.keras.applications.mobilenet_v2.preprocess_input(img)


def build_backbone():
    return tf.keras.applications.MobileNetV2(
        weights="imagenet", include_top=False, pooling="avg", input_shape=(IMG_SIZE, IMG_SIZE, 3)
    )


def build_head(n_classes):
    inp = tf.keras.Input(shape=(1280,), name="features")
    x = tf.keras.layers.Dropout(0.3)(inp)
    x = tf.keras.layers.Dense(256, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    out = tf.keras.layers.Dense(n_classes, activation="softmax")(x)
    head = tf.keras.Model(inp, out, name="head")
    head.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                 loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return head


def extract(backbone, paths):
    ds = (tf.data.Dataset.from_tensor_slices(paths)
          .map(load_image, num_parallel_calls=tf.data.AUTOTUNE)
          .batch(BATCH).prefetch(tf.data.AUTOTUNE))
    feats = []
    t0 = time.time()
    n_batches = int(np.ceil(len(paths) / BATCH))
    for i, batch in enumerate(ds):
        feats.append(backbone(batch, training=False).numpy())
        if i % 50 == 0 or i == n_batches - 1:
            done = min((i + 1) * BATCH, len(paths))
            rate = done / (time.time() - t0)
            print(f"  {done}/{len(paths)} images  ({rate:.0f} img/s, ~{(len(paths) - done) / rate / 60:.1f} min left)", flush=True)
    return np.concatenate(feats).astype(np.float32)


def plot_history(hist):
    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(hist["accuracy"], label="train")
    ax[0].plot(hist["val_accuracy"], label="validation")
    ax[0].set_title("Accuracy"); ax[0].set_xlabel("epoch"); ax[0].legend(); ax[0].grid(alpha=.3)
    ax[1].plot(hist["loss"], label="train")
    ax[1].plot(hist["val_loss"], label="validation")
    ax[1].set_title("Loss"); ax[1].set_xlabel("epoch"); ax[1].legend(); ax[1].grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOT_DIR, "training_curves.png"), dpi=150)
    plt.close(fig)


def short(label):
    crop, _, dis = label.partition("___")
    return (crop.split("_")[0].split(",")[0] + ": " + dis.replace("_", " ").strip())[:32] if dis else label.replace("_", " ")


def plot_confusion(cm, labels):
    cmn = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(15, 13))
    im = ax.imshow(cmn, cmap="Greens", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels))); ax.set_yticks(range(len(labels)))
    ax.set_xticklabels([short(l) for l in labels], rotation=90, fontsize=7)
    ax.set_yticklabels([short(l) for l in labels], fontsize=7)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
    ax.set_title("Normalised confusion matrix (test set)")
    fig.colorbar(im, fraction=0.046)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOT_DIR, "confusion_matrix.png"), dpi=150)
    plt.close(fig)


def plot_distribution(labels, ys):
    counts = np.bincount(ys, minlength=len(labels))
    order = np.argsort(counts)
    fig, ax = plt.subplots(figsize=(9, 10))
    ax.barh([short(labels[i]) for i in order], counts[order], color="#2e7d32")
    ax.set_xlabel("images"); ax.set_title("PlantVillage class distribution")
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOT_DIR, "class_distribution.png"), dpi=150)
    plt.close(fig)


def main():
    labels, paths, ys = list_images()
    print(f"{len(paths)} images, {len(labels)} classes")
    plot_distribution(labels, ys)

    idx = np.arange(len(paths))
    tr, tmp = train_test_split(idx, test_size=0.30, stratify=ys, random_state=SEED)
    va, te = train_test_split(tmp, test_size=0.50, stratify=ys[tmp], random_state=SEED)
    print(f"split: train={len(tr)} val={len(va)} test={len(te)}")

    cache = os.path.join(HERE, "features.npz")
    if os.path.exists(cache):
        print("loading cached features")
        feats = np.load(cache)["X"]
    else:
        print("extracting MobileNetV2 features (one-time)...")
        feats = extract(build_backbone(), paths)
        np.savez_compressed(cache, X=feats, y=ys, paths=paths, train=tr, val=va, test=te)

    cw = compute_class_weight("balanced", classes=np.arange(len(labels)), y=ys[tr])
    head = build_head(len(labels))
    t0 = time.time()
    hist = head.fit(
        feats[tr], ys[tr], validation_data=(feats[va], ys[va]),
        epochs=60, batch_size=128, class_weight=dict(enumerate(cw)), verbose=2,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True, monitor="val_accuracy"),
            tf.keras.callbacks.ReduceLROnPlateau(patience=3, factor=0.5, monitor="val_loss"),
        ],
    )
    train_secs = time.time() - t0
    plot_history(hist.history)

    probs = head.predict(feats[te], verbose=0)
    pred = probs.argmax(1)
    acc = float((pred == ys[te]).mean())
    top3 = float(np.mean([ys[te][i] in np.argsort(probs[i])[-3:] for i in range(len(te))]))
    cm = confusion_matrix(ys[te], pred)
    plot_confusion(cm, labels)
    rep = classification_report(ys[te], pred, target_names=labels, output_dict=True, zero_division=0)
    print(classification_report(ys[te], pred, target_names=[short(l) for l in labels], digits=3, zero_division=0))
    print(f"TEST accuracy={acc:.4f}  top-3={top3:.4f}")

    # Join backbone + head into a single inference model.
    backbone = build_backbone()
    inp = tf.keras.Input(shape=(IMG_SIZE, IMG_SIZE, 3))
    full = tf.keras.Model(inp, head(backbone(inp, training=False)))
    full.save(os.path.join(OUT_DIR, "krishi_model.keras"))
    head.save(os.path.join(OUT_DIR, "head_v1.keras"))

    with open(os.path.join(OUT_DIR, "labels.json"), "w") as f:
        json.dump(labels, f, indent=1)
    metrics = {
        "version": 1,
        "architecture": "MobileNetV2 (ImageNet, frozen) + Dense(256) head",
        "dataset": "PlantVillage (Mendeley Data, without augmentation)",
        "n_images": int(len(paths)), "n_classes": len(labels),
        "split": {"train": int(len(tr)), "val": int(len(va)), "test": int(len(te))},
        "epochs_run": len(hist.history["loss"]), "head_train_seconds": round(train_secs, 1),
        "test_accuracy": acc, "test_top3_accuracy": top3,
        "macro_f1": rep["macro avg"]["f1-score"], "weighted_f1": rep["weighted avg"]["f1-score"],
        "per_class": {l: {k: round(rep[l][k], 4) for k in ("precision", "recall", "f1-score", "support")} for l in labels},
        "history": {k: [float(v) for v in vs] for k, vs in hist.history.items()},
        "trained_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    with open(os.path.join(OUT_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1)
    print("saved model to", OUT_DIR)


if __name__ == "__main__":
    main()
