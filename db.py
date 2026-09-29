"""
Database layer for KrishiRakshak.

* Local development: SQLite file (krishirakshak.db).
* Deployment (Vercel): PostgreSQL (e.g. Neon) when DATABASE_URL / POSTGRES_URL is set,
  so every server instance shares the same users, farms, reports and photos.

App code always writes SQLite-style SQL with `?` placeholders; this module adapts it.
"""
import datetime as dt
import os
import sqlite3

from flask import g

from paths import DB_PATH

PG_URL = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
          or os.environ.get("POSTGRES_PRISMA_URL") or "")
IS_PG = PG_URL.startswith(("postgres://", "postgresql://"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('farmer', 'officer', 'admin')),
    name TEXT NOT NULL,
    phone TEXT,
    district TEXT,
    lang TEXT DEFAULT 'en',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS farms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    village TEXT, district TEXT,
    lat REAL NOT NULL, lon REAL NOT NULL,
    crop TEXT NOT NULL,
    variety TEXT,
    resistance TEXT DEFAULT 'S',          -- S susceptible, MR moderately resistant, R resistant
    sowing_date TEXT,
    area_acres REAL,
    soil_type TEXT,
    drainage TEXT DEFAULT 'moderate',     -- good / moderate / poor
    irrigation TEXT DEFAULT 'flood',      -- drip / flood / sprinkler / rainfed
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS labs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, kind TEXT, district TEXT,
    lat REAL, lon REAL, contact TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    farm_id INTEGER REFERENCES farms(id),
    image_path TEXT,
    crop TEXT,
    lat REAL, lon REAL, district TEXT, village TEXT,
    ai_label TEXT, ai_conf REAL, ai_top3 TEXT, model_version INTEGER,
    quality_note TEXT,
    status TEXT DEFAULT 'pending',        -- pending / confirmed / corrected / rejected
    final_label TEXT,
    severity TEXT,                        -- low / medium / high
    officer_id INTEGER REFERENCES users(id),
    officer_note TEXT,
    referred INTEGER DEFAULT 0,
    referral_reason TEXT,
    lab_id INTEGER REFERENCES labs(id),
    chemical_advised INTEGER DEFAULT 0,
    used_for_training INTEGER DEFAULT 0,
    source TEXT DEFAULT 'app',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    validated_at TEXT
);
CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    due_date TEXT NOT NULL,
    status TEXT DEFAULT 'due',            -- due / done
    outcome TEXT,                         -- better / same / worse
    note TEXT,
    done_at TEXT
);
CREATE TABLE IF NOT EXISTS trap_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER REFERENCES farms(id),
    user_id INTEGER REFERENCES users(id),
    pest TEXT NOT NULL,
    count REAL NOT NULL,
    traps INTEGER DEFAULT 1,
    days INTEGER DEFAULT 1,
    value REAL,                           -- normalised to the pest's ETL unit
    above_etl INTEGER DEFAULT 0,
    source TEXT DEFAULT 'manual',         -- manual / sensor
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    farm_id INTEGER REFERENCES farms(id),
    device_id TEXT,
    temp REAL, rh REAL, leaf_wetness REAL, soil_moisture REAL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    farm_id INTEGER REFERENCES farms(id),
    kind TEXT,                            -- weather / hotspot / trap / followup / validation
    level TEXT,                           -- low / moderate / high / severe
    ref TEXT,                             -- disease/pest/model key for translation
    detail TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version INTEGER NOT NULL,
    test_accuracy REAL,
    feedback_accuracy REAL,
    n_feedback INTEGER DEFAULT 0,
    active INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS images (
    name TEXT PRIMARY KEY,                -- uploaded leaf photos (shared by all server instances)
    data BLOB NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, is_read);
"""
TABLES = ["users", "labs", "farms", "reports", "followups", "trap_readings", "sensor_readings",
          "alerts", "model_versions", "images"]


def pg_schema():
    s = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    s = s.replace(" REAL", " DOUBLE PRECISION").replace(" BLOB", " BYTEA")
    return s.replace("DEFAULT (datetime('now','localtime'))",
                     "DEFAULT (to_char(now() AT TIME ZONE 'Asia/Kolkata', 'YYYY-MM-DD HH24:MI:SS'))")


def now():
    """Local timestamp string used for created/validated/done columns."""
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ connections
class _PgConn:
    """Minimal sqlite3-like wrapper around a psycopg connection."""

    def __init__(self):
        import psycopg
        from psycopg.rows import dict_row
        self.raw = psycopg.connect(PG_URL, row_factory=dict_row, prepare_threshold=None, connect_timeout=15)

    def execute(self, sql, args=()):
        sql = sql.replace("%", "%%").replace("?", "%s")
        cur = self.raw.cursor()
        cur.execute(sql, args)
        return cur

    def executescript(self, script):
        with self.raw.cursor() as cur:
            cur.execute(script)

    def commit(self):
        self.raw.commit()

    def close(self):
        self.raw.close()


def connect():
    if IS_PG:
        return _PgConn()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = connect()
    if IS_PG:
        conn.executescript(pg_schema())
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")
    else:
        conn.executescript(SCHEMA)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "email" not in cols:   # upgrade older local databases
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ helpers used by the app
def query(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    """Run a write statement; returns the new row id for INSERTs."""
    db = get_db()
    if IS_PG and sql.lstrip().upper().startswith("INSERT") and "RETURNING" not in sql.upper():
        row = db.execute(sql + " RETURNING id", args).fetchone()
        db.commit()
        return row["id"] if row else None
    cur = db.execute(sql, args)
    db.commit()
    return getattr(cur, "lastrowid", None)
