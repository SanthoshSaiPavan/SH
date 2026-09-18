"""Throttled re-evaluation of misplaced shipments with stability (switching) rules.

Vehicle movement marks nearby misplaced shipments dirty; every
RECOMPUTE_INTERVAL_SECONDS dirty shipments are re-run through Modules 2→3.
A recommendation only switches when the new best beats the current one by
SWITCH_MARGIN, or when the current one is no longer feasible. Approved or
auto-executed recoveries are locked until they complete or become infeasible.
"""
from __future__ import annotations

import asyncio
import logging

import config
from database.db import SessionLocal
from database.models import Hub, Route, Shipment, Vehicle
from engines import decision_agent, fleet_progress
from engines import graph_network as gn
from engines import recovery_engine as re_
from realtime.location_service import location_service
from realtime.socket_server import emit_fleet
from utils import clock
from utils.geo import haversine

log = logging.getLogger(__name__)


def _identity(strategy: re_.Strategy | None):
    return (strategy.type, strategy.vehicle_id) if strategy else None


class RecommendationLoop:
    def __init__(self):
        self.graph = None
        self.routes: list = []
        self.evaluations: dict[str, re_.Evaluation] = {}
        self.current: dict[str, re_.Strategy] = {}
        self.reasons: dict[str, str] = {}
        self.rejected: set[str] = set()
        self.dirty: set[str] = set()
        self.offline: set[str] = set()
        self.misplaced_pos: dict[str, tuple] = {}
        self.vehicle_paths: dict[str, list] = {}
        location_service.on_moved = self.on_vehicle_moved

    def reset(self):
        self.__init__()

    # ---- dirty tracking ---------------------------------------------------------
    def mark_dirty(self, shipment_id: str) -> None:
        self.dirty.add(shipment_id)

    def on_vehicle_moved(self, vehicle_id: str) -> None:
        path = self.vehicle_paths.get(vehicle_id)
        if not path:
            return
        for sid, (lat, lng) in self.misplaced_pos.items():
            if any(haversine(lat, lng, p[0], p[1]) <= config.RELEVANCE_RADIUS_KM for p in path):
                self.dirty.add(sid)

    def rebuild(self, db, positions: dict, offline: set) -> None:
        """Called every engine tick: fresh graph + caches used for dirty marking."""
        hubs = {h.id: h for h in db.query(Hub).all()}
        vehicles = db.query(Vehicle).all()
        self.routes = db.query(Route).all()
        cargo = {}
        for s in db.query(Shipment).filter(Shipment.current_vehicle_id.isnot(None)):
            classes = {f for f in (s.handling_flags or []) if f.startswith(gn.HAZMAT_PREFIX)}
            if classes:
                cargo.setdefault(s.current_vehicle_id, set()).update(classes)
        self.offline = set(offline)
        self.graph = gn.build_time_expanded_graph(hubs, vehicles, self.routes, clock.now(),
                                                  live_positions=positions,
                                                  exclude_vehicle_ids=self.offline,
                                                  cargo_hazmat=cargo)
        self.vehicle_paths = {
            v.id: [positions.get(v.id, (v.current_lat, v.current_lng))]
            + [(hubs[h].lat, hubs[h].lng) for h in v.planned_route[v.current_stop_index:]]
            for v in vehicles}
        misplaced = db.query(Shipment).filter_by(status="misplaced").all()
        self.misplaced_pos = {s.id: (s.current_lat, s.current_lng) for s in misplaced
                              if s.current_lat is not None}
        for s in misplaced:
            if s.id not in self.evaluations:
                self.dirty.add(s.id)

    # ---- evaluation ---------------------------------------------------------------
    def _switch_decision(self, sid: str, ev: re_.Evaluation) -> tuple[re_.Strategy, str | None]:
        """Apply stability rules. Returns (recommendation, reason if it changed)."""
        best = ev.best
        cur = self.current.get(sid)
        if cur is None:
            return best, "initial recommendation"
        same = next((s for s in ev.strategies if _identity(s) == _identity(cur) and s.feasible),
                    None)
        if same is None:
            why = ("went offline" if cur.vehicle_id in self.offline else
                   "no longer has a feasible path (rerouted, lost capacity or missed the "
                   "pickup window)")
            label = cur.vehicle_id or cur.type
            return best, f"{label} {why}; switched to {best.vehicle_id or best.type}"
        if _identity(best) != _identity(cur) and best.score > same.score + config.SWITCH_MARGIN:
            return best, (f"{best.vehicle_id or best.type} scores {best.score:.1f} vs "
                          f"{same.score:.1f} for {cur.vehicle_id or cur.type} "
                          f"(margin > {config.SWITCH_MARGIN:.0f})")
        return same, None

    def recommendation_payload(self, sid: str, rec: re_.Strategy, ev: re_.Evaluation,
                               reason: str | None) -> dict:
        return {
            "shipment_id": sid, "strategy": rec.type, "strategy_id": rec.id,
            "vehicle_id": rec.vehicle_id, "score": rec.score,
            "pickup_eta": rec.details.get("pickup_time")
            or rec.details.get("next_vehicle_departure"),
            "delivery_eta": rec.arrival_time.isoformat() if rec.arrival_time else None,
            "available_capacity": rec.details.get("available_capacity_kg"),
            "recovery_cost": round(rec.cost, 2),
            "cost_saving": round(ev.dedicated_cost - rec.cost, 2),
            "recovery_mode": "escalated" if sid in self.rejected else ev.recovery_mode,
            "deadline_met": rec.deadline_met, "reason": reason,
        }

    async def evaluate(self, db, sid: str) -> None:
        shipment = db.get(Shipment, sid)
        if shipment is None or shipment.status != "misplaced" or self.graph is None:
            self.evaluations.pop(sid, None)
            self.current.pop(sid, None)
            return
        ev = re_.evaluate_shipment(shipment, self.graph, self.routes, db=db)
        self.evaluations[sid] = ev
        if ev.best is None:
            return
        rec, reason = self._switch_decision(sid, ev)
        self.current[sid] = rec
        if reason:
            self.reasons[sid] = reason
        shipment.recovery_mode = "escalated" if sid in self.rejected else ev.recovery_mode
        db.commit()
        await emit_fleet("piggyback:recommendation",
                         self.recommendation_payload(sid, rec, ev, reason), shipment_id=sid)
        if ev.recovery_mode == "auto_executed" and sid not in self.rejected:
            await self._execute(db, shipment, ev.best, ev, "auto_executed", decided_by="system")
        elif simulation_auto_recovery() and ev.recovery_mode == "pending_approval":
            await self._execute(db, shipment, rec, ev, "pending_approval",
                                decided_by="simulation-auto-recovery")

    async def _execute(self, db, shipment, strategy, ev, mode, decided_by: str) -> dict:
        action = re_.execute_recovery(db, shipment, strategy, mode, ev.dedicated_cost)
        facts = decision_agent.fact_sheet(shipment, ev, strategy)
        decision_agent.log_decision(
            db, shipment.id, decision_agent.template_explanation(facts),
            decision_agent.summarize_risk(shipment, strategy, ev), confidence=strategy.score,
            operator_decision="approved" if mode != "auto_executed" else "auto_executed",
            operator_query=f"decided_by={decided_by}", recovery_action_id=action.id)
        self.current.pop(shipment.id, None)
        self.evaluations.pop(shipment.id, None)
        self.rejected.discard(shipment.id)
        await emit_fleet("recovery:started", {
            "shipment_id": shipment.id, "strategy": strategy.type,
            "vehicle_id": strategy.vehicle_id, "route": strategy.hubs,
            "legs": strategy.to_dict()["legs"], "mode": mode, "action_id": action.id,
            "system_initiated": mode == "auto_executed"}, shipment_id=shipment.id,
            vehicle_id=strategy.vehicle_id)
        return {"ok": True, "action_id": action.id}

    # ---- locked assignments ---------------------------------------------------------
    async def check_locked(self, db) -> None:
        """Unlock vehicle recoveries whose assigned vehicle can no longer pick up."""
        waiting = db.query(Shipment).filter(
            Shipment.recovery_strategy.in_(fleet_progress.VEHICLE_RECOVERIES),
            Shipment.current_hub_id.isnot(None),
            Shipment.status.in_(("piggybacked", "in_transit"))).all()
        for shipment in waiting:
            action = fleet_progress.active_action(db, shipment.id)
            legs = (action.recovery_route or {}).get("legs") if action else None
            if not legs:
                continue
            leg = next((lg for lg in legs if lg["from_hub"] == shipment.current_hub_id), None)
            if leg is None:
                continue
            vehicle = db.get(Vehicle, leg["vehicle_id"])
            remaining = vehicle.planned_route[vehicle.current_stop_index:] if vehicle else []
            offline = leg["vehicle_id"] in self.offline
            if vehicle is not None and not offline and shipment.current_hub_id in remaining:
                continue
            reason = (f"{leg['vehicle_id']} went offline" if offline else
                      f"{leg['vehicle_id']} no longer stops at {shipment.current_hub_id}")
            action.status = "failed"
            if vehicle is not None and legs.index(leg) == 0:
                fleet_progress._release(vehicle, shipment)
            shipment.status = "misplaced"
            shipment.recovery_strategy = None
            shipment.recovery_vehicle_id = None
            shipment.recovery_mode = None
            db.commit()
            await emit_fleet("shipment:alert", {
                "shipment_id": shipment.id, "type": "recovery_failed", "severity": "high",
                "priority": shipment.priority,
                "message": f"Locked recovery is no longer feasible: {reason}"},
                shipment_id=shipment.id)
            self.dirty.add(shipment.id)

    async def process(self) -> None:
        with SessionLocal() as db:
            await self.check_locked(db)
            dirty, self.dirty = self.dirty, set()
            for sid in dirty:
                try:
                    await self.evaluate(db, sid)
                except Exception:
                    db.rollback()
                    log.exception("Evaluation failed for %s", sid)
        linked: dict[str, set] = {}
        for sid, ev in self.evaluations.items():
            for c in ev.piggyback_candidates:
                for vid in c.vehicles:
                    linked.setdefault(vid, set()).add(sid)
        location_service.linked_shipments = linked

    async def run(self) -> None:
        while True:
            await asyncio.sleep(config.RECOMPUTE_INTERVAL_SECONDS)
            try:
                await self.process()
            except Exception:
                log.exception("Recommendation loop failed")

    # ---- operator actions ----------------------------------------------------------
    async def ensure_evaluation(self, db, sid: str) -> re_.Evaluation | None:
        if sid not in self.evaluations:
            await self.evaluate(db, sid)
        return self.evaluations.get(sid)

    async def approve(self, sid: str | None, strategy_id: str | None, user: str | None) -> dict:
        if not sid:
            return {"ok": False, "error": "shipment_id required"}
        with SessionLocal() as db:
            shipment = db.get(Shipment, sid)
            if shipment is None or shipment.status != "misplaced":
                return {"ok": False, "error": "shipment is not awaiting recovery"}
            ev = await self.ensure_evaluation(db, sid)
            if ev is None:
                return {"ok": False, "error": "no evaluation available"}
            strategy = ev.strategy(strategy_id) if strategy_id else self.current.get(sid, ev.best)
            if strategy is None or not strategy.feasible:
                return {"ok": False, "error": "strategy not found or not feasible"}
            return await self._execute(db, shipment, strategy, ev, "pending_approval",
                                       decided_by=user or "operator")

    async def reject(self, sid: str | None, reason: str, user: str | None) -> dict:
        if not sid:
            return {"ok": False, "error": "shipment_id required"}
        with SessionLocal() as db:
            shipment = db.get(Shipment, sid)
            if shipment is None:
                return {"ok": False, "error": "shipment not found"}
            rec = self.current.get(sid)
            shipment.recovery_mode = "escalated"
            db.commit()
            decision_agent.log_decision(
                db, sid, f"Operator rejected {rec.type if rec else 'recommendation'}: "
                         f"{reason or 'no reason given'}",
                None, confidence=rec.score if rec else None,
                operator_query=f"decided_by={user}", operator_decision="rejected")
        self.rejected.add(sid)
        await emit_fleet("shipment:alert", {
            "shipment_id": sid, "type": "escalated", "severity": "medium",
            "message": f"Recommendation rejected: {reason or 'no reason given'}"}, shipment_id=sid)
        return {"ok": True}

    def view(self, sid: str) -> dict | None:
        ev = self.evaluations.get(sid)
        if ev is None:
            return None
        data = ev.to_dict()
        rec = self.current.get(sid, ev.best)
        data["recommended"] = rec.to_dict() if rec else None
        data["recommendation_reason"] = self.reasons.get(sid)
        data["recovery_mode"] = "escalated" if sid in self.rejected else ev.recovery_mode
        return data


def simulation_auto_recovery() -> bool:
    from engines.simulation import simulation

    return simulation.auto_recovery


recommendation_loop = RecommendationLoop()
