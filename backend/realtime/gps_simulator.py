"""GPS simulator: moves every vehicle and emits `vehicle:location` through the
same ingest path a real driver uses (validation, auth check, Redis, rooms).

Vehicles drive along real road geometry between hubs (OSRM, cached in
data/road_routes.json via utils.roads); a pair missing from the cache falls
back to a straight line.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import config
from utils import roads
from utils.geo import bearing, haversine, point_to_line_distance


def leg_polyline(hubs: dict, from_id: str | None, to_id: str) -> list[tuple[float, float]]:
    to = hubs[to_id]
    if from_id is None or from_id not in hubs:
        return [(to.lat, to.lng)]
    path = roads.road_path(from_id, to_id)
    if path:
        return path
    frm = hubs[from_id]
    return [(frm.lat, frm.lng), (to.lat, to.lng)]


class GpsSimulator:
    def __init__(self):
        self.arrived_at: dict[str, datetime] = {}
        # vehicle_id -> ((from_hub, to_hub), index of the segment it is on)
        self.cursor: dict[str, tuple[tuple, int]] = {}

    def reset(self):
        self.arrived_at.clear()
        self.cursor.clear()

    def _segment(self, vehicle_id: str, leg: tuple, line: list, pos) -> int:
        """Index of the road segment the vehicle is on.

        Continues from the remembered segment on the same leg (searching only
        forward, so a road that doubles back near itself can't pull the vehicle
        backwards); otherwise finds the closest segment of the leg.
        """
        if len(line) < 2:
            return -1
        known = self.cursor.get(vehicle_id)
        start = known[1] if known and known[0] == leg else 0
        candidates = range(start, min(start + 25, len(line) - 1)) if known and known[0] == leg \
            else range(len(line) - 1)
        return min(candidates, key=lambda j: point_to_line_distance(pos, line[j], line[j + 1]))

    def dwell_done(self, vehicle, now: datetime) -> bool:
        arrived = self.arrived_at.setdefault(vehicle.id, now)
        return now - arrived >= timedelta(minutes=config.HUB_DWELL_MINUTES)

    def next_position(self, vehicle, hubs: dict, minutes: float, now: datetime) -> dict | None:
        """Position after `minutes` of driving, or None if the vehicle should not move."""
        route = vehicle.planned_route or []
        idx = vehicle.current_stop_index or 0
        if vehicle.status == "completed" or idx >= len(route):
            return None
        if vehicle.status == "at_hub":
            if idx + 1 >= len(route) or not self.dwell_done(vehicle, now):
                return None
            target = idx + 1
        else:
            self.arrived_at.pop(vehicle.id, None)
            target = idx
        prev_id = route[target - 1] if target > 0 else None
        leg = (prev_id, route[target])
        line = leg_polyline(hubs, prev_id, route[target])
        pos = (vehicle.current_lat, vehicle.current_lng)
        seg = self._segment(vehicle.id, leg, line, pos)
        budget = vehicle.speed_kmh * minutes / 60
        lat, lng = pos
        heading = 0.0
        # Walk forward along the road, vertex by vertex, until the distance budget runs out.
        for j in range(seg + 1, len(line)):
            wp = line[j]
            d = haversine(lat, lng, *wp)
            if d > 1e-6:
                heading = bearing(lat, lng, *wp)
            if d >= budget:
                f = budget / d if d else 1.0
                lat, lng = lat + (wp[0] - lat) * f, lng + (wp[1] - lng) * f
                break
            lat, lng = wp
            budget -= d
            seg = j
        self.cursor[vehicle.id] = (leg, min(seg, max(len(line) - 2, 0)))
        return {"vehicle_id": vehicle.id, "lat": round(lat, 6), "lng": round(lng, 6),
                "speed": vehicle.speed_kmh, "heading": round(heading, 1),
                "timestamp": now.isoformat()}


def restart_reversed(vehicle) -> bool:
    """Demo only: a vehicle that finished its route turns around so the map stays alive."""
    route = vehicle.planned_route or []
    finished = vehicle.status == "completed" or (
        vehicle.status == "at_hub" and vehicle.current_stop_index >= len(route) - 1)
    if not finished or len(route) < 2:
        return False
    vehicle.planned_route = list(reversed(route))
    vehicle.current_stop_index = 0
    vehicle.status = "at_hub"
    return True


gps_simulator = GpsSimulator()
