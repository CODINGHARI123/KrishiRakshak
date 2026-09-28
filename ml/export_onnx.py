"""
Export the model for lightweight deployment (e.g. Vercel), run locally after training:

    python ml/export_onnx.py

* ml/model/backbone.onnx   – frozen MobileNetV2 feature extractor (ONNX, runs with onnxruntime)
* ml/model/head_vN.npz     – classifier weights of every head version (plain NumPy)

The deployed app then needs only numpy + onnxruntime instead of TensorFlow.
"""
import glob
import os

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
import numpy as np
import tensorflow as tf
import tf2onnx

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")


def export_head(path):
    head = tf.keras.models.load_model(path, compile=False)
    dense = [l for l in head.layers if isinstance(l, tf.keras.layers.Dense)]
    (w1, b1), (w2, b2) = dense[0].get_weights(), dense[1].get_weights()
    out = path.replace(".keras", ".npz")
    np.savez(out, w1=w1, b1=b1, w2=w2, b2=b2)
    return out


def export_backbone():
    full = tf.keras.models.load_model(os.path.join(MODEL_DIR, "krishi_model.keras"), compile=False)
    backbone = next(l for l in full.layers if "mobilenet" in l.name.lower())
    spec = (tf.TensorSpec((None, 224, 224, 3), tf.float32, name="image"),)

    @tf.function(input_signature=spec)
    def features(image):
        return {"features": backbone(image, training=False)}

    out = os.path.join(MODEL_DIR, "backbone.onnx")
    tf2onnx.convert.from_function(features, input_signature=spec, opset=13, output_path=out)
    return backbone, out


if __name__ == "__main__":
    backbone, onnx_path = export_backbone()
    print("wrote", onnx_path, f"{os.path.getsize(onnx_path) / 1e6:.1f} MB")
    for p in sorted(glob.glob(os.path.join(MODEL_DIR, "head_v*.keras"))):
        print("wrote", export_head(p))

    # sanity check: ONNX + numpy head must match TensorFlow
    import onnxruntime as ort
    x = np.random.RandomState(0).uniform(-1, 1, (4, 224, 224, 3)).astype(np.float32)
    tf_feat = backbone(x, training=False).numpy()
    sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
    ox_feat = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    print("max feature difference TF vs ONNX:", float(np.abs(tf_feat - ox_feat).max()))
