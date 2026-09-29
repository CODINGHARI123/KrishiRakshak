"""
Create demo data for KrishiRakshak (run after ml/train.py):

    python seed.py            # wipes and recreates krishirakshak.db

* Demo users (see README.md for logins), extension labs, ~70 farms across
  Maharashtra, Andhra Pradesh and Telangana.
* ~450 field reports over the last 90 days.  Each report uses a REAL PlantVillage
  image from the validation split and the REAL model prediction for it, so the
  dashboard's AI-vs-expert agreement reflects the actual model.  Outbreak clusters
  are simulated (e.g. tomato late blight around Narayangaon) so that hotspot
  detection has something to find.
* Weekly pest-trap readings and a day of IoT sensor readings.
All farmer names, farms and reports are SYNTHETIC demo data.
"""
import datetime as dt
import json
import os
import random
import shutil

import numpy as np
from PIL import Image
from werkzeug.security import generate_password_hash

import db
import kb

random.seed(7)
np.random.seed(7)
BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE, "static", "uploads")
EMB = os.path.join(BASE, "ml", "embeddings")
FEEDBACK = os.path.join(BASE, "ml", "feedback")
MODEL_DIR = os.path.join(BASE, "ml", "model")
NOW = dt.datetime.now()

# district -> (lat, lon, [(village, lat, lon, [crops])])
REGIONS = {
    "Pune": [("Narayangaon", 19.118, 73.972, ["tomato", "potato"]), ("Manchar", 19.004, 73.944, ["potato", "tomato"]),
             ("Junnar", 19.206, 73.876, ["tomato", "corn"])],
    "Nashik": [("Pimpalgaon Baswant", 20.168, 73.988, ["grape", "tomato"]), ("Niphad", 20.080, 74.110, ["grape"]),
               ("Dindori", 20.203, 73.832, ["grape", "tomato"])],
    "Nagpur": [("Kalmeshwar", 21.232, 78.919, ["orange", "cotton"]), ("Katol", 21.271, 78.586, ["orange"]),
               ("Saoner", 21.386, 78.918, ["cotton", "soybean"])],
    "Chh. Sambhajinagar": [("Paithan", 19.476, 75.385, ["cotton", "corn"]), ("Vaijapur", 19.925, 74.728, ["corn", "cotton"])],
    "Kolhapur": [("Kagal", 16.577, 74.315, ["soybean", "corn"]), ("Hatkanangale", 16.740, 74.447, ["corn", "soybean"])],
    "Satara": [("Mahabaleshwar", 17.925, 73.658, ["strawberry"]), ("Wai", 17.953, 73.891, ["potato", "strawberry"])],
    "Ahmednagar": [("Sangamner", 19.567, 74.211, ["tomato", "corn"]), ("Rahuri", 19.393, 74.648, ["tomato", "brinjal"])],
    "Jalgaon": [("Chopda", 21.246, 75.293, ["cotton"]), ("Yawal", 21.168, 75.698, ["cotton", "corn"])],
    "Amravati": [("Warud", 21.472, 78.264, ["orange", "cotton"]), ("Morshi", 21.338, 78.013, ["orange", "soybean"])],
    "Guntur": [("Tenali", 16.243, 80.640, ["pepper", "cotton"]), ("Mangalagiri", 16.430, 80.568, ["pepper", "corn"])],
    "Warangal": [("Narsampet", 17.928, 79.894, ["rice", "cotton"]), ("Parkal", 18.203, 79.702, ["rice", "cotton"])],
    "Krishnagiri": [("Hosur", 12.740, 77.825, ["tomato", "corn"]), ("Rayakottai", 12.515, 78.030, ["tomato", "brinjal"])],
    "Coimbatore": [("Pollachi", 10.658, 77.009, ["corn", "cotton"]), ("Thondamuthur", 10.990, 76.842, ["tomato", "corn"])],
    "Kolar": [("Srinivaspur", 13.338, 78.213, ["tomato", "potato"]), ("Mulbagal", 13.165, 78.393, ["tomato", "corn"])],
    "Chikkaballapur": [("Chintamani", 13.400, 78.058, ["grape", "tomato"]), ("Sidlaghatta", 13.388, 77.862, ["grape", "corn"])],
    "Himachal (Shimla)": [("Kotkhai", 31.118, 77.536, ["apple", "cherry"]), ("Theog", 31.121, 77.358, ["apple", "peach"])],
}
NAMES = {
    "hi": (["Ramesh", "Suresh", "Sunita", "Anil", "Kavita", "Vijay", "Prakash", "Meena", "Sanjay", "Asha", "Ganesh", "Rekha", "Nitin", "Savita"],
           ["Patil", "Jadhav", "Pawar", "Shinde", "More", "Deshmukh", "Kale", "Thakur", "Wagh", "Gaikwad"]),
    "mr": (["Ramesh", "Suresh", "Sunita", "Anil", "Kavita", "Vijay", "Prakash", "Meena", "Sanjay", "Asha", "Ganesh", "Rekha", "Nitin", "Savita"],
           ["Patil", "Jadhav", "Pawar", "Shinde", "More", "Deshmukh", "Kale", "Wagh", "Gaikwad", "Kulkarni"]),
    "te": (["Venkat", "Padma", "Ravi", "Srinivas", "Lakshmi", "Balu", "Anjali", "Naresh"], ["Reddy", "Rao", "Naidu", "Chowdary", "Varma"]),
    "ta": (["Murugan", "Selvi", "Karthik", "Kavitha", "Senthil", "Meenakshi", "Arumugam", "Priya"], ["Pillai", "Gounder", "Raj", "Kumar", "Subramanian"]),
    "kn": (["Manjunath", "Lakshmamma", "Basavaraj", "Shobha", "Nagaraj", "Gowramma", "Siddappa", "Rekha"], ["Gowda", "Shetty", "Hegde", "Naik", "Patil"]),
}
LANG_OF = {"Pune": "mr", "Nashik": "mr", "Nagpur": "mr", "Chh. Sambhajinagar": "mr", "Kolhapur": "mr",
           "Satara": "mr", "Ahmednagar": "mr", "Jalgaon": "mr", "Amravati": "mr", "Guntur": "te", "Warangal": "te", "Krishnagiri": "ta", "Coimbatore": "ta", "Kolar": "kn", "Chikkaballapur": "kn"}
# Outbreak scenarios: (label, village, n_cases, days_back_window)
OUTBREAKS = [
    ("Tomato___Late_blight", "Narayangaon", 22, 20),
    ("Potato___Late_blight", "Manchar", 9, 14),
    ("Grape___Black_rot", "Pimpalgaon Baswant", 14, 25),
    ("Orange___Haunglongbing_(Citrus_greening)", "Kalmeshwar", 9, 40),
    ("Tomato___Tomato_Yellow_Leaf_Curl_Virus", "Sangamner", 12, 30),
    ("Corn___Common_rust", "Kagal", 11, 28),
    ("Strawberry___Leaf_scorch", "Mahabaleshwar", 8, 35),
    ("Pepper,_bell___Bacterial_spot", "Tenali", 9, 30),
    ("Apple___Apple_scab", "Kotkhai", 10, 45),
    ("Tomato___Early_blight", "Srinivaspur", 9, 25),
    ("Corn___Northern_Leaf_Blight", "Pollachi", 8, 30),
]
FIRST = ["Murugan", "Selvi", "Manjunath", "Lakshmamma", "Ramesh", "Suresh", "Sunita", "Anil", "Kavita", "Vijay", "Lakshmi", "Prakash", "Meena", "Sanjay", "Asha",
         "Ganesh", "Rekha", "Mahesh", "Savita", "Venkat", "Padma", "Ravi", "Shobha", "Nitin", "Usha", "Srinivas", "Jyoti", "Balu"]
LAST = ["Gowda", "Kumar", "Pillai", "Patil", "Jadhav", "Pawar", "Shinde", "More", "Deshmukh", "Kale", "Reddy", "Rao", "Naidu", "Thakur", "Wagh", "Gaikwad"]
VARIETIES = {"tomato": ["Arka Rakshak", "Abhinav", "Local"], "potato": ["Kufri Jyoti", "Kufri Pukhraj"],
             "grape": ["Thompson Seedless", "Sharad Seedless"], "orange": ["Nagpur Santra"], "cotton": ["Bt hybrid", "Desi"],
             "corn": ["Hybrid 900M", "Local"], "soybean": ["JS 335", "MACS 1407"], "strawberry": ["Winter Dawn", "Sweet Charlie"],
             "pepper": ["Indra", "California Wonder"], "rice": ["BPT 5204", "MTU 1010"], "brinjal": ["Manjari Gota", "Local"], "apple": ["Royal Delicious", "Gala"], "cherry": ["Stella"], "peach": ["Florida Prince"]}
RES = {"Arka Rakshak": "R", "Kufri Pukhraj": "MR", "MACS 1407": "MR", "Sharad Seedless": "MR"}


def ts(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


def jitter(lat, lon, km):
    r = km / 111.0
    return lat + random.uniform(-r, r), lon + random.uniform(-r, r) / np.cos(np.radians(lat))


def main():
    if os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
    for d in (UPLOAD, EMB, FEEDBACK):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    for f in os.listdir(MODEL_DIR):
        if f.startswith("head_v") and f != "head_v1.keras" or f == "active.json":
            os.remove(os.path.join(MODEL_DIR, f))
    db.init_db()
    conn = db.connect()
    cur = conn.cursor()

    def ins(sql, args):
        cur.execute(sql, args)
        return cur.lastrowid

    # ---------------- users
    pw = lambda p: generate_password_hash(p)
    admin = ins("INSERT INTO users(username,email,password_hash,role,name,district,lang) VALUES (?,?,?,?,?,?,?)",
                ("admin", "admin@example.com", pw("admin123"), "admin", "District Agriculture Officer", "Pune", "en"))
    officer = ins("INSERT INTO users(username,email,password_hash,role,name,phone,district,lang) VALUES (?,?,?,?,?,?,?,?)",
                  ("officer", "officer@example.com", pw("officer123"), "officer", "A. Kulkarni (Extension Officer)", "90000 00001", "Pune", "en"))
    officer2 = ins("INSERT INTO users(username,email,password_hash,role,name,phone,district,lang) VALUES (?,?,?,?,?,?,?,?)",
                   ("officer2", "officer2@example.com", pw("officer123"), "officer", "K. Reddy (Extension Officer)", "90000 00002", "Guntur", "te"))
    demo = ins("INSERT INTO users(username,email,password_hash,role,name,phone,district,lang) VALUES (?,?,?,?,?,?,?,?)",
               ("farmer", "farmer@example.com", pw("farmer123"), "farmer", "Ramesh Patil", "90000 11111", "Pune", "en"))

    # ---------------- labs
    for dist, villages in REGIONS.items():
        v = villages[0]
        lat, lon = jitter(v[1], v[2], 12)
        ins("INSERT INTO labs(name,kind,district,lat,lon,contact) VALUES (?,?,?,?,?,?)",
            (f"District Plant Health Clinic, {dist} (demo)", "lab", dist, lat, lon, "Demo lab – not a real contact"))
        lat, lon = jitter(v[1], v[2], 15)
        ins("INSERT INTO labs(name,kind,district,lat,lon,contact) VALUES (?,?,?,?,?,?)",
            (f"Krishi Vigyan Kendra, {dist} (demo)", "kvk", dist, lat, lon, "Demo – not a real contact"))

    # ---------------- farms
    farms = []   # dicts
    village_info = {}
    for dist, villages in REGIONS.items():
        for vname, vlat, vlon, crops in villages:
            village_info[vname] = (dist, vlat, vlon, crops)
            for _ in range(3):
                fl, ll = NAMES[LANG_OF.get(dist, "hi")]
                name = f"{random.choice(fl)} {random.choice(ll)}"
                uname = f"f{len(farms) + 1:03d}"
                uid = ins("INSERT INTO users(username,email,password_hash,role,name,district,lang) VALUES (?,?,?,?,?,?,?)",
                          (uname, f"{uname}@example.com", pw(os.urandom(8).hex()), "farmer", name, dist,
                           LANG_OF.get(dist, "hi")))
                crop = random.choice(crops)
                farms.append(_farm(ins, uid, f"{name.split()[0]}'s {kb.CROPS[crop]['en']} plot", vname, dist, vlat, vlon, crop))

    # demo farmer: two farms inside the Narayangaon/Manchar outbreak zone
    demo_farms = [
        _farm(ins, demo, "Tomato plot – river side", "Narayangaon", "Pune", 19.121, 73.978, "tomato",
              variety="Abhinav", resistance="S", sow_days=55, drainage="poor", irrigation="sprinkler"),
        _farm(ins, demo, "Potato field – upper", "Manchar", "Pune", 19.010, 73.950, "potato",
              variety="Kufri Jyoti", resistance="S", sow_days=40, drainage="moderate", irrigation="flood"),
    ]
    others = list(farms)
    farms.extend(demo_farms)
    village_info["Narayangaon"] = ("Pune", 19.118, 73.972, ["tomato", "potato"])

    # ---------------- model data (validation split images + real predictions)
    import tensorflow as tf
    data = np.load(os.path.join(BASE, "ml", "features.npz"), allow_pickle=True)
    X, y, paths, val = data["X"], data["y"], data["paths"], data["val"]
    labels = json.load(open(os.path.join(MODEL_DIR, "labels.json")))
    head = tf.keras.models.load_model(os.path.join(MODEL_DIR, "head_v1.keras"), compile=False)
    probs_all = head.predict(X[val], verbose=0)
    by_label = {}
    for k, i in enumerate(val):
        by_label.setdefault(labels[y[i]], []).append((i, probs_all[k]))
    for v in by_label.values():
        random.shuffle(v)
    used = {}

    def take(label):
        lst = by_label[label]
        k = used.get(label, 0)
        used[label] = k + 1
        return lst[k % len(lst)]

    def masked(prob, crop):
        allowed = [j for j, l in enumerate(labels) if kb.DISEASES.get(l, {}).get("crop") == crop or l == "Background_without_leaves"]
        p = np.zeros_like(prob)
        p[allowed] = prob[allowed]
        return p / p.sum() if p.sum() > 0 else prob

    reports = []

    def add_report(farm, true_label, created):
        i, prob = take(true_label)
        p = masked(prob, farm["crop"])
        order = np.argsort(p)[::-1][:3]
        ai, conf = labels[order[0]], float(p[order[0]])
        img = Image.open(str(paths[i])).convert("RGB")
        fname = f"seed_{len(reports) + 1:04d}.jpg"
        img.save(os.path.join(UPLOAD, fname), quality=85)
        lat, lon = jitter(farm["lat"], farm["lon"], 1.0)
        d = kb.DISEASES.get(ai, {})
        reasons = []
        if conf < 0.6:
            reasons.append("low_confidence")
        if d.get("referral"):
            reasons.append("needs_lab")
        if d.get("notifiable"):
            reasons.append("notifiable")
        age_h = (NOW - created).total_seconds() / 3600
        status, final, sev, validated, officer_id, chem = "pending", None, None, None, None, 0
        if age_h > 30 or random.random() < 0.35:
            r = random.random()
            officer_id = officer2 if farm["district"] in ("Guntur", "Warangal") else officer
            if r < 0.03:
                status = "rejected"
            else:
                final = true_label
                status = "confirmed" if ai == true_label else "corrected"
                sev = random.choices(["low", "medium", "high"], [0.35, 0.45, 0.2])[0]
                if kb.DISEASES.get(final, {}).get("type") == "healthy":
                    sev = None
                chem = int(sev in ("medium", "high") and bool(kb.DISEASES.get(final, {}).get("chemical")))
            validated = created + dt.timedelta(hours=random.uniform(1.5, min(40, max(2, age_h - 0.5))))
        lab_id = None
        if reasons:
            lab = conn.execute("SELECT id FROM labs WHERE district=? AND kind='lab'", (farm["district"],)).fetchone()
            lab_id = lab["id"] if lab else None
        rid = ins("INSERT INTO reports(user_id,farm_id,image_path,crop,lat,lon,district,village,ai_label,ai_conf,ai_top3,model_version,"
                  "status,final_label,severity,officer_id,referred,referral_reason,lab_id,chemical_advised,used_for_training,source,"
                  "created_at,validated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (farm["user_id"], farm["id"], "uploads/" + fname, farm["crop"], lat, lon, farm["district"], farm["village"],
                   ai, round(conf, 4), json.dumps([{"label": labels[j], "conf": round(float(p[j]), 4)} for j in order]), 1,
                   status, final, sev, officer_id, int(bool(lab_id)), ",".join(reasons), lab_id, chem,
                   int(status in ("confirmed", "corrected")), "seed", ts(created), ts(validated) if validated else None))
        np.save(os.path.join(EMB, f"r{rid}.npy"), X[i])
        if status in ("confirmed", "corrected"):
            np.save(os.path.join(FEEDBACK, f"r{rid}.npy"), X[i])
            json.dump({"label": final}, open(os.path.join(FEEDBACK, f"r{rid}.json"), "w"))
        dd = kb.DISEASES.get(ai, {})
        if dd.get("type") not in ("healthy", "background", None):
            due = created.date() + dt.timedelta(days=3 if dd.get("spread") == "fast" else 7)
            healthy_final = final and kb.DISEASES.get(final, {}).get("type") == "healthy"
            if healthy_final or status == "rejected":
                pass
            elif due <= NOW.date() - dt.timedelta(days=2) or (due <= NOW.date() and status in ("confirmed", "corrected")):
                outcome = random.choices(["better", "same", "worse"], [0.62, 0.25, 0.13])[0]
                ins("INSERT INTO followups(report_id,due_date,status,outcome,done_at) VALUES (?,?,?,?,?)",
                    (rid, due.isoformat(), "done", outcome, ts(dt.datetime.combine(due, dt.time(10)))))
                if outcome in ("same", "worse") and due + dt.timedelta(days=5) > NOW.date() - dt.timedelta(days=2):
                    ins("INSERT INTO followups(report_id,due_date) VALUES (?,?)", (rid, (due + dt.timedelta(days=5)).isoformat()))
            else:
                ins("INSERT INTO followups(report_id,due_date) VALUES (?,?)", (rid, due.isoformat()))
        reports.append(rid)

    # outbreak clusters
    for label, village, n, window in OUTBREAKS:
        cand = [f for f in others if f["village"] == village and f["crop"] == kb.DISEASES[label]["crop"]]
        if not cand:
            dist, vlat, vlon, _ = village_info[village]
            cand = [_farm(ins, random.choice([f["user_id"] for f in others if f["village"] == village]),
                          f"{kb.CROPS[kb.DISEASES[label]['crop']]['en']} plot", village, dist, vlat, vlon, kb.DISEASES[label]["crop"])]
            farms.extend(cand)
        for k in range(n):
            # later cases are more frequent -> growing outbreak
            back = window * (1 - random.random() ** 0.6)
            add_report(random.choice(cand), label, NOW - dt.timedelta(days=back, hours=random.uniform(0, 10)))

    # sporadic background reports (other diseases + healthy)
    imageable = [f for f in farms if kb.labels_for_crop(f["crop"]) and f not in demo_farms]
    for _ in range(300):
        f = random.choice(imageable)
        options = kb.labels_for_crop(f["crop"])
        weights = [0.35 if kb.DISEASES[l]["type"] == "healthy" else 1.0 for l in options]
        label = random.choices(options, weights)[0]
        if label not in by_label:
            continue
        add_report(f, label, NOW - dt.timedelta(days=random.uniform(0, 90), hours=random.uniform(0, 12)))

    # demo farmer: a few personal reports
    add_report(demo_farms[0], "Tomato___Late_blight", NOW - dt.timedelta(days=9))
    add_report(demo_farms[0], "Tomato___Early_blight", NOW - dt.timedelta(days=30))
    add_report(demo_farms[1], "Potato___healthy", NOW - dt.timedelta(days=12))
    add_report(demo_farms[0], "Tomato___Late_blight", NOW - dt.timedelta(hours=5))

    # ---------------- pest traps (weekly, 8 weeks)
    for f in farms:
        pests = [k for k, p in kb.PESTS.items() if f["crop"] in p["crops"]]
        for pest in pests:
            p = kb.PESTS[pest]
            base = p["etl"] * random.uniform(0.2, 0.7)
            for w in range(8, 0, -1):
                when = NOW - dt.timedelta(days=7 * w - random.uniform(0, 2))
                surge = 1 + (8 - w) * random.uniform(0, 0.18)
                if p["trap"] == "visual" or p["trap"] == "yellow_sticky":
                    value = max(0, np.random.normal(base * surge, base * 0.3))
                    count, traps, days = round(value * 5, 1), 5, 1
                else:
                    days = 7 if p["window_days"] == 1 else 7
                    value = max(0, np.random.normal(base * surge, base * 0.3))
                    count = round(value * days / p["window_days"])
                    traps = 1
                    value = count / traps / days * p["window_days"]
                ins("INSERT INTO trap_readings(farm_id,user_id,pest,count,traps,days,value,above_etl,source,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f["id"], f["user_id"], pest, count, traps, days, round(value, 2), int(value >= p["etl"]),
                     random.choice(["manual", "manual", "sensor"]), ts(when)))

    # ---------------- IoT sensor readings for the demo tomato farm (last 24 h, humid night)
    for h in range(24, 0, -1):
        when = NOW - dt.timedelta(hours=h)
        night = when.hour < 8 or when.hour > 19
        ins("INSERT INTO sensor_readings(farm_id,device_id,temp,rh,leaf_wetness,soil_moisture,created_at) VALUES (?,?,?,?,?,?,?)",
            (demo_farms[0]["id"], "ws-demo-01", round(random.uniform(17, 20) if night else random.uniform(22, 27), 1),
             round(random.uniform(90, 97) if night else random.uniform(70, 85)), round(random.uniform(60, 90) if night else random.uniform(5, 30)),
             round(random.uniform(30, 38), 1), ts(when)))

    metrics = json.load(open(os.path.join(MODEL_DIR, "metrics.json")))
    ins("INSERT INTO model_versions(version,test_accuracy,n_feedback,active,notes,created_at) VALUES (?,?,?,?,?,?)",
        (1, metrics["test_accuracy"], 0, 1, "initial PlantVillage model", metrics["trained_at"] + ":00"))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    print(f"seeded {len(farms)} farms, {n} reports, {len(os.listdir(FEEDBACK)) // 2} feedback images")
    conn.close()


def _farm(ins, uid, name, village, dist, vlat, vlon, crop, variety=None, resistance=None, sow_days=None,
          drainage=None, irrigation=None):
    lat, lon = jitter(vlat, vlon, 3.5)
    variety = variety or random.choice(VARIETIES.get(crop, ["Local"]))
    resistance = resistance or RES.get(variety, "S")
    dur = kb.CROPS[crop]["duration"]
    sow = (dt.date.today() - dt.timedelta(days=sow_days if sow_days is not None else random.randint(15, int(dur * 0.9)))).isoformat()
    drainage = drainage or random.choice(["good", "moderate", "moderate", "poor"])
    irrigation = irrigation or random.choice(["drip", "flood", "sprinkler", "rainfed"])
    fid = ins("INSERT INTO farms(user_id,name,village,district,lat,lon,crop,variety,resistance,sowing_date,area_acres,soil_type,drainage,irrigation) "
              "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (uid, name, village, dist, lat, lon, crop, variety, resistance, sow, round(random.uniform(0.5, 5), 1),
               random.choice(["black", "red", "alluvial", "loamy"]), drainage, irrigation))
    return {"id": fid, "user_id": uid, "village": village, "district": dist, "lat": lat, "lon": lon, "crop": crop}


if __name__ == "__main__":
    main()
