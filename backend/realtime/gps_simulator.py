"""GPS simulator: moves every vehicle and emits `vehicle:location` through the
same ingest path a real driver uses (validation, auth check, Redis, rooms).

TRUCK-101..104 follow the Hyderabad → Warangal → Vijayawada corridor through
intermediate town waypoints (Bhongir, Jangaon, Khammam). These are town-centre
coordinates, not road-snapped geometry. Other vehicles travel hub to hub in
straight lines.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import config
from utils.geo import bearing, haversine, point_to_line_distance

CORRIDOR_WAYPOINTS = {
    ("HUB-HYD-01", "HUB-WGL-01"): [(17.5110, 78.8890), (17.7230, 79.1520)],  # Bhongir, Jangaon
    ("HUB-WGL-01", "HUB-VJA-01"): [(17.2473, 80.1514)],  # Khammam
}


def leg_polyline(hubs: dict, from_id: str | None, to_id: str) -> list[tuple[float, float]]:
    to = hubs[to_id]
    if from_id is None or from_id not in hubs:
        return [(to.lat, to.lng)]
    frm = hubs[from_id]
    if (from_id, to_id) in CORRIDOR_WAYPOINTS:
        mids = CORRIDOR_WAYPOINTS[(from_id, to_id)]
    else:
        mids = list(reversed(CORRIDOR_WAYPOINTS.get((to_id, from_id), [])))
    return [(frm.lat, frm.lng)] + mids + [(to.lat, to.lng)]


class GpsSimulator:
    def __init__(self):
        self.arrived_at: dict[str, datetime] = {}

    def reset(self):
        self.arrived_at.clear()

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
        line = leg_polyline(hubs, prev_id, route[target])
        pos = (vehicle.current_lat, vehicle.current_lng)
        if len(line) > 1:  # resume from the closest segment of the leg polyline
            seg = min(range(len(line) - 1),
                      key=lambda j: point_to_line_distance(pos, line[j], line[j + 1]))
            ahead = line[seg + 1:]
        else:
            ahead = line
        budget = vehicle.speed_kmh * minutes / 60
        lat, lng = pos
        heading = 0.0
        for wp in ahead:
            d = haversine(lat, lng, *wp)
            if d > 1e-6:
                heading = bearing(lat, lng, *wp)
            if d >= budget:
                f = budget / d if d else 1.0
                lat, lng = lat + (wp[0] - lat) * f, lng + (wp[1] - lng) * f
                budget = 0
                break
            lat, lng = wp
            budget -= d
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
