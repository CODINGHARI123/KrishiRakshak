"""
KrishiRakshak – AI-based crop health surveillance & advisory system.

Run:  python app.py      then open http://localhost:5000 in Chrome.
"""
import datetime as dt
import functools
import io
import json
import os
import secrets
import threading
import time
import uuid

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash

import db
import hotspots as hs
import kb
import ml_service
import risk

BASE = os.path.dirname(os.path.abspath(__file__))
from paths import BUNDLED_UPLOADS, EMB_DIR, IS_SERVERLESS, SECRET_FILE, UPLOAD_DIR  # noqa: E402

PLOT_DIR = os.path.join(BASE, "ml", "plots")


def _secret():
    # On Vercel set KRISHI_SECRET_KEY so every instance shares the same session key.
    if os.environ.get("KRISHI_SECRET_KEY"):
        return os.environ["KRISHI_SECRET_KEY"]
    p = SECRET_FILE
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(secrets.token_hex(32))
    with open(p) as f:
        return f.read().strip()


app = Flask(__name__)
app.secret_key = _secret()
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
# Shared key that IoT trap / weather-station devices send in the X-Device-Key header.
DEVICE_KEY = os.environ.get("KRISHI_DEVICE_KEY", "demo-device-key")
app.teardown_appcontext(db.close_db)
db.init_db()

LEVEL_ORDER = {"low": 0, "moderate": 1, "high": 2, "severe": 3}


# ---------------------------------------------------------------- helpers
@app.before_request
def load_user():
    g.user = None
    if "uid" in session:
        g.user = db.query("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)
    g.lang = session.get("lang") or (g.user["lang"] if g.user else None) or "en"
    if g.lang not in kb.LANGS:
        g.lang = "en"


def T(key, **kw):
    return kb.t(key, g.lang, **kw)


def risk_name(key, lang=None):
    lang = lang or g.lang
    if key in kb.PESTS:
        return kb.loc(kb.PESTS[key]["name"], lang)
    return kb.t("model." + key, lang)


def label_name(label, lang=None):
    lang = lang or g.lang
    if label in kb.PESTS:
        return kb.loc(kb.PESTS[label]["name"], lang)
    return kb.full_name(label, lang)


@app.context_processor
def inject():
    unread = 0
    if g.get("user"):
        unread = db.query("SELECT COUNT(*) c FROM alerts WHERE user_id=? AND is_read=0",
                          (g.user["id"],), one=True)["c"]
    return dict(t=T, lang=g.lang, img_url=lambda p: url_for("media", name=os.path.basename(p or "")), LANGS=kb.LANGS, user=g.get("user"), unread=unread,
                label_name=label_name, crop_name=lambda c: kb.crop_name(c, g.lang), risk_name=risk_name,
                CROPS=kb.CROPS, PESTS=kb.PESTS, DISEASES=kb.DISEASES, speech_lang=kb.SPEECH_LANG[g.lang],
                today=dt.date.today().isoformat())


def login_required(*roles):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            if not g.user:
                return redirect(url_for("login", next=request.path))
            if roles and g.user["role"] not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def is_staff():
    return g.user and g.user["role"] in ("officer", "admin")


def add_alert(user_id, farm_id, kind, level, ref, detail="", dedupe_days=2):
    since = (dt.datetime.now() - dt.timedelta(days=dedupe_days)).strftime("%Y-%m-%d %H:%M:%S")
    dup = db.query("SELECT id FROM alerts WHERE user_id=? AND IFNULL(farm_id,0)=IFNULL(?,0) AND kind=? AND ref=? "
                   "AND created_at>=?", (user_id, farm_id, kind, ref, since), one=True)
    if not dup:
        db.execute("INSERT INTO alerts(user_id,farm_id,kind,level,ref,detail) VALUES (?,?,?,?,?,?)",
                   (user_id, farm_id, kind, level, ref, detail))


def staff_ids():
    return [r["id"] for r in db.query("SELECT id FROM users WHERE role IN ('officer','admin')")]


def nearby_case_counts(lat, lon, km=10, days=21):
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.query("SELECT lat, lon, COALESCE(final_label, ai_label) label FROM reports "
                    "WHERE status IN ('confirmed','corrected') AND created_at>=? AND lat IS NOT NULL", (since,))
    counts = {}
    for r in rows:
        if abs(r["lat"] - lat) > 0.2 or abs(r["lon"] - lon) > 0.2:
            continue
        if risk.haversine_km(lat, lon, r["lat"], r["lon"]) <= km:
            d = kb.DISEASES.get(r["label"])
            if d and d.get("model") not in (None, "none"):
                counts[d["model"]] = counts.get(d["model"], 0) + 1
    trap_since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    for r in db.query("SELECT t.pest, f.lat, f.lon FROM trap_readings t JOIN farms f ON f.id=t.farm_id "
                      "WHERE t.above_etl=1 AND t.created_at>=?", (trap_since,)):
        if risk.haversine_km(lat, lon, r["lat"], r["lon"]) <= km:
            counts[r["pest"]] = counts.get(r["pest"], 0) + 1
    return counts


def latest_sensor(farm_id):
    since = (dt.datetime.now() - dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    return db.query("SELECT * FROM sensor_readings WHERE farm_id=? AND created_at>=? ORDER BY id DESC LIMIT 1",
                    (farm_id, since), one=True)


def compute_farm_risk(farm, make_alerts=True):
    res = risk.farm_risk(farm, nearby_case_counts(farm["lat"], farm["lon"]), latest_sensor(farm["id"]))
    if make_alerts:
        for r in res["risks"]:
            if LEVEL_ORDER[r["level"]] >= 2:
                add_alert(farm["user_id"], farm["id"], "weather", r["level"], r["key"],
                          json.dumps({"score": r["score"], "peak": r["peak_date"]}))
    return res


def nearest_lab(lat, lon, kind=None):
    rows = db.query("SELECT * FROM labs" + (" WHERE kind=?" if kind else ""), (kind,) if kind else ())
    if not rows or lat is None:
        return None
    return min(rows, key=lambda r: risk.haversine_km(lat, lon, r["lat"], r["lon"]))


def report_rows_for_hotspots(days=30):
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.query("SELECT id, lat, lon, district, created_at, status, ai_conf, "
                    "COALESCE(final_label, ai_label) label FROM reports "
                    "WHERE lat IS NOT NULL AND created_at>=? AND (status IN ('confirmed','corrected') "
                    "OR (status='pending' AND ai_conf>=0.9))", (since,))
    return [dict(r) for r in rows]


def current_hotspots():
    return hs.find_hotspots(report_rows_for_hotspots())


def hotspot_alerts():
    """Warn every farm growing the affected crop within a hotspot's radius (+5 km buffer)."""
    spots = current_hotspots()
    farms = db.query("SELECT * FROM farms")
    n = 0
    for h in spots:
        crop = kb.label_crop(h["label"])
        for f in farms:
            if f["crop"] == crop and risk.haversine_km(h["lat"], h["lon"], f["lat"], f["lon"]) <= h["radius_km"] + 5:
                add_alert(f["user_id"], f["id"], "hotspot", h["severity"], h["label"],
                          json.dumps({"cases": h["cases"], "km": round(risk.haversine_km(h["lat"], h["lon"], f["lat"], f["lon"]), 1)}),
                          dedupe_days=3)
                n += 1
    return spots, n


def surveillance_scan():
    """Periodic job: weather risk for every farm + hotspot alerts."""
    conn_app = app.app_context()
    with conn_app:
        for f in db.query("SELECT * FROM farms"):
            try:
                compute_farm_risk(f)
            except Exception:
                pass
        hotspot_alerts()
        today = dt.date.today().isoformat()
        for fu in db.query("SELECT fu.*, r.user_id, r.farm_id, COALESCE(r.final_label, r.ai_label) label FROM followups fu "
                           "JOIN reports r ON r.id=fu.report_id WHERE fu.status='due' AND fu.due_date<=?", (today,)):
            add_alert(fu["user_id"], fu["farm_id"], "followup", "moderate", fu["label"], str(fu["report_id"]), dedupe_days=1)


def _scheduler():
    time.sleep(20)
    while True:
        try:
            surveillance_scan()
        except Exception:
            pass
        time.sleep(6 * 3600)


# ---------------------------------------------------------------- public
@app.route("/")
def index():
    if g.user:
        return redirect(url_for("officer_home" if is_staff() else "farmer_home"))
    stats = {
        "reports": db.query("SELECT COUNT(*) c FROM reports", one=True)["c"],
        "farms": db.query("SELECT COUNT(*) c FROM farms", one=True)["c"],
        "classes": len(kb.DISEASES) - 1,
        "hotspots": len(current_hotspots()),
    }
    metrics = _metrics()
    return render_template("index.html", stats=stats, metrics=metrics)


@app.route("/lang/<code>")
def set_lang(code):
    if code in kb.LANGS:
        session["lang"] = code
        if g.user:
            db.execute("UPDATE users SET lang=? WHERE id=?", (code, g.user["id"]))
    return redirect(request.referrer or url_for("index"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db.query("SELECT * FROM users WHERE username=?", (request.form["username"].strip().lower(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session["uid"] = u["id"]
            session["lang"] = u["lang"] or g.lang
            nxt = request.args.get("next")
            return redirect(nxt if nxt and nxt.startswith("/") else url_for("index"))
        flash(T("login.invalid"), "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    lang = session.get("lang")
    session.clear()
    session["lang"] = lang
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        username = f["username"].strip().lower()
        if not username or len(f["password"]) < 6:
            flash(T("register.invalid"), "error")
        elif db.query("SELECT id FROM users WHERE username=?", (username,), one=True):
            flash(T("register.taken"), "error")
        else:
            uid = db.execute("INSERT INTO users(username,password_hash,role,name,phone,district,lang) VALUES (?,?,?,?,?,?,?)",
                             (username, generate_password_hash(f["password"]), "farmer", f["name"].strip(),
                              f.get("phone"), f.get("district"), g.lang))
            session["uid"] = uid
            flash(T("register.ok"), "ok")
            return redirect(url_for("farm_new"))
    return render_template("register.html")


# ---------------------------------------------------------------- farmer
@app.route("/farmer")
@login_required()
def farmer_home():
    farms = db.query("SELECT * FROM farms WHERE user_id=? ORDER BY id", (g.user["id"],))
    cards = []
    for f in farms:
        try:
            r = compute_farm_risk(f)
            top = r["risks"][:3]
            src = r["weather"]["source"]
            today_w = next((d for d in r["weather"]["days"] if d["date"] == dt.date.today().isoformat()), None)
        except Exception:
            top, src, today_w, r = [], "error", None, {"stage": "", "das": None}
        cards.append({"farm": f, "risks": top, "source": src, "today": today_w, "stage": r["stage"], "das": r["das"]})
    alerts = db.query("SELECT * FROM alerts WHERE user_id=? ORDER BY is_read, id DESC LIMIT 8", (g.user["id"],))
    due = db.query("SELECT fu.*, r.image_path, COALESCE(r.final_label, r.ai_label) label FROM followups fu "
                   "JOIN reports r ON r.id=fu.report_id WHERE r.user_id=? AND fu.status='due' ORDER BY fu.due_date LIMIT 5",
                   (g.user["id"],))
    reports = db.query("SELECT * FROM reports WHERE user_id=? ORDER BY id DESC LIMIT 6", (g.user["id"],))
    return render_template("farmer_home.html", cards=cards, alerts=[_alert_view(a) for a in alerts], due=due, reports=reports)


def _alert_view(a):
    a = dict(a)
    try:
        det = json.loads(a["detail"]) if a["detail"] and a["detail"].startswith("{") else {}
    except ValueError:
        det = {}
    ref = a["ref"]
    if a["kind"] == "weather":
        a["title"] = T("alert.weather", name=risk_name(ref))
        a["body"] = T("alert.weather_body", score=det.get("score", "?"), date=det.get("peak") or "")
    elif a["kind"] == "hotspot":
        a["title"] = T("alert.hotspot", name=label_name(ref))
        a["body"] = T("alert.hotspot_body", cases=det.get("cases", "?"), km=det.get("km", "?"))
    elif a["kind"] == "trap":
        a["title"] = T("alert.trap", name=label_name(ref))
        a["body"] = T("alert.trap_body", value=det.get("value", "?"), etl=det.get("etl", "?"), unit=det.get("unit", ""))
    elif a["kind"] == "followup":
        a["title"] = T("alert.followup", name=label_name(ref))
        a["body"] = T("alert.followup_body")
        a["link"] = url_for("report_view", rid=int(a["detail"])) if (a["detail"] or "").isdigit() else None
    elif a["kind"] == "validation":
        a["title"] = T("alert.validated", name=label_name(ref))
        a["body"] = T("alert.validated_body")
        a["link"] = url_for("report_view", rid=int(det.get("report", 0))) if det.get("report") else None
    elif a["kind"] == "worse":
        a["title"] = T("alert.worse", name=label_name(ref))
        a["body"] = T("alert.worse_body")
        a["link"] = url_for("officer_review", rid=int(det.get("report", 0))) if det.get("report") else None
    elif a["kind"] == "newreport":
        a["title"] = T("alert.newreport", name=label_name(ref))
        a["body"] = T("alert.newreport_body", conf=det.get("conf", "?"))
        a["link"] = url_for("officer_review", rid=int(det.get("report", 0))) if det.get("report") else None
    else:
        a["title"], a["body"] = ref, a["detail"]
    return a


@app.route("/alerts")
@login_required()
def alerts_page():
    rows = db.query("SELECT a.*, f.name farm_name FROM alerts a LEFT JOIN farms f ON f.id=a.farm_id "
                    "WHERE a.user_id=? ORDER BY a.id DESC LIMIT 100", (g.user["id"],))
    views = [_alert_view(r) | {"farm_name": r["farm_name"]} for r in rows]
    db.execute("UPDATE alerts SET is_read=1 WHERE user_id=?", (g.user["id"],))
    return render_template("alerts.html", alerts=views)


@app.route("/farms/new", methods=["GET", "POST"])
@login_required()
def farm_new():
    if request.method == "POST":
        f = request.form
        try:
            lat, lon = float(f["lat"]), float(f["lon"])
        except (KeyError, ValueError):
            flash(T("farm.need_location"), "error")
            return render_template("farm_form.html")
        fid = db.execute(
            "INSERT INTO farms(user_id,name,village,district,lat,lon,crop,variety,resistance,sowing_date,area_acres,"
            "soil_type,drainage,irrigation) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (g.user["id"], f["name"], f.get("village"), f.get("district"), lat, lon, f["crop"], f.get("variety"),
             f.get("resistance", "S"), f.get("sowing_date") or None, float(f.get("area_acres") or 0) or None,
             f.get("soil_type"), f.get("drainage", "moderate"), f.get("irrigation", "flood")))
        return redirect(url_for("farm_view", fid=fid))
    return render_template("farm_form.html")


def _farm_or_404(fid):
    f = db.query("SELECT * FROM farms WHERE id=?", (fid,), one=True)
    if not f or (f["user_id"] != g.user["id"] and not is_staff()):
        abort(404)
    return f


@app.route("/farms/<int:fid>")
@login_required()
def farm_view(fid):
    f = _farm_or_404(fid)
    r = compute_farm_risk(f)
    traps = db.query("SELECT * FROM trap_readings WHERE farm_id=? ORDER BY id DESC LIMIT 15", (fid,))
    sensors = db.query("SELECT * FROM sensor_readings WHERE farm_id=? ORDER BY id DESC LIMIT 10", (fid,))
    reports = db.query("SELECT * FROM reports WHERE farm_id=? ORDER BY id DESC LIMIT 10", (fid,))
    pests = [k for k, p in kb.PESTS.items() if f["crop"] in p["crops"]]
    return render_template("farm_view.html", farm=f, r=r, traps=traps, sensors=sensors, reports=reports, pests=pests)


def record_trap(farm, pest, count, traps=1, days=1, source="manual", user_id=None):
    p = kb.PESTS[pest]
    traps = max(1, int(traps or 1))
    days = max(1, int(days or 1))
    if p["trap"] == "visual":                 # per-plant/leaf counts are averages, not per-trap rates
        value = count / traps
    else:
        value = count / traps / days * p["window_days"]
    above = value >= p["etl"]
    db.execute("INSERT INTO trap_readings(farm_id,user_id,pest,count,traps,days,value,above_etl,source) VALUES (?,?,?,?,?,?,?,?,?)",
               (farm["id"], user_id, pest, count, traps, days, round(value, 2), int(above), source))
    if above:
        detail = json.dumps({"value": round(value, 1), "etl": p["etl"], "unit": p["unit"]})
        add_alert(farm["user_id"], farm["id"], "trap", "high", pest, detail, dedupe_days=1)
        for sid in staff_ids():
            add_alert(sid, farm["id"], "trap", "high", pest, detail, dedupe_days=1)
    return value, above


@app.route("/farms/<int:fid>/trap", methods=["POST"])
@login_required()
def trap_add(fid):
    f = _farm_or_404(fid)
    pest = request.form["pest"]
    if pest not in kb.PESTS:
        abort(400)
    value, above = record_trap(f, pest, float(request.form["count"]), request.form.get("traps"),
                               request.form.get("days"), user_id=g.user["id"])
    p = kb.PESTS[pest]
    flash(T("trap.above" if above else "trap.below", value=round(value, 1), etl=p["etl"], unit=p["unit"]),
          "error" if above else "ok")
    return redirect(url_for("farm_view", fid=fid) + "#traps")


# ---------------------------------------------------------------- diagnosis
@app.route("/diagnose", methods=["GET", "POST"])
@login_required()
def diagnose():
    farms = db.query("SELECT * FROM farms WHERE user_id=?", (g.user["id"],)) if not is_staff() \
        else db.query("SELECT * FROM farms ORDER BY name")
    if request.method == "GET":
        return render_template("diagnose.html", farms=farms, model_ready=ml_service.available(),
                               preselect=request.args.get("farm", type=int))
    if not ml_service.available():
        flash(T("diag.no_model"), "error")
        return redirect(url_for("diagnose"))
    file = request.files.get("photo")
    if not file or not file.filename:
        flash(T("diag.no_photo"), "error")
        return redirect(url_for("diagnose"))
    try:
        img = Image.open(io.BytesIO(file.read()))
        img.load()
    except Exception:
        flash(T("diag.bad_image"), "error")
        return redirect(url_for("diagnose"))

    farm = None
    if request.form.get("farm_id"):
        farm = db.query("SELECT * FROM farms WHERE id=?", (int(request.form["farm_id"]),), one=True)
    crop = request.form.get("crop") or (farm["crop"] if farm else None)
    lat = farm["lat"] if farm else _float(request.form.get("lat"))
    lon = farm["lon"] if farm else _float(request.form.get("lon"))

    issues = ml_service.quality_check(img)
    pred = ml_service.predict(img, crop=crop if crop in kb.CROPS else None)

    name = f"{uuid.uuid4().hex[:16]}.jpg"
    save = img.convert("RGB")
    save.thumbnail((900, 900))
    save.save(os.path.join(UPLOAD_DIR, name), quality=88)

    d = kb.DISEASES.get(pred["label"], {})
    reasons = []
    if pred["conf"] < 0.6:
        reasons.append("low_confidence")
    if d.get("referral"):
        reasons.append("needs_lab")
    if d.get("notifiable"):
        reasons.append("notifiable")
    if pred["label"] == "Background_without_leaves":
        reasons.append("no_leaf")
    lab = nearest_lab(lat, lon, "lab") if reasons and "no_leaf" not in reasons else None

    rid = db.execute(
        "INSERT INTO reports(user_id,farm_id,image_path,crop,lat,lon,district,village,ai_label,ai_conf,ai_top3,"
        "model_version,quality_note,referred,referral_reason,lab_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (g.user["id"], farm["id"] if farm else None, "uploads/" + name, crop or d.get("crop"), lat, lon,
         farm["district"] if farm else request.form.get("district"), farm["village"] if farm else None,
         pred["label"], round(pred["conf"], 4), json.dumps(pred["top3"]), pred["version"],
         ",".join(issues + (["crop_mismatch:" + pred["crop_mismatch"]] if pred["crop_mismatch"] else [])),
         int(bool(lab)), ",".join(reasons), lab["id"] if lab else None))
    import numpy as np
    np.save(os.path.join(EMB_DIR, f"r{rid}.npy"), pred["feature"])

    if d.get("type") not in ("healthy", "background", None):
        days = 3 if d.get("spread") == "fast" else 7
        db.execute("INSERT INTO followups(report_id,due_date) VALUES (?,?)",
                   (rid, (dt.date.today() + dt.timedelta(days=days)).isoformat()))
        for sid in staff_ids():
            add_alert(sid, farm["id"] if farm else None, "newreport",
                      "high" if reasons else "moderate", pred["label"],
                      json.dumps({"report": rid, "conf": round(pred["conf"] * 100)}), dedupe_days=0)
    return redirect(url_for("report_view", rid=rid))


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@app.route("/report/<int:rid>")
@login_required()
def report_view(rid):
    r = db.query("SELECT r.*, u.name farmer_name, u.phone farmer_phone, o.name officer_name, f.name farm_name "
                 "FROM reports r LEFT JOIN users u ON u.id=r.user_id LEFT JOIN users o ON o.id=r.officer_id "
                 "LEFT JOIN farms f ON f.id=r.farm_id WHERE r.id=?", (rid,), one=True)
    if not r or (r["user_id"] != g.user["id"] and not is_staff()):
        abort(404)
    label = r["final_label"] or r["ai_label"]
    adv = kb.compose_advisory(label, g.lang, confidence=1.0 if r["final_label"] else r["ai_conf"])
    lab = db.query("SELECT * FROM labs WHERE id=?", (r["lab_id"],), one=True) if r["lab_id"] else None
    fu = db.query("SELECT * FROM followups WHERE report_id=? ORDER BY id", (rid,))
    farm_risk_item = None
    if r["farm_id"]:
        f = db.query("SELECT * FROM farms WHERE id=?", (r["farm_id"],), one=True)
        model = kb.DISEASES.get(label, {}).get("model")
        try:
            rr = compute_farm_risk(f, make_alerts=False)
            farm_risk_item = next((x for x in rr["risks"] if x["key"] == model), None)
        except Exception:
            pass
    return render_template("report.html", r=r, label=label, adv=adv, top3=json.loads(r["ai_top3"] or "[]"),
                           lab=lab, followups=fu, farm_risk=farm_risk_item,
                           speech=kb.advisory_speech(adv, g.lang) if adv else "",
                           issues=[i for i in (r["quality_note"] or "").split(",") if i])


@app.route("/followup/<int:fid>", methods=["POST"])
@login_required()
def followup_done(fid):
    fu = db.query("SELECT fu.*, r.user_id, r.farm_id, r.id rid, COALESCE(r.final_label, r.ai_label) label "
                  "FROM followups fu JOIN reports r ON r.id=fu.report_id WHERE fu.id=?", (fid,), one=True)
    if not fu or (fu["user_id"] != g.user["id"] and not is_staff()):
        abort(404)
    outcome = request.form.get("outcome")
    db.execute("UPDATE followups SET status='done', outcome=?, note=?, done_at=datetime('now','localtime') WHERE id=?",
               (outcome, request.form.get("note"), fid))
    if outcome == "worse":
        for sid in staff_ids():
            add_alert(sid, fu["farm_id"], "worse", "high", fu["label"], json.dumps({"report": fu["rid"]}), dedupe_days=0)
        db.execute("UPDATE reports SET referred=1, referral_reason=TRIM(IFNULL(referral_reason,'')||',not_improving',',') WHERE id=?",
                   (fu["rid"],))
    if outcome in ("same", "worse"):
        db.execute("INSERT INTO followups(report_id,due_date) VALUES (?,?)",
                   (fu["rid"], (dt.date.today() + dt.timedelta(days=5)).isoformat()))
    flash(T("followup.saved"), "ok")
    return redirect(url_for("report_view", rid=fu["rid"]))


@app.route("/reports")
@login_required()
def reports_list():
    if is_staff():
        rows = db.query("SELECT r.*, u.name farmer_name FROM reports r LEFT JOIN users u ON u.id=r.user_id "
                        "ORDER BY r.id DESC LIMIT 300")
    else:
        rows = db.query("SELECT r.*, NULL farmer_name FROM reports r WHERE user_id=? ORDER BY id DESC", (g.user["id"],))
    return render_template("reports.html", rows=rows)


# ---------------------------------------------------------------- advisories library
@app.route("/advisories")
def advisories():
    crop = request.args.get("crop")
    items = [(k, v) for k, v in kb.DISEASES.items() if v.get("type") not in ("healthy", "background")
             and (not crop or v.get("crop") == crop)]
    pests = [(k, v) for k, v in kb.PESTS.items() if not crop or crop in v["crops"]]
    return render_template("advisories.html", items=items, pests=pests, crop=crop)


@app.route("/advisories/<path:label>")
def advisory_view(label):
    adv = kb.compose_advisory(label, g.lang)
    if not adv:
        abort(404)
    pest = kb.PESTS.get(label)
    return render_template("advisory.html", adv=adv, pest=pest, speech=kb.advisory_speech(adv, g.lang))


# ---------------------------------------------------------------- officer
def _priority(r):
    p = 0
    reasons = r["referral_reason"] or ""
    if "notifiable" in reasons:
        p += 50
    if "not_improving" in reasons:
        p += 40
    if "needs_lab" in reasons:
        p += 20
    if "low_confidence" in reasons:
        p += 15
    d = kb.DISEASES.get(r["ai_label"], {})
    if d.get("spread") == "fast":
        p += 10
    return p


@app.route("/officer")
@login_required("officer", "admin")
def officer_home():
    status = request.args.get("status", "pending")
    rows = db.query("SELECT r.*, u.name farmer_name FROM reports r LEFT JOIN users u ON u.id=r.user_id "
                    "WHERE r.status=? ORDER BY r.id DESC LIMIT 200", (status,))
    rows = sorted(rows, key=lambda r: -_priority(r)) if status == "pending" else rows
    counts = {s: db.query("SELECT COUNT(*) c FROM reports WHERE status=?", (s,), one=True)["c"]
              for s in ("pending", "confirmed", "corrected", "rejected")}
    traps = db.query("SELECT t.*, f.name farm_name, f.district FROM trap_readings t JOIN farms f ON f.id=t.farm_id "
                     "WHERE t.above_etl=1 ORDER BY t.id DESC LIMIT 8")
    worse = db.query("SELECT fu.*, COALESCE(r.final_label, r.ai_label) label, r.id rid, u.name farmer_name FROM followups fu "
                     "JOIN reports r ON r.id=fu.report_id JOIN users u ON u.id=r.user_id "
                     "WHERE fu.outcome='worse' ORDER BY fu.done_at DESC LIMIT 8")
    return render_template("officer_home.html", rows=rows, counts=counts, status=status, traps=traps, worse=worse,
                           priority=_priority)


@app.route("/officer/review/<int:rid>", methods=["GET", "POST"])
@login_required("officer", "admin")
def officer_review(rid):
    r = db.query("SELECT r.*, u.name farmer_name, u.phone farmer_phone, f.name farm_name, f.variety, f.sowing_date "
                 "FROM reports r LEFT JOIN users u ON u.id=r.user_id LEFT JOIN farms f ON f.id=r.farm_id "
                 "WHERE r.id=?", (rid,), one=True)
    if not r:
        abort(404)
    if request.method == "POST":
        action = request.form["action"]
        final = request.form.get("final_label") or r["ai_label"]
        severity = request.form.get("severity") or "medium"
        refer = 1 if request.form.get("refer") else r["referred"]
        lab_id = r["lab_id"]
        if refer and not lab_id:
            lab = nearest_lab(r["lat"], r["lon"], "lab")
            lab_id = lab["id"] if lab else None
        if action == "confirm":
            status = "confirmed" if final == r["ai_label"] else "corrected"
        elif action == "reject":
            status, final = "rejected", None
        else:
            abort(400)
        chem = int(status in ("confirmed", "corrected") and severity in ("medium", "high")
                   and bool(kb.DISEASES.get(final, {}).get("chemical")))
        db.execute("UPDATE reports SET status=?, final_label=?, severity=?, officer_id=?, officer_note=?, referred=?, "
                   "lab_id=?, chemical_advised=?, validated_at=datetime('now','localtime') WHERE id=?",
                   (status, final, severity if final else None, g.user["id"], request.form.get("note"), refer,
                    lab_id, chem, rid))
        if final and status in ("confirmed", "corrected"):
            emb = os.path.join(EMB_DIR, f"r{rid}.npy")
            if os.path.exists(emb):
                import numpy as np
                ml_service.save_feedback(rid, np.load(emb), final)
                db.execute("UPDATE reports SET used_for_training=1 WHERE id=?", (rid,))
            if kb.DISEASES.get(final, {}).get("notifiable"):
                for sid in staff_ids():
                    add_alert(sid, r["farm_id"], "hotspot", "severe", final,
                              json.dumps({"cases": 1, "km": 0}), dedupe_days=0)
        if not final or kb.DISEASES.get(final, {}).get("type") in ("healthy", "background"):
            db.execute("UPDATE followups SET status='done', outcome='better', note='closed by officer' "
                       "WHERE report_id=? AND status='due'", (rid,))
        if r["user_id"]:
            add_alert(r["user_id"], r["farm_id"], "validation", "low", final or r["ai_label"],
                      json.dumps({"report": rid}), dedupe_days=0)
        hotspot_alerts()
        flash(T("review.saved"), "ok")
        nxt = db.query("SELECT id FROM reports WHERE status='pending' AND id<>? ORDER BY id DESC LIMIT 1", (rid,), one=True)
        return redirect(url_for("officer_review", rid=nxt["id"]) if nxt and request.form.get("next") else url_for("officer_home"))
    labels = sorted(kb.DISEASES.keys(), key=lambda l: kb.full_name(l, "en"))
    lab = db.query("SELECT * FROM labs WHERE id=?", (r["lab_id"],), one=True) if r["lab_id"] else None
    fu = db.query("SELECT * FROM followups WHERE report_id=? ORDER BY id", (rid,))
    adv = kb.compose_advisory(r["final_label"] or r["ai_label"], g.lang, confidence=r["ai_conf"] or 0)
    return render_template("review.html", r=r, labels=labels, top3=json.loads(r["ai_top3"] or "[]"), lab=lab,
                           followups=fu, adv=adv, issues=[i for i in (r["quality_note"] or "").split(",") if i])


@app.route("/officer/scan", methods=["POST"])
@login_required("officer", "admin")
def officer_scan():
    threading.Thread(target=surveillance_scan, daemon=True).start()
    flash(T("scan.started"), "ok")
    return redirect(request.referrer or url_for("officer_home"))


@app.route("/map")
@login_required()
def map_page():
    return render_template("map.html", staff=is_staff())


@app.route("/dashboard")
@login_required("officer", "admin")
def dashboard():
    return render_template("dashboard.html", metrics=_metrics())


def _metrics():
    p = os.path.join(ml_service.MODEL_DIR, "metrics.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


@app.route("/admin/model", methods=["GET", "POST"])
@login_required("officer", "admin")
def admin_model():
    if request.method == "POST":
        if not ml_service.available():
            flash(T("diag.no_model"), "error")
        elif ml_service.retrain(on_done=_record_version):
            flash(T("model.retrain_started"), "ok")
        return redirect(url_for("admin_model"))
    versions = db.query("SELECT * FROM model_versions ORDER BY version DESC")
    n_fb = len(ml_service.feedback_items())
    active = ml_service.active_version() if ml_service.available() else None
    return render_template("admin_model.html", metrics=_metrics(), versions=versions, n_feedback=n_fb,
                           status=ml_service.retrain_status, active=active)


def _record_version(res):
    conn = db.connect()
    if res["accepted"]:
        conn.execute("UPDATE model_versions SET active=0")
    conn.execute("INSERT INTO model_versions(version,test_accuracy,feedback_accuracy,n_feedback,active,notes) VALUES (?,?,?,?,?,?)",
                 (res["version"], res["test_accuracy"], res["feedback_accuracy"], res["n_feedback"], int(res["accepted"]),
                  "accepted" if res["accepted"] else "rejected: accuracy dropped"))
    conn.commit()
    conn.close()


@app.route("/media/<name>")
def media(name):
    """Report photos: new uploads (writable dir) first, then the bundled demo photos."""
    name = os.path.basename(name)
    for d in (UPLOAD_DIR, BUNDLED_UPLOADS):
        if os.path.exists(os.path.join(d, name)):
            return send_from_directory(d, name, max_age=86400)
    abort(404)


@app.route("/ml-plots/<name>")
@login_required()
def ml_plot(name):
    return send_from_directory(PLOT_DIR, name)


# ---------------------------------------------------------------- JSON APIs
@app.route("/api/hotspots")
@login_required()
def api_hotspots():
    spots = current_hotspots()
    for h in spots:
        h["name"] = label_name(h["label"])
    return jsonify(spots)


@app.route("/api/reports")
@login_required("officer", "admin")
def api_reports():
    days = request.args.get("days", 30, type=int)
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    rows = db.query("SELECT id, lat, lon, status, ai_conf, district, created_at, COALESCE(final_label, ai_label) label "
                    "FROM reports WHERE lat IS NOT NULL AND created_at>=?", (since,))
    return jsonify([dict(r) | {"name": label_name(r["label"]),
                               "type": kb.DISEASES.get(r["label"], {}).get("type")} for r in rows])


@app.route("/api/farms-risk")
@login_required("officer", "admin")
def api_farms_risk():
    out = []
    for f in db.query("SELECT * FROM farms"):
        try:
            r = compute_farm_risk(f, make_alerts=False)
            top = r["risks"][0] if r["risks"] else None
        except Exception:
            top = None
        out.append({"id": f["id"], "name": f["name"], "lat": f["lat"], "lon": f["lon"], "crop": kb.crop_name(f["crop"], g.lang),
                    "district": f["district"], "level": top["level"] if top else "low", "score": top["score"] if top else 0,
                    "risk": risk_name(top["key"]) if top else ""})
    return jsonify(out)


@app.route("/api/farm/<int:fid>/risk")
@login_required()
def api_farm_risk(fid):
    f = _farm_or_404(fid)
    r = compute_farm_risk(f, make_alerts=False)
    for x in r["risks"]:
        x["name"] = risk_name(x["key"])
    return jsonify(r)


@app.route("/api/stats")
@login_required("officer", "admin")
def api_stats():
    days = request.args.get("days", 90, type=int)
    since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [dict(r) for r in db.query("SELECT * FROM reports WHERE created_at>=?", (since,))]
    lab = lambda r: r["final_label"] or r["ai_label"]
    diseased = [r for r in rows if kb.DISEASES.get(lab(r), {}).get("type") not in ("healthy", "background")]
    validated = [r for r in rows if r["status"] in ("confirmed", "corrected")]
    agree = sum(1 for r in validated if r["status"] == "confirmed")
    hours = []
    for r in rows:
        if r["validated_at"]:
            try:
                a = dt.datetime.fromisoformat(r["created_at"])
                b = dt.datetime.fromisoformat(r["validated_at"])
                hours.append((b - a).total_seconds() / 3600)
            except ValueError:
                pass
    villages_all = {(f["district"], f["village"]) for f in db.query("SELECT district, village FROM farms")}
    villages_seen = {(r["district"], r["village"]) for r in rows if r["created_at"] >= (dt.datetime.now() - dt.timedelta(days=30)).strftime("%Y-%m-%d")}
    confirmed_disease = [r for r in validated if kb.DISEASES.get(lab(r), {}).get("chemical")]
    no_chem = sum(1 for r in confirmed_disease if not r["chemical_advised"])

    # weekly trend
    weeks = {}
    for r in rows:
        d = dt.date.fromisoformat(r["created_at"][:10])
        wk = (d - dt.timedelta(days=d.weekday())).isoformat()
        w = weeks.setdefault(wk, {"pending": 0, "confirmed": 0, "corrected": 0, "rejected": 0})
        w[r["status"]] = w.get(r["status"], 0) + 1
    by_disease, by_district, conf_bins = {}, {}, [0] * 10
    for r in diseased:
        by_disease[lab(r)] = by_disease.get(lab(r), 0) + 1
        by_district[r["district"] or "—"] = by_district.get(r["district"] or "—", 0) + 1
    for r in rows:
        if r["ai_conf"] is not None:
            conf_bins[min(9, int(r["ai_conf"] * 10))] += 1
    fu = {o: db.query("SELECT COUNT(*) c FROM followups WHERE outcome=?", (o,), one=True)["c"] for o in ("better", "same", "worse")}
    fu["due"] = db.query("SELECT COUNT(*) c FROM followups WHERE status='due'", one=True)["c"]
    traps = db.query("SELECT pest, COUNT(*) n, SUM(above_etl) above FROM trap_readings WHERE created_at>=? GROUP BY pest", (since,))
    top_d = sorted(by_disease.items(), key=lambda x: -x[1])[:10]
    return jsonify({
        "kpi": {
            "reports": len(rows), "diseased": len(diseased),
            "pending": sum(1 for r in rows if r["status"] == "pending"),
            "validated": len(validated),
            "agreement": round(100 * agree / len(validated), 1) if validated else None,
            "avg_response_h": round(sum(hours) / len(hours), 1) if hours else None,
            "referrals": sum(1 for r in rows if r["referred"]),
            "hotspots": len(current_hotspots()),
            "coverage": round(100 * len(villages_seen & villages_all) / len(villages_all), 1) if villages_all else None,
            "no_chem_pct": round(100 * no_chem / len(confirmed_disease), 1) if confirmed_disease else None,
            "farms": db.query("SELECT COUNT(*) c FROM farms", one=True)["c"],
        },
        "weekly": [{"week": k, **v} for k, v in sorted(weeks.items())],
        "top_diseases": [{"label": k, "name": label_name(k), "n": v} for k, v in top_d],
        "districts": [{"district": k, "n": v} for k, v in sorted(by_district.items(), key=lambda x: -x[1])],
        "confidence": conf_bins,
        "followups": fu,
        "traps": [{"pest": r["pest"], "name": label_name(r["pest"]), "n": r["n"], "above": r["above"] or 0} for r in traps],
    })


@app.route("/api/sensor", methods=["POST"])
def api_sensor():
    """
    IoT endpoint for field weather stations and smart pest traps.
    Header: X-Device-Key.  Body JSON:
      {"farm_id": 1, "device_id": "ws-01", "temp": 24.1, "rh": 93, "leaf_wetness": 70,
       "soil_moisture": 31, "trap": {"pest": "fall_armyworm", "count": 6, "traps": 1, "days": 1}}
    """
    if request.headers.get("X-Device-Key") != DEVICE_KEY:
        return jsonify({"error": "invalid device key"}), 401
    data = request.get_json(force=True, silent=True) or {}
    farm = db.query("SELECT * FROM farms WHERE id=?", (data.get("farm_id"),), one=True)
    if not farm:
        return jsonify({"error": "unknown farm_id"}), 404
    out = {"ok": True}
    if any(k in data for k in ("temp", "rh", "leaf_wetness", "soil_moisture")):
        db.execute("INSERT INTO sensor_readings(farm_id,device_id,temp,rh,leaf_wetness,soil_moisture) VALUES (?,?,?,?,?,?)",
                   (farm["id"], data.get("device_id"), data.get("temp"), data.get("rh"), data.get("leaf_wetness"),
                    data.get("soil_moisture")))
    trap = data.get("trap")
    if trap and trap.get("pest") in kb.PESTS:
        value, above = record_trap(farm, trap["pest"], float(trap.get("count", 0)), trap.get("traps"), trap.get("days"),
                                   source="sensor")
        out["trap"] = {"value": round(value, 2), "above_etl": above}
    return jsonify(out)


@app.errorhandler(403)
def e403(_):
    return render_template("error.html", code=403, msg=T("err.403")), 403


@app.errorhandler(404)
def e404(_):
    return render_template("error.html", code=404, msg=T("err.404")), 404


if __name__ == "__main__":
    if not IS_SERVERLESS:
        threading.Thread(target=_scheduler, daemon=True).start()
    if ml_service.available():   # warm up the model so the first diagnosis is fast
        threading.Thread(target=ml_service.load, daemon=True).start()
    print("KrishiRakshak running at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
