"""Module 4 detour helpers: the no-harm check and live-leg geometry."""
from __future__ import annotations

import math
from collections import defaultdict

import config
from utils import roads
from utils.geo import EARTH_RADIUS_KM, haversine

PROTECTED_STATUSES = ("in_transit", "delayed", "piggybacked")  # cargo the no-harm rule protects


def cargo_aboard_from(shipments) -> dict[str, list[dict]]:
    """`cargo_aboard` for the graph: shipments riding a vehicle, protected by the no-harm rule.

    Misplaced shipments are not protected (they are being rescued anyway).
    """
    aboard: dict[str, list[dict]] = defaultdict(list)
    for s in shipments:
        if s.current_vehicle_id and s.status in PROTECTED_STATUSES:
            aboard[s.current_vehicle_id].append({
                "shipment_id": s.id, "drop_hub": s.destination_hub_id,
                "deadline": s.deadline, "priority": s.priority})
    return dict(aboard)


def harmed(cargo: list[dict], planned: list[dict], detoured: list[dict]) -> list[dict]:
    """Cargo that reaches its drop hub by the deadline on `planned` but not on `detoured`.

    Cargo already late on the planned schedule is not harmed.
    """
    victims = []
    for c in cargo:
        before = next((s["arrive"] for s in planned if s["hub"] == c["drop_hub"]), None)
        after = next((s["arrive"] for s in detoured if s["hub"] == c["drop_hub"]), None)
        if before is not None and after is not None and before <= c["deadline"] < after:
            victims.append({"shipment_id": c["shipment_id"], "priority": c["priority"],
                            "late_hours": round((after - c["deadline"]).total_seconds() / 3600, 2)})
    return victims


def project(point, a, b) -> tuple[float, float]:
    """(km from point to segment a→b, fraction 0–1 along it of the nearest point)."""
    coslat = math.cos(math.radians((a[0] + b[0]) / 2))

    def xy(p):
        return math.radians(p[1]) * coslat * EARTH_RADIUS_KM, math.radians(p[0]) * EARTH_RADIUS_KM

    (px, py), (ax, ay), (bx, by) = xy(point), xy(a), xy(b)
    dx, dy = bx - ax, by - ay
    seg = dx * dx + dy * dy
    t = 0.0 if seg == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg))
    return math.hypot(px - ax - t * dx, py - ay - t * dy), t


def road_ahead(prev_id: str | None, next_hub, pos) -> tuple[list, float | None]:
    """(polyline from `pos` to `next_hub` along the current leg's road, OSRM km scale).

    The scale is None when the road is not cached (straight-segment fallback).
    """
    path = roads.road_path(prev_id, next_hub.id) if prev_id else None
    if not path:
        return [pos, (next_hub.lat, next_hub.lng)], None
    i = min(range(len(path) - 1), key=lambda k: project(pos, path[k], path[k + 1])[0])
    total = sum(haversine(*p, *q) for p, q in zip(path, path[1:]))
    scale = (roads.road_distance_km(prev_id, next_hub.id) or total) / max(total, 1e-9)
    return [pos] + path[i + 1:], scale


def km_along_to(ahead: list, scale: float | None, hub) -> float | None:
    """Road km from ahead[0] to `hub`, or None if the hub is not ahead within MAX_DETOUR_KM.

    A hub whose nearest point on the road ahead is the vehicle itself lies behind it.
    """
    pt = (hub.lat, hub.lng)
    off, t, j = min((*project(pt, p, q), k) for k, (p, q) in enumerate(zip(ahead, ahead[1:])))
    if off > config.MAX_DETOUR_KM or (j == 0 and t == 0.0):
        return None
    if scale is None:
        return haversine(*ahead[0], *pt) * config.ROAD_DISTANCE_FACTOR
    along = sum(haversine(*p, *q) for p, q in zip(ahead[:j + 1], ahead[1:j + 1]))
    along += t * haversine(*ahead[j], *ahead[j + 1])
    return along * scale + off * config.ROAD_DISTANCE_FACTOR
