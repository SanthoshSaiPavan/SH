"""MODULE 5: Simulation engine and the main engine tick.

Every SIM_TICK_SECONDS the engine loop:
  1. (DEMO SIMULATION, running) advances the simulated clock and moves every
     vehicle through the GPS simulator → location ingest pipeline
  2. (DEMO) every N ticks randomly misplaces a shipment, and tops the network back up
     to SIM_TARGET_ACTIVE_SHIPMENTS by loading new shipments at hubs
  3. runs anomaly detection (Module 1) and raises alerts
  4. rebuilds the time-expanded graph (Module 4) for the recommendation loop
  5. advances reroute/dedicated recoveries and syncs carried shipment positions
  6. emits 'simulation:tick'
In LIVE GPS mode steps 1–2 are skipped and the clock is wall time.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import selectinload

import config
from database.db import SessionLocal
from database.models import Hub, Route, Shipment, Vehicle
from database.seed_data import PRIORITY_MIX, carried_shipment
from engines import anomaly_detector, fleet_progress
from realtime import auth
from realtime.gps_simulator import gps_simulator, restart_reversed
from realtime.location_service import location_service
from realtime.socket_server import emit_fleet
from utils import clock

log = logging.getLogger(__name__)


class SimulationEngine:
    def __init__(self):
        self.mode = "demo"  # 'demo' (DEMO SIMULATION) | 'live' (LIVE GPS)
        self.running = False
        self.speed = 1
        self.tick_number = 0
        self.auto_recovery = False
        self.rng = random.Random()
        self.last_events = 0

    def status(self) -> dict:
        return {"mode": self.mode, "running": self.running, "speed": self.speed,
                "tick_number": self.tick_number, "auto_recovery": self.auto_recovery,
                "sim_time": clock.now().isoformat(), "available_speeds": list(config.SIM_SPEEDS)}

    def start(self):
        if self.mode != "demo":
            self.set_mode("demo")
        self.running = True

    def stop(self):
        self.running = False

    def set_speed(self, speed: int):
        if speed not in config.SIM_SPEEDS:
            raise ValueError(f"speed must be one of {config.SIM_SPEEDS}")
        self.speed = speed

    def set_mode(self, mode: str):
        if mode not in ("demo", "live"):
            raise ValueError("mode must be 'demo' or 'live'")
        if mode == self.mode:
            return
        self.mode = mode
        self.running = False
        # Timestamps from the other clock would be rejected as stale/implausible.
        location_service.last_ts.clear()
        clock.set_sim_time(clock.utcnow() if mode == "demo" else None)

    # ---- demo movement --------------------------------------------------------
    async def move_vehicles(self, minutes: float) -> None:
        now = clock.now()
        with SessionLocal() as db:
            hubs = {h.id: h for h in db.query(Hub).all()}
            vehicles = db.query(Vehicle).all()
            claims = auth.simulator_claims([v.id for v in vehicles])
            updates = []
            for v in vehicles:
                at_end = v.status == "completed" or (
                    v.status == "at_hub" and v.current_stop_index >= len(v.planned_route) - 1)
                if at_end and gps_simulator.dwell_done(v, now) and restart_reversed(v):
                    db.commit()
                pos = gps_simulator.next_position(v, hubs, minutes, now)
                if pos:
                    updates.append(pos)
        for pos in updates:
            ok, err = await location_service.ingest(claims, pos)
            if not ok:
                log.warning("Simulator update rejected for %s: %s", pos["vehicle_id"], err)

    def misplace(self, db, shipment_id: str | None = None, kind: str | None = None) -> dict:
        """Misplace a shipment (random when not specified). Returns what happened.

        Changes the physical ground truth and writes only the scans a real network would
        produce; detection then has to find it from those scans:
          wrong_hub      unloaded at an off-route hub   -> 'excess' scan there
          wrong_vehicle  loaded onto another vehicle    -> 'load' scan onto it (manifest unchanged)
          stuck          left behind at its last hub    -> no scan; a 'short' is raised when its
                         manifest vehicle reaches the next hub (scan gap/time anomaly as fallback)
        """
        query = db.query(Shipment).filter(Shipment.status == "in_transit",
                                          Shipment.recovery_strategy.is_(None),
                                          Shipment.current_vehicle_id.isnot(None))
        shipment = (db.get(Shipment, shipment_id) if shipment_id
                    else self.rng.choice(query.all() or [None]))
        if shipment is None:
            raise ValueError("No eligible shipment to misplace")
        if shipment.status not in ("in_transit", "delayed"):
            raise ValueError(f"{shipment.id} is {shipment.status}, not in transit")
        kind = kind or self.rng.choices(list(config.SIM_MISPLACE_PROBS),
                                        weights=list(config.SIM_MISPLACE_PROBS.values()))[0]
        now = clock.now()
        vehicle = db.get(Vehicle, shipment.current_vehicle_id) if shipment.current_vehicle_id else None
        expected = set(shipment.expected_route or [])
        if kind == "wrong_hub":
            hub = self.rng.choice([h for h in db.query(Hub).all() if h.id not in expected])
            if vehicle:
                fleet_progress._release(vehicle, shipment)
            fleet_progress._place_at_hub(shipment, hub)
            shipment.actual_route = list(shipment.actual_route or []) + [hub.id]
            shipment.last_scan_at = now
            fleet_progress.record_scan(shipment, "excess", now, hub.id, expected=False,
                                       note="scanned at a hub not on its expected route")
            detail = f"unloaded at {hub.id}"
        elif kind == "wrong_vehicle":
            others = [v for v in db.query(Vehicle).all()
                      if v.id != shipment.current_vehicle_id and v.status != "completed"
                      and not expected & set(v.planned_route[v.current_stop_index:])
                      and v.total_capacity_kg - v.used_capacity_kg >= shipment.weight_kg]
            if not others:
                raise ValueError("No vehicle available to misload onto")
            wrong = self.rng.choice(others)
            if vehicle:
                fleet_progress._release(vehicle, shipment)
            wrong.used_capacity_kg += shipment.weight_kg
            wrong.used_capacity_cbm += shipment.volume_cbm
            shipment.current_vehicle_id = wrong.id
            shipment.current_hub_id = None
            shipment.current_lat, shipment.current_lng = wrong.current_lat, wrong.current_lng
            shipment.last_scan_at = now
            next_hub = anomaly_detector.expected_segment(shipment)[1]
            at_hub = wrong.planned_route[wrong.current_stop_index] if wrong.status == "at_hub" else None
            fleet_progress.record_scan(shipment, "load", now, at_hub, wrong.id,
                                       expected=anomaly_detector.vehicle_serves(wrong, next_hub),
                                       note=f"manifested on {shipment.manifest_vehicle_id}")
            detail = f"loaded onto {wrong.id}"
        elif kind == "stuck":
            last = next((h for h in reversed(shipment.actual_route or []) if h in expected),
                        shipment.origin_hub_id)
            hub = db.get(Hub, last)
            if vehicle:
                fleet_progress._release(vehicle, shipment)
            fleet_progress._place_at_hub(shipment, hub)
            detail = f"left behind at {hub.id}; {shipment.manifest_vehicle_id} drives on without it"
        else:
            raise ValueError(f"unknown misplacement type {kind}")
        db.commit()
        return {"shipment_id": shipment.id, "type": kind, "detail": detail}

    def generate_shipment(self, db, vehicle: Vehicle) -> Shipment:
        """Load one new shipment onto `vehicle`, which is dwelling at a hub."""
        now = clock.now()
        hubs = {h.id: h for h in db.query(Hub).all()}
        date_tag = now.strftime("%Y%m%d")
        n = db.query(func.count(Shipment.id)).scalar() + 1
        while db.get(Shipment, f"SHP-{date_tag}-{n:04d}") is not None:
            n += 1
        shipment = carried_shipment(self.rng, now, hubs, vehicle, vehicle.current_stop_index,
                                    f"SHP-{date_tag}-{n:04d}", f"PGS{date_tag}{n:04d}",
                                    self.rng.choice(PRIORITY_MIX), now)
        vehicle.used_capacity_kg += shipment.weight_kg
        vehicle.used_capacity_cbm += shipment.volume_cbm
        db.add(shipment)
        db.commit()
        return shipment

    async def top_up_shipments(self) -> None:
        """Refill the network toward SIM_TARGET_ACTIVE_SHIPMENTS, one new shipment per
        vehicle currently dwelling at a (non-final) hub with room for it."""
        created = []
        with SessionLocal() as db:
            deficit = (config.SIM_TARGET_ACTIVE_SHIPMENTS
                       - db.query(Shipment).filter_by(status="in_transit").count())
            if deficit <= 0:
                return
            at_hub = [v for v in db.query(Vehicle).filter_by(status="at_hub").all()
                      if v.current_stop_index < len(v.planned_route) - 1
                      and v.total_capacity_kg - v.used_capacity_kg >= 400]
            self.rng.shuffle(at_hub)
            for vehicle in at_hub[:deficit]:
                s = self.generate_shipment(db, vehicle)
                created.append({"shipment_id": s.id, "vehicle_id": s.current_vehicle_id,
                                "origin_hub_id": s.origin_hub_id,
                                "destination_hub_id": s.destination_hub_id,
                                "priority": s.priority})
        for payload in created:
            log.info("Generated shipment %s on %s", payload["shipment_id"], payload["vehicle_id"])
            await emit_fleet("shipment:created", payload, shipment_id=payload["shipment_id"])

    async def step(self) -> None:
        minutes = config.SIM_MINUTES_PER_TICK * self.speed
        clock.advance(timedelta(minutes=minutes))
        await self.move_vehicles(minutes)
        if self.tick_number and self.tick_number % config.SIM_MISPLACE_EVERY_N_TICKS == 0:
            with SessionLocal() as db:
                try:
                    log.info("Simulated misplacement: %s", self.misplace(db))
                except ValueError as exc:
                    log.info("Skipped simulated misplacement: %s", exc)
        if self.tick_number % config.SIM_NEW_SHIPMENT_EVERY_N_TICKS == 0:
            await self.top_up_shipments()


simulation = SimulationEngine()


async def run_detection() -> int:
    """Module 1 over active shipments; flag new anomalies and alert."""
    from realtime.recommendation_loop import recommendation_loop

    now = clock.now()

    def detect() -> list:  # worker thread, own session
        alerts = []
        with SessionLocal() as db:
            hubs = {h.id: h for h in db.query(Hub).all()}
            vehicles = {v.id: v for v in db.query(Vehicle).all()}
            active = (db.query(Shipment).options(selectinload(Shipment.scans)).filter(
                Shipment.status.in_(anomaly_detector.ACTIVE_STATUSES),
                Shipment.recovery_strategy.is_(None)).all())
            for result in anomaly_detector.detect_anomalies(active, hubs, now, vehicles=vehicles):
                s = db.get(Shipment, result.shipment_id)
                s.status = "misplaced"
                s.misplacement_type = result.misplacement_type
                s.misplacement_detected_at = now
                alerts.append({"shipment_id": s.id, "type": result.misplacement_type,
                               "severity": result.severity,
                               "severity_score": result.severity_score,
                               "priority": s.priority, "message": result.reason})
            db.commit()
        return alerts

    alerts = await asyncio.to_thread(detect)
    for alert in alerts:
        await emit_fleet("shipment:alert", alert, shipment_id=alert["shipment_id"])
        recommendation_loop.mark_dirty(alert["shipment_id"])
    return len(alerts)


async def engine_tick() -> None:
    from realtime.recommendation_loop import recommendation_loop

    if simulation.mode == "demo" and simulation.running:
        await simulation.step()
        simulation.tick_number += 1
    events_count = await run_detection()
    positions = await location_service.positions()
    now = clock.now()

    def progress() -> list:  # worker thread, own session
        with SessionLocal() as db:
            fleet_progress.sync_carried_shipments(db, positions)
            events = fleet_progress.progress_virtual_recoveries(db, now)
            db.commit()
        return events

    events = await asyncio.to_thread(progress)
    await recommendation_loop.rebuild(positions, location_service.offline_vehicles())
    for event, body, shipment_id, vehicle_id in events:
        await emit_fleet(event, body, shipment_id, vehicle_id)
    events_count += len(events)
    simulation.last_events = events_count
    await emit_fleet("simulation:tick", {"tick_number": simulation.tick_number,
                                         "timestamp": clock.now().isoformat(),
                                         "events_count": events_count,
                                         "mode": simulation.mode, "running": simulation.running,
                                         "speed": simulation.speed})


async def engine_loop() -> None:
    while True:
        await asyncio.sleep(config.SIM_TICK_SECONDS)
        try:
            await engine_tick()
        except Exception:
            log.exception("Engine tick failed")


def load_routes(db) -> list:
    return db.query(Route).all()
