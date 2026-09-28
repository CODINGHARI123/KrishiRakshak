"""
Simulates a field weather station + smart pheromone trap sending data to KrishiRakshak.

    python iot_simulator.py --farm 1 --pest helicoverpa --count 7

Uses the /api/sensor endpoint with the X-Device-Key header.
"""
import argparse
import json
import random
import urllib.request

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://localhost:5000/api/sensor")
p.add_argument("--key", default="demo-device-key")
p.add_argument("--farm", type=int, required=True)
p.add_argument("--pest", help="pest key from kb/pests.json, e.g. fall_armyworm")
p.add_argument("--count", type=float, default=0)
a = p.parse_args()

body = {"farm_id": a.farm, "device_id": "sim-01",
        "temp": round(random.uniform(18, 30), 1), "rh": round(random.uniform(60, 98)),
        "leaf_wetness": round(random.uniform(0, 90)), "soil_moisture": round(random.uniform(20, 40), 1)}
if a.pest:
    body["trap"] = {"pest": a.pest, "count": a.count, "traps": 1, "days": 1}

req = urllib.request.Request(a.url, data=json.dumps(body).encode(), method="POST",
                             headers={"Content-Type": "application/json", "X-Device-Key": a.key})
print("sent:", body)
print("response:", urllib.request.urlopen(req).read().decode())
