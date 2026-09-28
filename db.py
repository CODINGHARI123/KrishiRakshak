"""SQLite storage for KrishiRakshak."""
import os
import sqlite3

from flask import g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "krishirakshak.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id, is_read);
"""


def connect():
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
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid
