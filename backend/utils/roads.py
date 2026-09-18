"""Road geometry and distances between hubs, from the cached OSRM data.

data/road_routes.json is produced by scripts/fetch_road_routes.py. Pairs are
stored once as "A|B" (A < B); lookups in the B→A direction reverse the path.
Missing pairs return None so callers can fall back to straight-line estimates.
"""
import json
import os
from functools import lru_cache

import config
from utils.geo import haversine, interpolate

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "road_routes.json")


@lru_cache(maxsize=1)
def _pairs() -> dict:
    try:
        with open(DATA_FILE) as f:
            return json.load(f).get("pairs", {})
    except (OSError, ValueError):
        return {}


def _entry(a_id: str, b_id: str):
    if a_id == b_id:
        return None, False
    if a_id < b_id:
        return _pairs().get(f"{a_id}|{b_id}"), False
    return _pairs().get(f"{b_id}|{a_id}"), True


def road_path(a_id: str, b_id: str) -> list[tuple[float, float]] | None:
    """[(lat, lng), ...] along the road from hub a to hub b, or None if not cached."""
    entry, reverse = _entry(a_id, b_id)
    if entry is None:
        return None
    path = [tuple(p) for p in entry["path"]]
    return path[::-1] if reverse else path


def road_distance_km(a_id: str, b_id: str) -> float | None:
    entry, _ = _entry(a_id, b_id)
    return entry["km"] if entry else None


def paths_for(pairs: list[tuple[str, str]]) -> dict[str, list]:
    """{"A|B": [[lat, lng], ...]} in the requested direction, for pairs that are cached."""
    out = {}
    for a_id, b_id in pairs:
        path = road_path(a_id, b_id)
        if path is not None:
            out[f"{a_id}|{b_id}"] = [list(p) for p in path]
    return out


# ---- helpers with straight-line fallback ------------------------------------------
def _fallback_km(lat1, lng1, lat2, lng2) -> float:
    return haversine(lat1, lng1, lat2, lng2) * config.ROAD_DISTANCE_FACTOR


def hub_km(a, b) -> float:
    """Road km between two Hub objects (OSRM when cached, else great-circle × factor)."""
    km = road_distance_km(a.id, b.id)
    return km if km is not None else _fallback_km(a.lat, a.lng, b.lat, b.lng)


def _cumulative(path) -> list[float]:
    out = [0.0]
    for (la1, ln1), (la2, ln2) in zip(path, path[1:]):
        out.append(out[-1] + haversine(la1, ln1, la2, ln2))
    return out


def km_to_hub(prev_id: str | None, hub, lat: float, lng: float) -> float:
    """Road km still to drive from (lat, lng) to `hub` on the leg prev_id → hub.

    Uses the nearest vertex of the cached road path, scaled so the full path
    length matches the OSRM distance; falls back to great-circle × factor.
    """
    path = road_path(prev_id, hub.id) if prev_id else None
    if not path:
        return _fallback_km(lat, lng, hub.lat, hub.lng)
    cum = _cumulative(path)
    nearest = min(range(len(path)), key=lambda i: haversine(lat, lng, *path[i]))
    along = cum[-1] - cum[nearest] + haversine(lat, lng, *path[nearest])
    scale = (road_distance_km(prev_id, hub.id) or cum[-1]) / max(cum[-1], 1e-9)
    return along * scale


def point_along_path(path, fraction: float) -> tuple[float, float]:
    """(lat, lng) at `fraction` (0–1) of a polyline's length."""
    cum = _cumulative(path)
    target = max(0.0, min(1.0, fraction)) * cum[-1]
    for i in range(1, len(path)):
        if cum[i] >= target:
            seg = cum[i] - cum[i - 1]
            return interpolate(*path[i - 1], *path[i], (target - cum[i - 1]) / seg if seg else 1.0)
    return path[-1]


def hub_polyline(hubs: dict, hub_ids: list[str]) -> list[tuple[float, float]]:
    """Road polyline through a sequence of hubs (straight segments where not cached)."""
    points: list[tuple[float, float]] = []
    for a_id, b_id in zip(hub_ids, hub_ids[1:]):
        seg = road_path(a_id, b_id) or [(hubs[a_id].lat, hubs[a_id].lng),
                                        (hubs[b_id].lat, hubs[b_id].lng)]
        points.extend(seg if not points else seg[1:])
    return points
