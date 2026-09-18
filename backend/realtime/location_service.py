"""Location ingest: validate → Redis latest state → batched PostgreSQL history → rooms.

Also runs the live / delayed / offline status checker. `last_seen` is wall
clock (for staleness); position timestamps are the engine clock (simulated
time in DEMO mode), so implied-speed checks use real vehicle speeds.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis

import config
from database.db import SessionLocal
from database.models import Hub, Vehicle, VehicleLocation
from engines import fleet_progress
from realtime import auth
from realtime.socket_server import emit_fleet, emit_to_rooms
from utils import clock, roads
from utils.geo import haversine

log = logging.getLogger(__name__)
DELAY_TOLERANCE = timedelta(minutes=10)  # ASSUMPTION: ETA slip before 'delayed'


class LocationService:
    def __init__(self):
        self.redis = aioredis.from_url(config.REDIS_URL, decode_responses=True)
        self.buffer: list[dict] = []
        self.last_ts: dict[str, datetime] = {}
        self.status: dict[str, str] = {}
        self.planned_arrival: dict[str, datetime] = {}
        self.linked_shipments: dict[str, set] = {}  # vehicle_id -> shipment ids (candidates/assigned)
        self.on_moved = None  # set by the recommendation loop

    # ---- validation --------------------------------------------------------
    def _validate(self, claims, data, vehicle) -> tuple[dict | None, str | None]:
        vid = data.get("vehicle_id")
        if vehicle is None:
            return None, f"unknown vehicle {vid}"
        if not auth.can_report_vehicle(claims, vid):
            return None, "not authorised for this vehicle"
        try:
            lat, lng = float(data["lat"]), float(data["lng"])
            speed = float(data.get("speed") or 0.0)
            heading = float(data.get("heading") or 0.0) % 360
            ts = (datetime.fromisoformat(str(data["timestamp"]).replace("Z", "+00:00"))
                  if data.get("timestamp") else clock.now())
        except (KeyError, TypeError, ValueError):
            return None, "malformed payload"
        if ts.tzinfo is not None:
            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        b = config.INDIA_BOUNDS
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None, "coordinates out of range"
        if not (b["min_lat"] <= lat <= b["max_lat"] and b["min_lng"] <= lng <= b["max_lng"]):
            return None, "coordinates outside India"
        prev_ts = self.last_ts.get(vid)
        if (prev_ts is not None and ts <= prev_ts
                and claims.get("sub") != config.STALE_TIMESTAMP_EXEMPT_USER):
            return None, "stale timestamp"
        if prev_ts is not None:
            hours = (ts - prev_ts).total_seconds() / 3600
            km = haversine(vehicle.current_lat, vehicle.current_lng, lat, lng)
            if hours > 0 and km / hours > config.MAX_PLAUSIBLE_SPEED_KMH:
                return None, f"implausible jump ({km / hours:.0f} km/h)"
        return {"vehicle_id": vid, "lat": lat, "lng": lng, "speed": speed,
                "heading": heading, "timestamp": ts}, None

    # ---- ingest ------------------------------------------------------------
    async def ingest(self, claims: dict, data: dict) -> tuple[bool, str | None]:
        events = []
        with SessionLocal() as db:
            vehicle = db.get(Vehicle, data.get("vehicle_id"))
            loc, error = self._validate(claims, data, vehicle)
            if error:
                log.info("Rejected location update %s: %s", data.get("vehicle_id"), error)
                return False, error
            vid = loc["vehicle_id"]
            prev_status, prev_idx = vehicle.status, vehicle.current_stop_index
            events = fleet_progress.on_position(db, vehicle, loc["lat"], loc["lng"],
                                                loc["timestamp"])
            if vehicle.status == "in_transit" and (prev_status != "in_transit"
                                                   or vehicle.current_stop_index != prev_idx):
                self._plan_arrival(db, vehicle, loc["timestamp"])
            db.commit()
            state = self._state(vehicle, loc)
            fleet_room = f"fleet:{vehicle.fleet_id}"
        self.last_ts[vid] = loc["timestamp"]
        await self.redis.set(f"vehicle:{vid}", json.dumps(state))
        await self.redis.set(f"vehicle:{vid}:last_seen", time.time())
        self.buffer.append({**loc})
        payload = {k: state[k] for k in ("vehicle_id", "lat", "lng", "speed", "heading",
                                          "timestamp", "status", "used_capacity_kg",
                                          "max_capacity_kg")}
        rooms = [f"vehicle:{vid}", fleet_room] + [
            f"shipment:{s}" for s in self.linked_shipments.get(vid, ())]
        await emit_to_rooms("vehicle:location:update", payload, rooms)
        for event, body, shipment_id, vehicle_id in events:
            await emit_fleet(event, body, shipment_id, vehicle_id)
        if self.on_moved:
            self.on_moved(vid)
        return True, None

    def _plan_arrival(self, db, vehicle, ts):
        idx = vehicle.current_stop_index
        hub = db.get(Hub, vehicle.planned_route[idx])
        prev_id = vehicle.planned_route[idx - 1] if idx > 0 else None
        km = roads.km_to_hub(prev_id, hub, vehicle.current_lat, vehicle.current_lng)
        self.planned_arrival[vehicle.id] = ts + timedelta(hours=km / max(vehicle.speed_kmh, 1))

    @staticmethod
    def _state(vehicle: Vehicle, loc: dict) -> dict:
        route = vehicle.planned_route or []
        return {
            "vehicle_id": vehicle.id, "lat": loc["lat"], "lng": loc["lng"],
            "speed": loc["speed"], "heading": loc["heading"],
            "timestamp": loc["timestamp"].isoformat(),
            "used_capacity_kg": vehicle.used_capacity_kg,
            "max_capacity_kg": vehicle.total_capacity_kg,
            "status": vehicle.status, "current_route_id": vehicle.route_id,
            "destination_hub_id": route[-1] if route else None,
            "next_hub_id": (route[vehicle.current_stop_index]
                            if vehicle.current_stop_index < len(route) else None),
            "planned_route": route,
        }

    # ---- reads -------------------------------------------------------------
    async def all_states(self) -> dict[str, dict]:
        keys = [k async for k in self.redis.scan_iter("vehicle:*") if k.count(":") == 1]
        values = await self.redis.mget(keys) if keys else []
        states = {k.split(":", 1)[1]: json.loads(v) for k, v in zip(keys, values) if v}
        for vid, st in states.items():
            st["connection"] = self.status.get(vid, "offline")
        return states

    async def positions(self) -> dict[str, tuple[float, float]]:
        return {vid: (s["lat"], s["lng"]) for vid, s in (await self.all_states()).items()}

    def offline_vehicles(self) -> set[str]:
        return {vid for vid, st in self.status.items() if st == "offline"}

    async def prime_from_db(self) -> None:
        """Seed Redis with DB positions so the map has markers before the first ping."""
        with SessionLocal() as db:
            for v in db.query(Vehicle).all():
                if await self.redis.exists(f"vehicle:{v.id}"):
                    continue
                loc = {"lat": v.current_lat, "lng": v.current_lng, "speed": 0.0,
                       "heading": 0.0, "timestamp": clock.now()}
                await self.redis.set(f"vehicle:{v.id}", json.dumps(self._state(v, loc)))

    async def reset(self) -> None:
        keys = [k async for k in self.redis.scan_iter("vehicle:*")]
        if keys:
            await self.redis.delete(*keys)
        self.buffer.clear()
        self.last_ts.clear()
        self.status.clear()
        self.planned_arrival.clear()

    # ---- background tasks ----------------------------------------------------
    async def flush_loop(self) -> None:
        while True:
            await asyncio.sleep(config.LOCATION_FLUSH_SECONDS)
            try:
                self.flush()
            except Exception:  # keep the loop alive; log and retry next interval
                log.exception("Location history flush failed")

    def flush(self) -> None:
        if not self.buffer:
            return
        batch, self.buffer = self.buffer, []
        with SessionLocal() as db:
            db.add_all(VehicleLocation(vehicle_id=r["vehicle_id"], lat=r["lat"], lng=r["lng"],
                                       speed_kmh=r["speed"], heading=r["heading"],
                                       recorded_at=r["timestamp"]) for r in batch)
            db.commit()

    async def status_loop(self) -> None:
        while True:
            await asyncio.sleep(config.STATUS_CHECK_INTERVAL_SECONDS)
            try:
                await self.check_statuses()
            except Exception:
                log.exception("Status check failed")

    async def check_statuses(self) -> None:
        now_wall = time.time()
        with SessionLocal() as db:
            vehicles = {v.id: v for v in db.query(Vehicle).all()}
        states = await self.all_states()
        for vid, vehicle in vehicles.items():
            seen = await self.redis.get(f"vehicle:{vid}:last_seen")
            age = now_wall - float(seen) if seen else float("inf")
            if age > config.OFFLINE_AFTER_SECONDS:
                new = "offline"
            elif self._is_delayed(vehicle, states.get(vid)):
                new = "delayed"
            elif age <= config.STALE_AFTER_SECONDS:
                new = "live"
            else:
                new = self.status.get(vid, "live")
            if self.status.get(vid) != new:
                self.status[vid] = new
                await emit_fleet("vehicle:status", {"vehicle_id": vid, "status": new},
                                 vehicle_id=vid)
                if self.on_moved and new == "offline":
                    self.on_moved(vid)

    def _is_delayed(self, vehicle: Vehicle, state: dict | None) -> bool:
        planned = self.planned_arrival.get(vehicle.id)
        if planned is None or state is None or vehicle.status != "in_transit":
            return False
        route = vehicle.planned_route or []
        if vehicle.current_stop_index >= len(route):
            return False
        idx = vehicle.current_stop_index
        with SessionLocal() as db:
            hub = db.get(Hub, route[idx])
        km = roads.km_to_hub(route[idx - 1] if idx > 0 else None, hub, state["lat"], state["lng"])
        speed = max(state.get("speed") or 0.0, 5.0)
        eta = clock.now() + timedelta(hours=km / speed)
        return eta > planned + DELAY_TOLERANCE


location_service = LocationService()

