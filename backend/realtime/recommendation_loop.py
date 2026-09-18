"""Throttled re-evaluation and joint assignment of misplaced shipments.

Vehicle movement marks nearby misplaced shipments dirty; every
RECOMPUTE_INTERVAL_SECONDS dirty shipments are re-run through Modules 2→3, then all
misplaced shipments are assigned together (engines.assignment) so no vehicle is
recommended beyond its remaining capacity. A recommendation only switches when another
option beats it by SWITCH_MARGIN, the current one is no longer feasible, or its capacity
went to a higher-value shipment. Approved or auto-executed recoveries are locked until
they complete or become infeasible.

Graph builds, evaluations, assignment and executions run in worker threads, each with its
own session; loop state is only mutated on the event loop. Execution is serialised per
shipment and re-checks the shipment in a fresh session, so it can never run twice.
"""
from __future__ import annotations

import asyncio
import logging

import config
from database.db import SessionLocal
from database.models import Hub, Route, Shipment, Vehicle
from engines import assignment, decision_agent, fleet_progress
from engines import graph_network as gn
from engines import recovery_engine as re_
from engines.assignment import identity as _identity
from realtime.location_service import location_service
from realtime.socket_server import emit_fleet
from utils import clock
from utils.geo import haversine

log = logging.getLogger(__name__)
_EPS = 1e-9


def _label(strategy: re_.Strategy) -> str:
    return strategy.vehicle_id or strategy.type


def recovery_cargo(shipments, legs_by_sid: dict) -> dict:
    """Recovery shipments waiting at a hub for the vehicle that carries their final leg,
    as graph `cargo_aboard` entries keyed by that vehicle."""
    out: dict = {}
    for s in shipments:
        legs = legs_by_sid.get(s.id) or []
        leg = next((lg for lg in legs if lg["from_hub"] == s.current_hub_id), None)
        if leg is None or legs[-1]["vehicle_id"] != leg["vehicle_id"]:
            continue
        out.setdefault(leg["vehicle_id"], []).append(
            {"shipment_id": s.id, "drop_hub": s.destination_hub_id, "deadline": s.deadline,
             "priority": s.priority})
    return out


def merge_cargo(*parts: dict) -> dict:
    merged: dict = {}
    for part in parts:
        for vid, items in part.items():
            merged.setdefault(vid, []).extend(items)
    return merged


def switch_reason(cur, new, ev, offline: set, displaced: tuple | None) -> str | None:
    """Why the recommendation is `new` instead of `cur`; None if it did not change.
    `displaced` = (vehicle_id, other_sid, other_priority) when capacity decided it."""
    capacity = (f"capacity on {displaced[0]} assigned to {displaced[1]} ({displaced[2]})"
                if displaced else None)
    if cur is None:
        return capacity or "initial recommendation"
    if _identity(new) == _identity(cur):
        return None
    same = next((s for s in ev.strategies if _identity(s) == _identity(cur) and s.feasible),
                None)
    if same is None or cur.vehicle_id in offline:
        why = ("went offline" if cur.vehicle_id in offline else
               "no longer has a feasible path (rerouted, lost capacity or missed the "
               "pickup window)")
        return f"{_label(cur)} {why}; switched to {_label(new)}"
    if capacity:
        return capacity
    if new.score > same.score + config.SWITCH_MARGIN:
        return (f"{_label(new)} scores {new.score:.1f} vs {same.score:.1f} for {_label(cur)} "
                f"(margin > {config.SWITCH_MARGIN:.0f})")
    return f"{_label(new)} preferred over {_label(cur)} (Pareto front changed)"


def lacking_capacity(db, shipment, strategy) -> str | None:
    """First vehicle of `strategy` without room for `shipment` right now (DB total − used)."""
    vids = strategy.vehicles or ([strategy.vehicle_id] if strategy.vehicle_id
                                 and strategy.type in fleet_progress.VEHICLE_RECOVERIES else [])
    for vid in dict.fromkeys(vids):
        v = db.get(Vehicle, vid)
        if v is None:
            return vid
        aboard = shipment.current_vehicle_id == vid  # released when the recovery detaches it
        kg = v.total_capacity_kg - v.used_capacity_kg + (shipment.weight_kg if aboard else 0.0)
        cbm = v.total_capacity_cbm - v.used_capacity_cbm + (shipment.volume_cbm if aboard else 0.0)
        if kg + _EPS < shipment.weight_kg or cbm + _EPS < shipment.volume_cbm:
            return vid
    return None


def _execute_sync(sid: str, strategy, ev, mode: str, decided_by: str) -> dict:
    with SessionLocal() as db:
        shipment = db.get(Shipment, sid)
        if shipment is None or shipment.status != "misplaced" \
                or shipment.recovery_strategy is not None:
            return {"ok": False, "error": "already being recovered"}
        short = lacking_capacity(db, shipment, strategy)
        if short:
            return {"ok": False, "error": f"{short} lacks capacity for {sid}"}
        action = re_.execute_recovery(db, shipment, strategy, mode, ev.dedicated_cost)
        facts = decision_agent.fact_sheet(shipment, ev, strategy)
        decision_agent.log_decision(
            db, sid, decision_agent.template_explanation(facts),
            decision_agent.summarize_risk(shipment, strategy, ev), confidence=strategy.score,
            operator_decision="approved" if mode != "auto_executed" else "auto_executed",
            operator_query=f"decided_by={decided_by}", recovery_action_id=action.id)
        return {"ok": True, "action_id": action.id}


def _evaluate_sync(sids, graph, routes, rejected: frozenset, persist: bool = True) -> dict:
    """{sid: Evaluation, or None if the shipment is no longer misplaced}."""
    out = {}
    with SessionLocal() as db:
        for sid in sids:
            try:
                shipment = db.get(Shipment, sid)
                if shipment is None or shipment.status != "misplaced":
                    out[sid] = None
                    continue
                ev = re_.evaluate_shipment(shipment, graph, routes, db=db)
                if persist:
                    shipment.recovery_mode = "escalated" if sid in rejected else ev.recovery_mode
                    db.commit()
                out[sid] = ev
            except Exception:
                db.rollback()
                log.exception("Evaluation failed for %s", sid)
    return out


def _assign_sync(evaluations: dict, current: dict, offline: frozenset):
    """Joint assignment over the evaluated shipments that are still misplaced.
    Returns (shipment info, {sid: Strategy | None}, {sid: displaced tuple})."""
    with SessionLocal() as db:
        rows = db.query(Shipment).filter(Shipment.id.in_(list(evaluations)),
                                         Shipment.status == "misplaced").all()
        vehicles = db.query(Vehicle).all()
    info = {s.id: {"priority": s.priority, "weight_kg": s.weight_kg,
                   "volume_cbm": s.volume_cbm} for s in rows}
    capacity = {v.id: (max(0.0, v.total_capacity_kg - v.used_capacity_kg),
                       max(0.0, v.total_capacity_cbm - v.used_capacity_cbm))
                for v in vehicles if v.id not in offline}
    options = {sid: [s for s in evaluations[sid].strategies if s.feasible] for sid in info}
    chosen = assignment.assign(info, options, capacity, current)
    displaced = {}
    for sid in info:
        want = assignment.preferred(options[sid], info[sid]["priority"], current.get(sid),
                                    capacity)
        if _identity(want) != _identity(chosen[sid]):
            hit = assignment.displaced_by(sid, want, chosen, info, capacity)
            if hit:
                displaced[sid] = (hit[0], hit[1], info[hit[1]]["priority"])
    return info, chosen, displaced


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
        self.locks: dict[str, asyncio.Lock] = {}
        self.cycle_lock = asyncio.Lock()
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

    @staticmethod
    def _build(positions: dict, offline: frozenset) -> dict:
        with SessionLocal() as db:
            hubs = {h.id: h for h in db.query(Hub).all()}
            vehicles = db.query(Vehicle).all()
            routes = db.query(Route).all()
            aboard = db.query(Shipment).filter(Shipment.current_vehicle_id.isnot(None)).all()
            hazmat: dict = {}
            for s in aboard:
                classes = {f for f in (s.handling_flags or []) if f.startswith(gn.HAZMAT_PREFIX)}
                if classes:
                    hazmat.setdefault(s.current_vehicle_id, set()).update(classes)
            waiting = db.query(Shipment).filter(
                Shipment.recovery_strategy.in_(fleet_progress.VEHICLE_RECOVERIES),
                Shipment.current_hub_id.isnot(None),
                Shipment.status.in_(("piggybacked", "in_transit"))).all()
            legs = {}
            for s in waiting:
                action = fleet_progress.active_action(db, s.id)
                legs[s.id] = (action.recovery_route or {}).get("legs") if action else None
            misplaced = db.query(Shipment).filter_by(status="misplaced").all()
        cargo = merge_cargo(gn.cargo_aboard_from(aboard), recovery_cargo(waiting, legs))
        graph = gn.build_time_expanded_graph(hubs, vehicles, routes, clock.now(),
                                             live_positions=positions,
                                             exclude_vehicle_ids=set(offline),
                                             cargo_hazmat=hazmat, cargo_aboard=cargo)
        return {
            "graph": graph, "routes": routes,
            "vehicle_paths": {
                v.id: [positions.get(v.id, (v.current_lat, v.current_lng))]
                + [(hubs[h].lat, hubs[h].lng) for h in v.planned_route[v.current_stop_index:]]
                for v in vehicles},
            "misplaced_pos": {s.id: (s.current_lat, s.current_lng) for s in misplaced
                              if s.current_lat is not None},
            "misplaced": [s.id for s in misplaced],
        }

    async def rebuild(self, positions: dict, offline: set) -> None:
        """Called every engine tick: fresh graph + caches used for dirty marking.
        The graph is built off the loop and swapped in whole."""
        state = await asyncio.to_thread(self._build, positions, frozenset(offline))
        self.offline = set(offline)
        self.graph, self.routes = state["graph"], state["routes"]
        self.vehicle_paths, self.misplaced_pos = state["vehicle_paths"], state["misplaced_pos"]
        for sid in state["misplaced"]:
            if sid not in self.evaluations:
                self.dirty.add(sid)

    # ---- evaluation + joint assignment ----------------------------------------------
    def _mode(self, sid: str, ev: re_.Evaluation, rec: re_.Strategy | None) -> str:
        if sid in self.rejected:
            return "escalated"
        if ev.recovery_mode == "auto_executed" and _identity(rec) != _identity(ev.best):
            return "pending_approval"  # capacity moved it off the option auto-mode judged
        return ev.recovery_mode

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
            "recovery_mode": self._mode(sid, ev, rec),
            "deadline_met": rec.deadline_met, "reason": reason,
            "on_time_probability": round(rec.on_time_probability, 3),
            "pareto_label": rec.pareto_label,
        }

    async def _cycle(self, sids) -> None:
        """Re-evaluate `sids`, assign all evaluated shipments, publish, then execute."""
        to_execute = []
        async with self.cycle_lock:
            graph, routes = self.graph, self.routes
            evaluated: set = set()
            if sids and graph is None:
                self.dirty.update(sids)
            elif sids:
                evs = await asyncio.to_thread(_evaluate_sync, sorted(sids), graph, routes,
                                              frozenset(self.rejected))
                for sid, ev in evs.items():
                    if ev is None:
                        self.evaluations.pop(sid, None)
                        self.current.pop(sid, None)
                    else:
                        self.evaluations[sid] = ev
                        evaluated.add(sid)
            if not self.evaluations:
                return
            snapshot = dict(self.evaluations)
            current = {sid: _identity(s) for sid, s in self.current.items()}
            info, chosen, displaced = await asyncio.to_thread(
                _assign_sync, snapshot, current, frozenset(self.offline))
            for sid in sorted(snapshot):
                ev = snapshot[sid]
                if self.evaluations.get(sid) is not ev:
                    continue  # executed or re-evaluated meanwhile
                if sid not in info:
                    self.evaluations.pop(sid, None)
                    self.current.pop(sid, None)
                    continue
                rec = chosen.get(sid)
                if rec is None and ev.best is not None and not ev.best.feasible:
                    rec = ev.best  # nothing feasible: show the escalation
                if rec is None:
                    self.current.pop(sid, None)
                    continue
                reason = switch_reason(self.current.get(sid), rec, ev, self.offline,
                                       displaced.get(sid))
                self.current[sid] = rec
                if reason:
                    self.reasons[sid] = reason
                if reason or sid in evaluated:
                    await emit_fleet("piggyback:recommendation",
                                     self.recommendation_payload(sid, rec, ev, reason),
                                     shipment_id=sid)
                if sid in evaluated and rec.feasible:
                    to_execute.append((sid, rec, ev))
        for sid, rec, ev in to_execute:
            if ev.recovery_mode == "auto_executed" and sid not in self.rejected \
                    and _identity(rec) == _identity(ev.best):
                result = await self._execute(sid, rec, ev, "auto_executed", decided_by="system")
            elif simulation_auto_recovery() and ev.recovery_mode == "pending_approval":
                result = await self._execute(sid, rec, ev, "pending_approval",
                                             decided_by="simulation-auto-recovery")
            else:
                continue
            if not result.get("ok"):
                log.info("Automatic execution for %s skipped: %s", sid, result.get("error"))

    # ---- execution -----------------------------------------------------------------
    def _lock(self, sid: str) -> asyncio.Lock:
        return self.locks.setdefault(sid, asyncio.Lock())

    async def _execute(self, sid: str, strategy, ev, mode: str, decided_by: str) -> dict:
        async with self._lock(sid):
            return await self._execute_locked(sid, strategy, ev, mode, decided_by)

    async def _execute_locked(self, sid: str, strategy, ev, mode: str, decided_by: str) -> dict:
        result = await asyncio.to_thread(_execute_sync, sid, strategy, ev, mode, decided_by)
        if not result.get("ok"):
            return result
        self.current.pop(sid, None)
        self.evaluations.pop(sid, None)
        self.rejected.discard(sid)
        # The capacity just consumed changes every other shipment's assignment.
        self.dirty.update(s for s in set(self.evaluations) | set(self.misplaced_pos) if s != sid)
        await emit_fleet("recovery:started", {
            "shipment_id": sid, "strategy": strategy.type,
            "vehicle_id": strategy.vehicle_id, "route": strategy.hubs,
            "legs": strategy.to_dict()["legs"], "mode": mode, "action_id": result["action_id"],
            "system_initiated": mode == "auto_executed"}, shipment_id=sid,
            vehicle_id=strategy.vehicle_id)
        return result

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
        await self._cycle(dirty)
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
        """`db` is unused (kept for callers): evaluation runs in a worker thread."""
        if sid not in self.evaluations:
            await self._cycle({sid})
        return self.evaluations.get(sid)

    async def approve(self, sid: str | None, strategy_id: str | None, user: str | None) -> dict:
        """Execute against a fresh evaluation on the current graph, never a cached one."""
        if not sid:
            return {"ok": False, "error": "shipment_id required"}
        graph, routes = self.graph, self.routes
        if graph is None:
            return {"ok": False, "error": "no evaluation available"}
        async with self._lock(sid):
            evs = await asyncio.to_thread(_evaluate_sync, [sid], graph, routes,
                                          frozenset(self.rejected), False)
            ev = evs.get(sid)
            if ev is None:
                return {"ok": False, "error": "shipment is not awaiting recovery"}
            self.evaluations[sid] = ev
            cur = self.current.get(sid)
            strategy = (ev.strategy(strategy_id) if strategy_id else
                        next((s for s in ev.strategies if s.feasible
                              and _identity(s) == _identity(cur)), ev.best))
            if strategy is None or not strategy.feasible:
                self.dirty.add(sid)
                return {"ok": False, "error": "strategy no longer feasible"}
            return await self._execute_locked(sid, strategy, ev, "pending_approval",
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
        data["recovery_mode"] = self._mode(sid, ev, rec)
        return data


def simulation_auto_recovery() -> bool:
    from engines.simulation import simulation

    return simulation.auto_recovery


recommendation_loop = RecommendationLoop()
