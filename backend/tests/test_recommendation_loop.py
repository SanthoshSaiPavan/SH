"""Recommendation loop pieces that do not need Postgres: reasons, recovery cargo,
double-execution guard (K2) and fresh-evaluation approval (K4). The DB is faked."""
import asyncio
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from database.models import Shipment, Vehicle
from engines.recovery_engine import Evaluation, Strategy
from realtime import recommendation_loop as rl

NOW = datetime(2026, 9, 19, 8, 0)


def strat(kind, score, vehicle=None, feasible=True, pareto=False):
    return Strategy(id=f"{kind}:{vehicle}" if vehicle else kind, type=kind, feasible=feasible,
                    score=score, vehicle_id=vehicle, vehicles=[vehicle] if vehicle else [],
                    pareto=pareto, arrival_time=NOW + timedelta(hours=5))


def evaluation(sid, strategies, mode="pending_approval"):
    return Evaluation(sid, strategies, mode, [], 5000.0, NOW)


# ---- reason wording ------------------------------------------------------------------
def test_reason_initial_and_unchanged():
    a = strat("piggyback", 80, "T1")
    ev = evaluation("SHP-1", [a])
    assert rl.switch_reason(None, a, ev, set(), None) == "initial recommendation"
    assert rl.switch_reason(a, a, ev, set(), None) is None


def test_reason_infeasible_and_offline():
    old, new = strat("piggyback", 80, "T1"), strat("dedicated", 50)
    ev = evaluation("SHP-1", [new, strat("piggyback", 0, "T1", feasible=False)])
    assert rl.switch_reason(old, new, ev, set(), None).startswith(
        "T1 no longer has a feasible path")
    ev = evaluation("SHP-1", [new, strat("piggyback", 80, "T1")])
    assert rl.switch_reason(old, new, ev, {"T1"}, None) == \
        "T1 went offline; switched to dedicated"


def test_reason_margin_and_capacity():
    old, new = strat("piggyback", 60, "T1"), strat("piggyback", 70, "T2")
    ev = evaluation("SHP-1", [new, strat("piggyback", 60, "T1")])
    assert rl.switch_reason(old, new, ev, set(), None) == \
        "T2 scores 70.0 vs 60.0 for T1 (margin > 5)"
    assert rl.switch_reason(old, new, ev, set(), ("T1", "SHP-9", "critical")) == \
        "capacity on T1 assigned to SHP-9 (critical)"
    assert rl.switch_reason(None, new, ev, set(), ("T1", "SHP-9", "high")) == \
        "capacity on T1 assigned to SHP-9 (high)"


# ---- recovery cargo for the no-harm rule ------------------------------------------------
def _leg(vid, a, b):
    return {"vehicle_id": vid, "from_hub": a, "to_hub": b}


def test_recovery_cargo_only_for_final_leg_vehicle():
    deadline = NOW + timedelta(hours=10)
    final = SimpleNamespace(id="SHP-1", current_hub_id="H2", destination_hub_id="H3",
                            deadline=deadline, priority="high")
    transfer = SimpleNamespace(id="SHP-2", current_hub_id="H1", destination_hub_id="H3",
                               deadline=deadline, priority="low")
    legs = {"SHP-1": [_leg("T1", "H1", "H2"), _leg("T2", "H2", "H3")],
            "SHP-2": [_leg("T1", "H1", "H2"), _leg("T2", "H2", "H3")]}
    cargo = rl.recovery_cargo([final, transfer], legs)
    assert cargo == {"T2": [{"shipment_id": "SHP-1", "drop_hub": "H3", "deadline": deadline,
                             "priority": "high"}]}
    assert rl.recovery_cargo([final], {"SHP-1": None}) == {}


def test_merge_cargo():
    a = {"T1": [{"shipment_id": "S1"}]}
    b = {"T1": [{"shipment_id": "S2"}], "T2": [{"shipment_id": "S3"}]}
    assert rl.merge_cargo(a, b) == {"T1": [{"shipment_id": "S1"}, {"shipment_id": "S2"}],
                                    "T2": [{"shipment_id": "S3"}]}


# ---- fake DB -------------------------------------------------------------------------
class FakeDB:
    def __init__(self, shipments, vehicles):
        self.rows = {Shipment: shipments, Vehicle: vehicles}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, model, key):
        return self.rows[model].get(key)

    def commit(self):
        pass

    def rollback(self):
        pass


@pytest.fixture
def world(monkeypatch):
    shipment = SimpleNamespace(id="SHP-1", status="misplaced", recovery_strategy=None,
                               current_vehicle_id=None, weight_kg=100.0, volume_cbm=1.0,
                               priority="critical")
    vehicles = {"T1": SimpleNamespace(id="T1", total_capacity_kg=1000.0, used_capacity_kg=0.0,
                                      total_capacity_cbm=20.0, used_capacity_cbm=0.0)}
    calls = []

    def execute_recovery(db, s, strategy, mode, dedicated_cost):
        time.sleep(0.05)  # widen the race window
        calls.append((s.id, strategy.id, mode))
        s.recovery_strategy, s.status = strategy.type, "piggybacked"
        return SimpleNamespace(id=f"RA-{len(calls)}")

    async def emit(*args, **kwargs):
        pass

    monkeypatch.setattr(rl, "SessionLocal", lambda: FakeDB({"SHP-1": shipment}, vehicles))
    monkeypatch.setattr(rl.re_, "execute_recovery", execute_recovery)
    monkeypatch.setattr(rl.decision_agent, "fact_sheet", lambda *a, **k: {})
    monkeypatch.setattr(rl.decision_agent, "template_explanation", lambda *a, **k: "")
    monkeypatch.setattr(rl.decision_agent, "summarize_risk", lambda *a, **k: {})
    monkeypatch.setattr(rl.decision_agent, "log_decision", lambda *a, **k: None)
    monkeypatch.setattr(rl, "emit_fleet", emit)
    return SimpleNamespace(shipment=shipment, vehicles=vehicles, calls=calls,
                           loop=rl.RecommendationLoop())


async def test_concurrent_executions_run_once(world):
    s = strat("piggyback", 90, "T1")
    ev = evaluation("SHP-1", [s], mode="auto_executed")
    results = await asyncio.gather(
        world.loop._execute("SHP-1", s, ev, "auto_executed", "system"),
        world.loop._execute("SHP-1", s, ev, "pending_approval", "operator"))
    assert len(world.calls) == 1
    assert sorted(r["ok"] for r in results) == [False, True]
    assert {"ok": False, "error": "already being recovered"} in results


async def test_approve_racing_auto_execution_runs_once(world, monkeypatch):
    s = strat("piggyback", 90, "T1")
    ev = evaluation("SHP-1", [s], mode="auto_executed")

    def fresh(sids, graph, routes, rejected, persist=True):
        return {sid: evaluation(sid, [strat("piggyback", 90, "T1")])
                if world.shipment.status == "misplaced" else None for sid in sids}

    monkeypatch.setattr(rl, "_evaluate_sync", fresh)
    world.loop.graph = object()
    results = await asyncio.gather(
        world.loop._execute("SHP-1", s, ev, "auto_executed", "system"),
        world.loop.approve("SHP-1", "piggyback:T1", "op"))
    assert len(world.calls) == 1
    assert [r["ok"] for r in results] == [True, False]


async def test_approve_refuses_strategy_no_longer_feasible(world, monkeypatch):
    monkeypatch.setattr(rl, "_evaluate_sync", lambda sids, *a, **k: {
        "SHP-1": evaluation("SHP-1", [strat("dedicated", 50),
                                      strat("piggyback", 0, "T1", feasible=False)])})
    world.loop.graph = object()
    assert await world.loop.approve("SHP-1", "piggyback:T1", "op") == \
        {"ok": False, "error": "strategy no longer feasible"}
    assert await world.loop.approve("SHP-1", "piggyback:T9", "op") == \
        {"ok": False, "error": "strategy no longer feasible"}
    assert world.calls == []


async def test_approve_refuses_when_vehicle_lacks_capacity(world, monkeypatch):
    monkeypatch.setattr(rl, "_evaluate_sync", lambda sids, *a, **k: {
        "SHP-1": evaluation("SHP-1", [strat("piggyback", 80, "T1")])})
    world.loop.graph = object()
    world.vehicles["T1"].used_capacity_kg = 950.0
    result = await world.loop.approve("SHP-1", "piggyback:T1", "op")
    assert result == {"ok": False, "error": "T1 lacks capacity for SHP-1"}
    assert world.calls == []


async def test_execution_marks_other_misplaced_dirty(world, monkeypatch):
    monkeypatch.setattr(rl, "_evaluate_sync", lambda sids, *a, **k: {
        "SHP-1": evaluation("SHP-1", [strat("piggyback", 80, "T1")])})
    world.loop.graph = object()
    world.loop.evaluations["SHP-2"] = evaluation("SHP-2", [strat("dedicated", 50)])
    world.loop.misplaced_pos = {"SHP-1": (17.0, 78.0), "SHP-3": (17.0, 79.0)}
    result = await world.loop.approve("SHP-1", None, "op")
    assert result["ok"] and world.calls == [("SHP-1", "piggyback:T1", "pending_approval")]
    assert world.loop.dirty == {"SHP-2", "SHP-3"}


# ---- cycle: the assigned option is what gets published and auto-executed ----------------
async def test_cycle_auto_executes_assigned_option_only_if_it_is_best(world, monkeypatch):
    best, other = strat("piggyback", 90, "T1"), strat("dedicated", 50)
    ev = evaluation("SHP-1", [best, other], mode="auto_executed")
    sent = []

    async def emit(event, payload, **kwargs):
        sent.append((event, payload))

    monkeypatch.setattr(rl, "emit_fleet", emit)
    monkeypatch.setattr(rl, "_evaluate_sync", lambda sids, *a, **k: {"SHP-1": ev})
    info = {"SHP-1": {"priority": "critical", "weight_kg": 100.0, "volume_cbm": 1.0}}
    monkeypatch.setattr(rl, "_assign_sync", lambda *a: (
        info, {"SHP-1": other}, {"SHP-1": ("T1", "SHP-7", "critical")}))
    world.loop.graph = object()
    await world.loop._cycle({"SHP-1"})
    assert world.calls == []
    (event, payload), = sent
    assert event == "piggyback:recommendation"
    assert payload["strategy_id"] == "dedicated"
    assert payload["recovery_mode"] == "pending_approval"
    assert payload["reason"] == "capacity on T1 assigned to SHP-7 (critical)"
    assert "on_time_probability" in payload and "pareto_label" in payload

    monkeypatch.setattr(rl, "_assign_sync", lambda *a: (info, {"SHP-1": best}, {}))
    await world.loop._cycle({"SHP-1"})
    assert world.calls == [("SHP-1", "piggyback:T1", "auto_executed")]
