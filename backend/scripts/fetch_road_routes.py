"""Fetch road geometry between every pair of hubs from OSRM and cache it.

Run from backend/:  .venv/bin/python -m scripts.fetch_road_routes
Writes data/road_routes.json (committed, so the demo needs no internet at runtime).
Uses the public OSRM demo server by default (fair use: ~1 request/second).
"""
import itertools
import json
import os
import sys
import time

import httpx

from database.seed_data import HUBS
from utils.geo import haversine

OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "road_routes.json")
THIN_KM = 2.0  # keep one point every ~2 km (plus the exact endpoints)


def thin(coords: list[list[float]]) -> list[list[float]]:
    """coords are OSRM [lng, lat]; returns [lat, lng] rounded to 5 dp."""
    kept = [coords[0]]
    for lng, lat in coords[1:-1]:
        if haversine(kept[-1][1], kept[-1][0], lat, lng) >= THIN_KM:
            kept.append([lng, lat])
    kept.append(coords[-1])
    return [[round(lat, 5), round(lng, 5)] for lng, lat in kept]


def fetch(a, b, client) -> dict:
    url = f"{OSRM_URL}/route/v1/driving/{a[5]},{a[4]};{b[5]},{b[4]}"
    resp = client.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok":
        raise RuntimeError(f"{a[0]}→{b[0]}: {data.get('code')}")
    route = data["routes"][0]
    return {"km": round(route["distance"] / 1000, 1), "hours": round(route["duration"] / 3600, 2),
            "path": thin(route["geometry"]["coordinates"])}


def main() -> None:
    existing = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            existing = json.load(f).get("pairs", {})
    pairs = dict(existing)
    with httpx.Client() as client:
        for a, b in itertools.combinations(sorted(HUBS, key=lambda h: h[0]), 2):
            key = f"{a[0]}|{b[0]}"
            if key in pairs:
                continue
            for attempt in range(3):
                try:
                    pairs[key] = fetch(a, b, client)
                    print(f"{key}: {pairs[key]['km']} km, {len(pairs[key]['path'])} pts", file=sys.stderr)
                    break
                except (httpx.HTTPError, RuntimeError) as exc:
                    print(f"{key}: attempt {attempt + 1} failed: {exc}", file=sys.stderr)
                    time.sleep(3)
            time.sleep(1.1)
    with open(OUT, "w") as f:
        json.dump({"source": f"OSRM ({OSRM_URL}), © OpenStreetMap contributors",
                   "thin_km": THIN_KM, "pairs": pairs}, f, separators=(",", ":"))
    print(f"Wrote {len(pairs)} pairs to {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
