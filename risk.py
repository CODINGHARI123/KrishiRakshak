"""
Weather-based disease & pest risk forecasting.

Weather: Open-Meteo forecast API (free, no key) – hourly temperature, relative
humidity, precipitation and wind for the past 3 days and next 7 days.

Each disease model turns daily weather into a 0–1 "favourability" score using
published infection rules (e.g. Hutton criteria for late blight, Mills table for
apple scab).  The farm-level risk then combines:

    weather favourability  x  crop-stage susceptibility  x  variety resistance
    x  soil drainage / irrigation factor  +  local outbreak history  (+ sensors)
"""
import datetime as dt
import json
import math
import threading
import time
import urllib.request
from collections import defaultdict

from kb import CROPS, PESTS

_CACHE = {}
_LOCK = threading.Lock()
CACHE_SECONDS = 3600

HUMID_MODELS = {"late_blight", "early_blight", "leaf_spot_humid", "bacterial", "black_rot",
                "gray_leaf_spot", "northern_leaf_blight", "apple_scab", "rust"}


# ---------------------------------------------------------------- weather
def fetch_weather(lat, lon):
    """Return {'days': [...], 'source': 'open-meteo'|'offline-sample'} with daily aggregates."""
    key = (round(lat, 2), round(lon, 2))
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    url = ("https://api.open-meteo.com/v1/forecast?latitude={:.4f}&longitude={:.4f}"
           "&hourly=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
           "&past_days=3&forecast_days=7&timezone=auto").format(lat, lon)
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read().decode())
        days = _aggregate(data["hourly"])
        out = {"days": days, "source": "open-meteo"}
    except Exception:
        out = {"days": _offline_sample(lat, lon), "source": "offline-sample"}
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def _aggregate(h):
    by_day = defaultdict(lambda: {"t": [], "rh": [], "p": [], "w": []})
    for i, ts in enumerate(h["time"]):
        d = by_day[ts[:10]]
        d["t"].append(h["temperature_2m"][i])
        d["rh"].append(h["relative_humidity_2m"][i])
        d["p"].append(h["precipitation"][i] or 0)
        d["w"].append(h["wind_speed_10m"][i] or 0)
    days = []
    for date in sorted(by_day):
        d = by_day[date]
        t = [x for x in d["t"] if x is not None]
        rh = [x for x in d["rh"] if x is not None]
        if not t or not rh:
            continue
        wet = sum(1 for i, x in enumerate(d["rh"]) if (x is not None and x >= 90) or d["p"][i] > 0.1)
        days.append({
            "date": date,
            "tmin": round(min(t), 1), "tmax": round(max(t), 1), "tmean": round(sum(t) / len(t), 1),
            "rh_mean": round(sum(rh) / len(rh)), "rh90_hours": sum(1 for x in rh if x >= 90),
            "wet_hours": wet, "rain": round(sum(d["p"]), 1), "wind_max": round(max(d["w"]), 1),
        })
    return days


def _offline_sample(lat, lon):
    """Deterministic, season-aware sample weather used only when the internet is unavailable."""
    today = dt.date.today()
    doy = today.timetuple().tm_yday
    monsoon = 160 <= doy <= 280
    base_t = 27 - (abs(lat) - 18) * 0.4 + 4 * math.sin((doy - 80) / 365 * 2 * math.pi)
    days = []
    for k in range(-3, 7):
        d = today + dt.timedelta(days=k)
        wobble = math.sin((d.toordinal() + lat * 7 + lon) * 0.9)
        rh = (84 if monsoon else 58) + 8 * wobble
        rain = max(0.0, (9 if monsoon else 0.5) * (wobble + 0.3))
        tmean = base_t + 1.5 * wobble
        days.append({
            "date": d.isoformat(), "tmin": round(tmean - 5, 1), "tmax": round(tmean + 5, 1),
            "tmean": round(tmean, 1), "rh_mean": round(rh), "rh90_hours": max(0, int((rh - 75) * 0.8)),
            "wet_hours": max(0, int((rh - 72) * 0.9 + rain)), "rain": round(rain, 1), "wind_max": 12.0,
        })
    return days


# ---------------------------------------------------------------- disease models
def _between(x, lo, hi):
    return lo <= x <= hi


def day_score(model, d):
    t, wet, rh90, rain = d["tmean"], d["wet_hours"], d["rh90_hours"], d["rain"]
    if model == "late_blight":          # Hutton criteria: Tmin >= 10°C and >= 6 h RH >= 90%
        if d["tmin"] >= 10 and rh90 >= 6 and t <= 26:
            return 1.0
        return 0.5 if d["tmin"] >= 8 and rh90 >= 3 and t <= 27 else 0.05
    if model == "early_blight":
        if _between(t, 20, 30) and wet >= 8:
            return 1.0
        return 0.55 if _between(t, 18, 32) and wet >= 4 else 0.1
    if model == "powdery_mildew":       # warm, humid air but dry leaves; heavy rain washes spores
        if _between(t, 16, 28) and 50 <= d["rh_mean"] <= 90 and rain < 2:
            return 1.0
        return 0.45 if _between(t, 12, 32) and rain < 8 else 0.1
    if model == "apple_scab":           # simplified Mills table: wet hours needed vs temperature
        need = 14 if t < 10 else 11 if t < 13 else 9 if t < 24 else 12
        if _between(t, 6, 26) and wet >= need:
            return 1.0
        return 0.5 if _between(t, 5, 27) and wet >= need * 0.6 else 0.05
    if model == "rust":
        if _between(t, 15, 25) and rh90 >= 6:
            return 1.0
        return 0.5 if _between(t, 12, 28) and rh90 >= 3 else 0.1
    if model == "bacterial":            # warm + splashing rain
        if _between(t, 24, 32) and rain >= 5:
            return 1.0
        return 0.55 if _between(t, 20, 34) and (rain >= 1 or rh90 >= 6) else 0.1
    if model == "black_rot":
        if _between(t, 20, 32) and wet >= 6:
            return 1.0
        return 0.5 if _between(t, 15, 34) and wet >= 3 else 0.05
    if model == "northern_leaf_blight":
        if _between(t, 18, 27) and wet >= 6:
            return 1.0
        return 0.5 if _between(t, 15, 30) and wet >= 3 else 0.05
    if model == "gray_leaf_spot":
        if _between(t, 22, 30) and rh90 >= 12:
            return 1.0
        return 0.5 if _between(t, 20, 32) and rh90 >= 6 else 0.05
    if model == "leaf_spot_humid":
        if _between(t, 20, 30) and wet >= 8:
            return 1.0
        return 0.5 if _between(t, 16, 32) and wet >= 4 else 0.1
    if model == "mites_hot_dry":
        if d["tmax"] >= 30 and d["rh_mean"] < 50 and rain < 1:
            return 1.0
        return 0.5 if d["tmax"] >= 28 and d["rh_mean"] < 62 and rain < 3 else 0.05
    if model == "vector_hot_dry":       # whitefly / psyllid vectors multiply in warm dry spells
        if _between(t, 26, 35) and d["rh_mean"] < 65 and rain < 2:
            return 1.0
        return 0.45 if _between(t, 22, 36) and rain < 5 else 0.1
    return 0.0


def pest_day_score(pest, d):
    w = PESTS[pest]["weather"]
    ok_t = _between(d["tmean"], w.get("tmin", 0), w.get("tmax", 50))
    ok_rh = d["rh_mean"] >= w.get("rh_min", 0) and d["rh_mean"] <= w.get("rh_max", 100)
    return 1.0 if ok_t and ok_rh else 0.5 if ok_t or ok_rh else 0.1


def weather_favourability(daily_scores, dates, today):
    """Peak 3-day rolling mean over the forecast window (today onward)."""
    future = [s for s, dte in zip(daily_scores, dates) if dte >= today]
    if not future:
        return 0.0, None
    best, best_i = 0.0, 0
    for i in range(len(future)):
        win = future[i:i + 3]
        m = sum(win) / len(win)
        if m > best:
            best, best_i = m, i
    start = [d for d in dates if d >= today][best_i]
    return best, start


# ---------------------------------------------------------------- farm factors
def crop_stage(farm):
    """Return (stage_key, susceptibility_factor, days_after_sowing)."""
    try:
        das = (dt.date.today() - dt.date.fromisoformat(farm["sowing_date"])).days
    except Exception:
        return "vegetative", 1.0, None
    dur = CROPS.get(farm["crop"], {}).get("duration", 120)
    f = das / dur
    if f < 0.15:
        return "seedling", 0.85, das
    if f < 0.45:
        return "vegetative", 1.0, das
    if f < 0.8:
        return "flowering", 1.15, das
    if f <= 1.1:
        return "maturity", 0.75, das
    return "harvested", 0.4, das


RESISTANCE_FACTOR = {"S": 1.0, "MR": 0.75, "R": 0.5}


def env_factor(model, farm):
    f = 1.0
    if model in HUMID_MODELS:
        f *= {"poor": 1.15, "moderate": 1.0, "good": 0.92}.get(farm["drainage"] or "moderate", 1.0)
        f *= {"sprinkler": 1.1, "flood": 1.03, "drip": 0.93, "rainfed": 1.0}.get(farm["irrigation"] or "flood", 1.0)
    if model in ("mites_hot_dry", "vector_hot_dry") and (farm["irrigation"] == "rainfed"):
        f *= 1.08
    return f


def level(score):
    return "severe" if score >= 75 else "high" if score >= 50 else "moderate" if score >= 25 else "low"


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def farm_risk(farm, nearby_cases=None, sensor=None, weather=None):
    """
    nearby_cases: {model_key: count of confirmed cases within 10 km in 21 days}
    sensor: latest sensor reading row (optional) – boosts wetness-driven models.
    """
    nearby_cases = nearby_cases or {}
    weather = weather or fetch_weather(farm["lat"], farm["lon"])
    days = weather["days"]
    dates = [d["date"] for d in days]
    today = dt.date.today().isoformat()
    stage, stage_f, das = crop_stage(farm)
    res_f = RESISTANCE_FACTOR.get(farm["resistance"] or "S", 1.0)

    sensor_boost = 0.0
    if sensor is not None:
        if (sensor["leaf_wetness"] or 0) >= 50 or (sensor["rh"] or 0) >= 90:
            sensor_boost = 0.1

    out = []
    for model in CROPS.get(farm["crop"], {}).get("diseases", []):
        scores = [day_score(model, d) for d in days]
        fav, peak = weather_favourability(scores, dates, today)
        if model in HUMID_MODELS:
            fav = min(1.0, fav + sensor_boost)
        hist = min(25, 6 * nearby_cases.get(model, 0))
        score = min(100, round(85 * fav * stage_f * res_f * env_factor(model, farm) + hist))
        out.append({
            "kind": "disease", "key": model, "score": score, "level": level(score),
            "weather": round(fav, 2), "history_cases": nearby_cases.get(model, 0), "peak_date": peak,
            "daily": [{"date": d, "s": round(s, 2)} for d, s in zip(dates, scores)],
        })
    for pest, p in PESTS.items():
        if farm["crop"] not in p["crops"]:
            continue
        scores = [pest_day_score(pest, d) for d in days]
        fav, peak = weather_favourability(scores, dates, today)
        hist = min(25, 6 * nearby_cases.get(pest, 0))
        score = min(100, round(75 * fav * stage_f + hist))
        out.append({"kind": "pest", "key": pest, "score": score, "level": level(score),
                    "weather": round(fav, 2), "history_cases": nearby_cases.get(pest, 0), "peak_date": peak,
                    "daily": [{"date": d, "s": round(s, 2)} for d, s in zip(dates, scores)]})
    out.sort(key=lambda r: -r["score"])
    return {"stage": stage, "das": das, "stage_factor": stage_f, "resistance_factor": res_f,
            "risks": out, "weather": weather}
