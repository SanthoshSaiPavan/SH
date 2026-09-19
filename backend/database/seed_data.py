"""Demo seed data: Indian logistics network.

Run `python -m database.seed_data` from backend/ to drop and re-seed.
Hubs RT-01..RT-08 come from the plan. HUB-WGL-01, HUB-VJA-01 and RT-09 were
added (approved) so the Module 7 Telangana/AP demo has real hubs; RT-09
distance/time are approximate.
"""
import random
import sys
from datetime import timedelta

import bcrypt

import config
from database.db import Base, SessionLocal, engine
from database.models import Hub, Route, Shipment, User, Vehicle
from utils import clock, roads
from utils.geo import haversine, interpolate

HUBS = [
    ("HUB-DEL-01", "Delhi Central Hub", "Delhi", "Delhi", 28.6139, 77.2090, "distribution", 5000),
    ("HUB-DEL-02", "Delhi South Sorting", "Delhi", "Delhi", 28.5245, 77.1855, "transfer", 2000),
    ("HUB-MUM-01", "Mumbai Main Hub", "Mumbai", "Maharashtra", 19.0760, 72.8777, "distribution", 6000),
    ("HUB-BLR-01", "Bangalore Tech Hub", "Bangalore", "Karnataka", 12.9716, 77.5946, "distribution", 4000),
    ("HUB-HYD-01", "Hyderabad Central", "Hyderabad", "Telangana", 17.3850, 78.4867, "distribution", 3500),
    ("HUB-CHN-01", "Chennai Port Hub", "Chennai", "Tamil Nadu", 13.0827, 80.2707, "distribution", 4500),
    ("HUB-KOL-01", "Kolkata East Hub", "Kolkata", "West Bengal", 22.5726, 88.3639, "distribution", 3000),
    ("HUB-JAI-01", "Jaipur Transfer", "Jaipur", "Rajasthan", 26.9124, 75.7873, "transfer", 1500),
    ("HUB-LKO-01", "Lucknow Sorting", "Lucknow", "Uttar Pradesh", 26.8467, 80.9462, "transfer", 1800),
    ("HUB-AHM-01", "Ahmedabad West", "Ahmedabad", "Gujarat", 23.0225, 72.5714, "transfer", 2200),
    ("HUB-PUN-01", "Pune Distribution", "Pune", "Maharashtra", 18.5204, 73.8567, "distribution", 2500),
    ("HUB-NAG-01", "Nagpur Central India", "Nagpur", "Maharashtra", 21.1458, 79.0882, "transfer", 2000),
    ("HUB-BHO-01", "Bhopal Relay", "Bhopal", "Madhya Pradesh", 23.2599, 77.4126, "transfer", 1200),
    ("HUB-PAT-01", "Patna East Hub", "Patna", "Bihar", 25.6093, 85.1376, "transfer", 1000),
    ("HUB-VIZ-01", "Vizag Port Hub", "Visakhapatnam", "Andhra Pradesh", 17.6868, 83.2185, "destination", 1500),
    ("HUB-WGL-01", "Warangal Transfer", "Warangal", "Telangana", 17.9689, 79.5941, "transfer", 1200),
    ("HUB-VJA-01", "Vijayawada Distribution", "Vijayawada", "Andhra Pradesh", 16.5062, 80.6480, "distribution", 2500),
]

ROUTES = [
    ("RT-01", "Delhi-Mumbai Express", ["HUB-DEL-01", "HUB-JAI-01", "HUB-AHM-01", "HUB-MUM-01"], 1400, 24, 18),
    ("RT-02", "Delhi-Bangalore Golden", ["HUB-DEL-01", "HUB-BHO-01", "HUB-NAG-01", "HUB-HYD-01", "HUB-BLR-01"], 2150, 36, 16),
    ("RT-03", "Mumbai-Chennai Coastal", ["HUB-MUM-01", "HUB-PUN-01", "HUB-BLR-01", "HUB-CHN-01"], 1350, 22, 17),
    ("RT-04", "Delhi-Kolkata Eastern", ["HUB-DEL-01", "HUB-LKO-01", "HUB-PAT-01", "HUB-KOL-01"], 1500, 26, 15),
    ("RT-05", "Hyderabad-Vizag Coastal", ["HUB-HYD-01", "HUB-VIZ-01"], 620, 10, 14),
    ("RT-06", "Delhi-Hyderabad Direct", ["HUB-DEL-01", "HUB-BHO-01", "HUB-NAG-01", "HUB-HYD-01"], 1600, 27, 16),
    ("RT-07", "Mumbai-Pune Shuttle", ["HUB-MUM-01", "HUB-PUN-01"], 150, 3, 20),
    ("RT-08", "Central India Cross", ["HUB-NAG-01", "HUB-BHO-01", "HUB-AHM-01", "HUB-MUM-01"], 1100, 18, 15),
    ("RT-09", "Hyderabad-Warangal-Vijayawada", ["HUB-HYD-01", "HUB-WGL-01", "HUB-VJA-01"], 360, 7, 14),
]

VEHICLE_SPECS = {  # type: (kg, cbm, speed)
    "truck": (10000, 40, 55),
    "trailer": (20000, 70, 50),
    "van": (1500, 10, 65),
}
CARRIERS = ["BlueDart Freight", "Gati", "VRL Logistics", "TCI Express", "Delhivery", "Safexpress"]

# (id, type, route_id, reversed, stop_index, progress to next stop, used fraction, hazmat)
NATIONAL_VEHICLES = [
    ("VEH-TRK-0001", "truck", "RT-01", False, 1, 0.4, 0.55, []),
    ("VEH-TRK-0002", "truck", "RT-01", True, 2, 0.6, 0.40, ["hazmat_class_3"]),
    ("VEH-TRL-0003", "trailer", "RT-02", False, 2, 0.3, 0.60, []),
    ("VEH-TRK-0004", "truck", "RT-02", True, 1, 0.7, 0.35, []),
    ("VEH-TRK-0005", "truck", "RT-03", False, 1, 0.5, 0.50, []),
    ("VEH-VAN-0006", "van", "RT-03", True, 2, 0.2, 0.30, []),
    ("VEH-TRK-0007", "truck", "RT-04", False, 1, 0.3, 0.45, []),
    ("VEH-TRL-0008", "trailer", "RT-04", True, 2, 0.8, 0.70, ["hazmat_class_3"]),
    ("VEH-TRK-0009", "truck", "RT-05", False, 1, 0.5, 0.40, []),
    ("VEH-TRK-0010", "truck", "RT-06", False, 2, 0.6, 0.50, []),
    ("VEH-VAN-0011", "van", "RT-07", False, 1, 0.5, 0.20, []),
    ("VEH-TRK-0012", "truck", "RT-08", False, 1, 0.2, 0.45, []),
]

# Module 7 demo trucks on RT-09. TRUCK-102 approaches Warangal with 35% free
# capacity (the first recommendation); TRUCK-104 follows as the fallback.
# TRUCK-105..110 (approved) fill the corridor in both directions so the demo
# graph stays busy; the forward ones are already past Warangal, so SHP-501's
# TRUCK-102/104 story is unchanged. TRUCK-107/110 start at Vijayawada (stop 0)
# for the shipments stranded there; TRUCK-107 is hazmat-certified for SHP-505.
# (id, reversed, stop_index, progress to next stop, used fraction, hazmat)
DEMO_TRUCKS = [
    ("TRUCK-101", False, 2, 0.35, 0.60, []),
    ("TRUCK-102", False, 1, 0.45, 0.65, []),
    ("TRUCK-103", True, 1, 0.50, 0.50, []),
    ("TRUCK-104", False, 1, 0.10, 0.40, []),
    ("TRUCK-105", False, 2, 0.70, 0.50, []),
    ("TRUCK-106", True, 1, 0.20, 0.45, []),
    ("TRUCK-107", True, 0, 0.0, 0.30, ["hazmat_class_3"]),
    ("TRUCK-108", False, 2, 0.20, 0.85, []),
    ("TRUCK-109", True, 2, 0.60, 0.40, []),
    ("TRUCK-110", True, 0, 0.0, 0.55, []),
]

# Extra scripted wrong-hub shipments in the RT-09 corridor (approved), so the
# demo shows several recoveries at once.
# (id, origin, destination, current hub, priority, flags, kg, deadline hours)
DEMO_MISPLACED = [
    ("SHP-502", "HUB-VJA-01", "HUB-HYD-01", "HUB-WGL-01", "medium", [], 80, 14),
    ("SHP-503", "HUB-HYD-01", "HUB-VJA-01", "HUB-WGL-01", "high", [], 45, 8),
    ("SHP-504", "HUB-WGL-01", "HUB-HYD-01", "HUB-VJA-01", "low", ["fragile"], 150, 20),
    ("SHP-505", "HUB-HYD-01", "HUB-WGL-01", "HUB-VJA-01", "high", ["hazmat_class_3"], 200, 12),
]

USERS = [  # username, password, role, vehicle_id
    ("admin", "admin123", "ADMIN", None),
    ("operator", "operator123", "LOGISTICS_OPERATOR", None),
    ("driver101", "driver123", "DRIVER", "TRUCK-101"),
    ("driver102", "driver123", "DRIVER", "TRUCK-102"),
    ("driver103", "driver123", "DRIVER", "TRUCK-103"),
    ("driver104", "driver123", "DRIVER", "TRUCK-104"),
]


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _position_between(hubs, route, stop_index, progress):
    """Point `progress` of the way along the road from route[stop_index-1] to route[stop_index]."""
    a, b = hubs[route[max(stop_index - 1, 0)]], hubs[route[stop_index]]
    path = roads.road_path(a.id, b.id)
    if path:
        return roads.point_along_path(path, progress)
    return interpolate(a.lat, a.lng, b.lat, b.lng, progress)


def _leg_hours(a: Hub, b: Hub, speed: float) -> float:
    return roads.hub_km(a, b) / speed


def _hours_since_departure(hubs, v) -> float:
    """Time since the vehicle left its previous hub, consistent with its seeded position."""
    route, idx = v.planned_route, v.current_stop_index
    prev, nxt = hubs[route[max(idx - 1, 0)]], hubs[route[idx]]
    driven = roads.hub_km(prev, nxt) - roads.km_to_hub(prev.id, nxt, v.current_lat, v.current_lng)
    return max(driven, 0.0) / v.speed_kmh


def build_seed():
    rng = random.Random(42)
    now = clock.now()
    hubs = {
        h[0]: Hub(id=h[0], name=h[1], city=h[2], state=h[3], lat=h[4], lng=h[5],
                  hub_type=h[6], capacity_packages=h[7], current_load=0, can_hold_misplaced=True)
        for h in HUBS
    }
    routes = {
        r[0]: Route(id=r[0], name=r[1], hub_sequence=r[2], distance_km=r[3],
                    estimated_time_hours=r[4], cost_per_km=r[5], active=True)
        for r in ROUTES
    }

    vehicles: dict[str, Vehicle] = {}

    def make_vehicle(vid, vtype, route_id, rev, stop_idx, progress, used, hazmat, carrier):
        kg, cbm, speed = VEHICLE_SPECS[vtype]
        route = list(routes[route_id].hub_sequence)
        if rev:
            route.reverse()
        lat, lng = _position_between(hubs, route, stop_idx, progress)
        vehicles[vid] = Vehicle(
            id=vid, vehicle_type=vtype, carrier_name=carrier, current_lat=lat, current_lng=lng,
            route_id=route_id, planned_route=route, current_stop_index=stop_idx,
            total_capacity_kg=kg, used_capacity_kg=round(kg * used, 1),
            total_capacity_cbm=cbm, used_capacity_cbm=round(cbm * used, 1),
            speed_kmh=speed, status="in_transit", piggybacked_shipments=[],
            hazmat_certifications=hazmat, fleet_id=config.DEFAULT_FLEET_ID,
        )

    for vid, vtype, rid, rev, idx, prog, used, hazmat in NATIONAL_VEHICLES:
        make_vehicle(vid, vtype, rid, rev, idx, prog, used, hazmat, rng.choice(CARRIERS))
    for vid, rev, idx, prog, used, hazmat in DEMO_TRUCKS:
        make_vehicle(vid, "truck", "RT-09", rev, idx, prog, used, hazmat, "Deccan Roadways")
    vehicles["TRUCK-102"].speed_kmh = 60

    shipments = _build_shipments(rng, now, hubs, vehicles)

    users = [User(id=f"USR-{u[0]}", username=u[0], password_hash=_hash(u[1]), role=u[2],
                  vehicle_id=u[3]) for u in USERS]
    return list(hubs.values()), list(routes.values()), list(vehicles.values()), shipments, users


PRIORITY_MIX = ["critical"] * 3 + ["high"] * 7 + ["medium"] * 13 + ["low"] * 7


def carried_shipment(rng, now, hubs, v, origin_idx: int, shipment_id: str, tracking: str,
                     priority: str, last_scan_at) -> Shipment:
    """A shipment riding vehicle `v` from planned_route[origin_idx] to a later stop on its route."""
    route = v.planned_route
    origin = route[origin_idx]
    destination = route[rng.randint(max(origin_idx + 1, v.current_stop_index), len(route) - 1)]
    expected = route[origin_idx: route.index(destination, origin_idx) + 1]
    weight = round(rng.uniform(20, 400), 1)
    volume = round(weight / rng.uniform(150, 300), 2)
    remaining = sum(_leg_hours(hubs[a], hubs[b], v.speed_kmh) for a, b in zip(expected, expected[1:]))
    flags = []
    if v.hazmat_certifications and rng.random() < 0.5:
        flags.append("hazmat_class_3")
    elif rng.random() < 0.1:
        flags.append("fragile")
    return Shipment(
        id=shipment_id, tracking_number=tracking, origin_hub_id=origin,
        destination_hub_id=destination, current_hub_id=None, expected_route=expected,
        actual_route=[origin], status="in_transit", priority=priority, handling_flags=flags,
        weight_kg=weight, volume_cbm=volume,
        deadline=now + timedelta(hours=remaining * rng.uniform(1.4, 2.5) + 2),
        current_lat=v.current_lat, current_lng=v.current_lng, current_vehicle_id=v.id,
        last_scan_at=last_scan_at,
    )


def _build_shipments(rng, now, hubs, vehicles):
    """30 in-transit shipments riding national vehicles, plus scripted SHP-501..505."""
    priorities = list(PRIORITY_MIX)
    rng.shuffle(priorities)
    carriers = [v for v in vehicles.values() if not v.id.startswith("TRUCK-")]
    date_tag = now.strftime("%Y%m%d")
    shipments = []
    for n in range(30):
        v = carriers[n % len(carriers)]
        shipments.append(carried_shipment(
            rng, now, hubs, v, max(v.current_stop_index - 1, 0), f"SHP-{date_tag}-{n + 1:04d}",
            f"PGS{date_tag}{n + 1:04d}", priorities[n],
            now - timedelta(hours=_hours_since_departure(hubs, v))))

    wgl = hubs["HUB-WGL-01"]
    shipments.append(Shipment(
        id="SHP-501", tracking_number="PGS-DEMO-501", origin_hub_id="HUB-HYD-01",
        destination_hub_id="HUB-VJA-01", current_hub_id="HUB-WGL-01",
        expected_route=["HUB-HYD-01", "HUB-VJA-01"], actual_route=["HUB-HYD-01", "HUB-WGL-01"],
        status="in_transit", priority="high", handling_flags=[], weight_kg=120, volume_cbm=0.6,
        deadline=now + timedelta(hours=10), current_lat=wgl.lat, current_lng=wgl.lng,
        current_vehicle_id=None, last_scan_at=now - timedelta(minutes=20),
    ))
    for sid, origin, dest, at, priority, flags, kg, deadline_h in DEMO_MISPLACED:
        hub = hubs[at]
        shipments.append(Shipment(
            id=sid, tracking_number=f"PGS-DEMO-{sid[4:]}", origin_hub_id=origin,
            destination_hub_id=dest, current_hub_id=at, expected_route=[origin, dest],
            actual_route=[origin, at], status="in_transit", priority=priority,
            handling_flags=flags, weight_kg=kg, volume_cbm=round(kg / 200, 2),
            deadline=now + timedelta(hours=deadline_h), current_lat=hub.lat, current_lng=hub.lng,
            current_vehicle_id=None, last_scan_at=now - timedelta(minutes=20),
        ))
    return shipments


def reseed() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    hubs, routes, vehicles, shipments, users = build_seed()
    with SessionLocal() as db:
        db.add_all(hubs + routes)
        db.flush()
        db.add_all(vehicles)
        db.flush()
        db.add_all(shipments + users)
        db.commit()


def seed_if_empty() -> bool:
    with SessionLocal() as db:
        if db.query(Hub).first() is not None:
            return False
    reseed()
    return True


def clear_live_state() -> None:
    """Drop Redis vehicle state so stale positions don't survive a reseed."""
    import redis

    r = redis.Redis.from_url(config.REDIS_URL)
    keys = list(r.scan_iter("vehicle:*"))
    if keys:
        r.delete(*keys)


if __name__ == "__main__":
    reseed()
    clear_live_state()
    print("Seeded PiggyShip demo data.", file=sys.stderr)
