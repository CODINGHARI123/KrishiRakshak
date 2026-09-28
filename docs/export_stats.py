"""Dump live dashboard statistics (same numbers as /api/stats) to docs/stats.json for the PPT/report."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as webapp  # noqa: E402
import db  # noqa: E402

c = webapp.app.test_client()
with webapp.app.app_context():
    oid = db.query("SELECT id FROM users WHERE username='officer'", one=True)["id"]
with c.session_transaction() as s:
    s["uid"] = oid
stats = c.get("/api/stats?days=90").get_json()
hs = c.get("/api/hotspots").get_json()
with webapp.app.app_context():
    stats["farms"] = db.query("SELECT COUNT(*) c FROM farms", one=True)["c"]
    stats["reports"] = db.query("SELECT COUNT(*) c FROM reports", one=True)["c"]
    stats["traps"] = db.query("SELECT COUNT(*) c FROM trap_readings", one=True)["c"]
    stats["feedback"] = db.query("SELECT COUNT(*) c FROM reports WHERE used_for_training=1", one=True)["c"]
stats["hotspots"] = len(hs)
stats["hotspot_list"] = [{"name": h["name"], "cases": h["cases"], "radius_km": h["radius_km"], "districts": h["districts"]} for h in hs]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.json")
json.dump(stats, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(json.dumps(stats["kpi"], indent=1))
print("hotspots:", [(h["name"], h["cases"]) for h in hs])
