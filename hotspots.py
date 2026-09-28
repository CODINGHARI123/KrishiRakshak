"""
Geospatial hotspot detection.

Confirmed (and high-confidence pending) reports from the last N days are grouped
per disease/pest and clustered with DBSCAN using the haversine metric
(eps = 5 km, min 3 cases).  Each cluster becomes a hotspot with centroid,
radius, case count and 7-day growth.
"""
import datetime as dt

import numpy as np
from sklearn.cluster import DBSCAN

from kb import DISEASES
from risk import haversine_km

EARTH_KM = 6371.0


def find_hotspots(rows, eps_km=5.0, min_cases=3):
    """rows: iterable of dicts with lat, lon, label, created_at."""
    groups = {}
    for r in rows:
        lab = r["label"]
        d = DISEASES.get(lab)
        if d and d.get("type") in ("healthy", "background"):
            continue
        groups.setdefault(lab, []).append(r)

    week_ago = (dt.datetime.now() - dt.timedelta(days=7)).strftime("%Y-%m-%d")
    hotspots = []
    for lab, items in groups.items():
        if len(items) < min_cases:
            continue
        coords = np.radians([[i["lat"], i["lon"]] for i in items])
        cl = DBSCAN(eps=eps_km / EARTH_KM, min_samples=min_cases, metric="haversine").fit(coords)
        for c in set(cl.labels_) - {-1}:
            members = [items[k] for k in range(len(items)) if cl.labels_[k] == c]
            lat = float(np.mean([m["lat"] for m in members]))
            lon = float(np.mean([m["lon"] for m in members]))
            radius = max(1.0, max(haversine_km(lat, lon, m["lat"], m["lon"]) for m in members))
            recent = sum(1 for m in members if m["created_at"][:10] >= week_ago)
            n = len(members)
            hotspots.append({
                "label": lab, "lat": round(lat, 5), "lon": round(lon, 5),
                "radius_km": round(radius + 1, 1), "cases": n, "last7": recent,
                "growth": round(recent / n, 2),
                "severity": "severe" if n >= 12 or recent >= 6 else "high" if n >= 6 else "moderate",
                "districts": sorted({m.get("district") or "" for m in members} - {""}),
            })
    hotspots.sort(key=lambda h: -h["cases"])
    return hotspots
