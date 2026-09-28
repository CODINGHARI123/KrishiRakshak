"""
File locations.  Locally everything lives inside the project folder.
On Vercel (read-only file system) writable data goes to /tmp: the bundled demo
database is copied there on a cold start, so demo data is always available but
new records reset whenever Vercel starts a fresh instance.
"""
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("KRISHI_SERVERLESS"))
RUNTIME = "/tmp/krishirakshak" if IS_SERVERLESS else BASE

BUNDLED_DB = os.path.join(BASE, "krishirakshak.db")
DB_PATH = os.path.join(RUNTIME, "krishirakshak.db")
BUNDLED_UPLOADS = os.path.join(BASE, "static", "uploads")          # demo photos shipped with the app
UPLOAD_DIR = os.path.join(RUNTIME, "uploads") if IS_SERVERLESS else BUNDLED_UPLOADS
EMB_DIR = os.path.join(RUNTIME, "ml", "embeddings")
FEEDBACK_DIR = os.path.join(RUNTIME, "ml", "feedback")
SECRET_FILE = os.path.join(RUNTIME, ".secret_key")

for d in (RUNTIME, UPLOAD_DIR, EMB_DIR, FEEDBACK_DIR):
    os.makedirs(d, exist_ok=True)
if IS_SERVERLESS and not os.path.exists(DB_PATH) and os.path.exists(BUNDLED_DB):
    shutil.copyfile(BUNDLED_DB, DB_PATH)
