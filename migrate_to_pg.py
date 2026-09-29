"""
Copy the local demo database (krishirakshak.db, SQLite) into PostgreSQL (e.g. Neon on Vercel).

    set DATABASE_URL=postgresql://...        (Windows: $env:DATABASE_URL="..." in PowerShell)
    python migrate_to_pg.py

Safety: refuses to run if the Postgres database already contains users, so real
registrations are never overwritten (use --force only on an empty/test database).

Optional: OFFICER_PASSWORD / ADMIN_PASSWORD env vars replace the demo passwords of the
officer and admin accounts in Postgres (recommended for a public website).
"""
import os
import sqlite3
import sys

from werkzeug.security import generate_password_hash

import db
from paths import BUNDLED_DB

ORDER = ["users", "labs", "farms", "reports", "followups", "trap_readings", "sensor_readings",
         "alerts", "model_versions", "images"]


def main():
    if not db.IS_PG:
        sys.exit("Set DATABASE_URL (or POSTGRES_URL) to a postgresql:// connection string first.")
    src = sqlite3.connect(BUNDLED_DB)
    src.row_factory = sqlite3.Row
    pg = db.connect()
    pg.executescript(db.pg_schema())
    pg.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")
    pg.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    pg.commit()

    existing = pg.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if existing and "--force" not in sys.argv:
        sys.exit(f"Postgres already has {existing} users – nothing copied (protects real registrations).")
    if existing:
        pg.execute("TRUNCATE " + ", ".join(reversed(ORDER)) + " RESTART IDENTITY CASCADE")

    for table in ORDER:
        rows = src.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            print(f"{table:16s} 0 rows")
            continue
        cols = rows[0].keys()
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
        cur = pg.raw.cursor()
        cur.executemany(sql.replace("?", "%s"), [tuple(r) for r in rows])
        if "id" in cols:
            pg.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))")
        print(f"{table:16s} {len(rows)} rows")

    for role, var in (("officer", "OFFICER_PASSWORD"), ("admin", "ADMIN_PASSWORD")):
        if os.environ.get(var):
            pg.execute("UPDATE users SET password_hash=? WHERE role=?", (generate_password_hash(os.environ[var]), role))
            print(f"{role} passwords replaced from {var}")
    pg.commit()
    pg.close()
    print("done")


if __name__ == "__main__":
    main()
