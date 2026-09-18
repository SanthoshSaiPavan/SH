"""Level-up engine tests: no-harm rule, live-leg detours, P(on-time), Pareto, sensitivity."""
from datetime import timedelta

import pytest

import config
from database.seed_data import build_seed
from engines import graph_network as gn
from engines import piggyback_matcher as pm
from engines import recovery_engine as re_
from engines.on_time import on_time_probability
from utils import clock


@pytest.fixture()
def world():
    hubs, routes, vehicles, shipments, _ = build_seed()
    return {
        "hubs": {h.id: h for h in hubs}, "routes": routes,
        "vehicles": {v.id: v for v in vehicles},
        "shipments": {s.id: s for s in shipments}, "now": clock.now(),
    }


def graph_for(world, protect=True, vehicles=None, **kw):
    if protect:
        kw["cargo_aboard"] = gn.cargo_aboard_from(world["shipments"].values())
    return gn.build_time_expanded_graph(world["hubs"], vehicles or list(world["vehicles"].values()),
                                        world["routes"], world["now"], **kw)


def evaluate(world, graph=None):
    s = world["shipments"]["SHP-501"]
    return re_.evaluate_shipment(s, graph or graph_for(world), world["routes"], now=world["now"])


# ---- no-harm rule ------------------------------------------------------------
def test_cargo_aboard_from_seed(world):
    aboard = gn.cargo_aboard_from(world["shipments"].values())
    assert [c["shipment_id"] for c in aboard["TRUCK-102"]] == ["SHP-311"]
    assert aboard["TRUCK-102"][0]["drop_hub"] == "HUB-VJA-01"
    world["shipments"]["SHP-311"].status = "misplaced"  # being rescued: not protected
    assert "TRUCK-102" not in gn.cargo_aboard_from(world["shipments"].values())


def test_truck_102_rejected_for_shp_311(world):
    ev = evaluate(world)
    assert "piggyback:TRUCK-102" not in [s.id for s in ev.strategies]
    [rej] = [r for r in ev.rejected_options if r["vehicle_id"] == "TRUCK-102"]
    assert rej["detour_hub"] == "HUB-WGL-01"
    [victim] = rej["victims"]
    assert victim["shipment_id"] == "SHP-311" and victim["priority"] == "critical"
    assert victim["late_hours"] > 0
    assert rej["reason"].startswith("Detour to HUB-WGL-01 makes SHP-311 (critical)")


def test_without_cargo_truck_102_detours_live_at_warangal(world):
    g = graph_for(world, protect=False)
    assert g.graph["rejected_detours"] == []
    assert ("arr", "TRUCK-102", "1p", "detour:live:HUB-WGL-01") in g
    candidates = pm.find_piggyback_matches(world["shipments"]["SHP-501"], g, world["now"])
    t102 = next(c for c in candidates if c.vehicle_id == "TRUCK-102")
    assert t102.hubs == ["HUB-WGL-01", "HUB-VJA-01"]
    assert t102.arrival_time < world["shipments"]["SHP-501"].deadline


def test_harmful_detours_recorded_and_kept_when_not_enforced(world):
    key = ("TRUCK-102", "detour:live:HUB-WGL-01")
    enforced = graph_for(world)
    assert [v["shipment_id"] for v in enforced.graph["harmful_detours"][key]] == ["SHP-311"]
    assert ("arr", "TRUCK-102", "1p", key[1]) not in enforced
    g = graph_for(world, enforce_no_harm=False)
    assert g.graph["rejected_detours"] == []
    assert g.graph["harmful_detours"][key] == enforced.graph["harmful_detours"][key]
    assert ("arr", "TRUCK-102", "1p", key[1]) in g


def test_legs_carry_their_variant(world):
    g = graph_for(world, enforce_no_harm=False)
    candidates = pm.find_piggyback_matches(world["shipments"]["SHP-501"], g, world["now"])
    by_vehicle = {c.vehicle_id: c for c in candidates}
    [leg] = by_vehicle["TRUCK-102"].legs
    assert leg["variant"] == "detour:live:HUB-WGL-01"
    assert (leg["vehicle_id"], leg["variant"]) in g.graph["harmful_detours"]
    assert all(leg["variant"] == "main" for leg in by_vehicle["TRUCK-104"].legs)


def test_harmless_detour_is_kept(world):
    world["shipments"]["SHP-311"].deadline += timedelta(hours=24)  # plenty of slack
    g = graph_for(world)
    assert not any(r["vehicle_id"] == "TRUCK-102" for r in g.graph["rejected_detours"])
    assert ("arr", "TRUCK-102", "1p", "detour:live:HUB-WGL-01") in g


def test_already_late_cargo_is_not_harmed(world):
    world["shipments"]["SHP-311"].deadline = world["now"] + timedelta(minutes=5)
    g = graph_for(world)
    assert ("arr", "TRUCK-102", "1p", "detour:live:HUB-WGL-01") in g


def test_hub_behind_vehicle_is_not_a_live_detour(world):
    v = world["vehicles"]["TRUCK-102"]
    wgl = world["hubs"]["HUB-WGL-01"]
    vja = world["hubs"]["HUB-VJA-01"]
    v.current_lat = wgl.lat + (vja.lat - wgl.lat) * 0.3  # already past Warangal
    v.current_lng = wgl.lng + (vja.lng - wgl.lng) * 0.3
    g = graph_for(world, protect=False)
    assert not any(n[0] == "arr" and n[1] == "TRUCK-102" and n[3] != "main" for n in g)


def test_detour_chains_keep_invariants(world):
    g = graph_for(world, protect=False)
    buffer = timedelta(minutes=config.HANDLING_BUFFER_MINUTES)
    detour_nodes = [n for n, d in g.nodes(data=True) if d.get("detour")]
    assert detour_nodes and all(n[3].startswith("detour:") for n in detour_nodes)
    for u, v, d in g.edges(data=True):
        if d["kind"] == "board":
            assert g.nodes[u]["time"] >= world["now"]
            assert g.nodes[v]["time"] - g.nodes[u]["time"] == buffer
        if d["kind"] in ("leg", "wait", "onboard"):
            assert g.nodes[v]["time"] >= g.nodes[u]["time"]
        if d["kind"] in ("leg", "onboard", "board", "unload"):
            end = v if d["kind"] != "unload" else u
            assert d["detour"] == bool(g.nodes[end].get("detour"))


def test_hold_never_uses_a_detour_chain(world):
    g = graph_for(world, protect=False)
    s = world["shipments"]["SHP-501"]
    hold = re_.hold_strategy(s, g, world["now"])
    assert hold.feasible and hold.vehicle_id == "TRUCK-104"
    # Only TRUCK-102's detour reaches VJA from WGL faster, and hold must not take it.
    assert all(leg["vehicle_id"] != "TRUCK-102" for leg in hold.legs)
    assert hold.vehicles == ["TRUCK-104"]


# ---- P(on-time) ------------------------------------------------------------------
def _vehicle_strategy(now, dep_h, arr_h, sid="piggyback:X"):
    leg = {"vehicle_id": "X", "departure_time": now + timedelta(hours=dep_h),
           "arrival_time": now + timedelta(hours=arr_h)}
    return re_.Strategy(id=sid, type="piggyback", feasible=True, arrival_time=leg["arrival_time"],
                        legs=[leg])


def test_on_time_probability_bounds_and_determinism(world):
    s, now = world["shipments"]["SHP-501"], world["now"]
    st = _vehicle_strategy(now, 1, 5)
    s.deadline = now + timedelta(hours=100)
    assert on_time_probability(st, s, now) > 0.99
    s.deadline = now + timedelta(hours=2)
    assert on_time_probability(st, s, now) == 0.0
    s.deadline = now + timedelta(hours=5.5)
    p = on_time_probability(st, s, now)
    assert 0.0 <= p <= 1.0 and p == on_time_probability(st, s, now)
    assert "arrival_p90" in st.details
    assert on_time_probability(re_.Strategy(id="hold", type="hold", feasible=False), s, now) == 0.0


def test_missed_transfer_counts_as_late(world):
    s, now = world["shipments"]["SHP-501"], world["now"]
    s.deadline = now + timedelta(hours=100)
    legs = [{"vehicle_id": "A", "departure_time": now + timedelta(hours=1),
             "arrival_time": now + timedelta(hours=5)},
            {"vehicle_id": "B", "departure_time": now + timedelta(hours=4),  # leaves before A lands
             "arrival_time": now + timedelta(hours=8)}]
    st = re_.Strategy(id="piggyback:A", type="piggyback", feasible=True,
                      arrival_time=legs[-1]["arrival_time"], legs=legs)
    assert on_time_probability(st, s, now) < 0.05


def test_strategies_carry_on_time_probability(world):
    ev = evaluate(world)
    for st in ev.strategies:
        assert 0.0 <= st.on_time_probability <= 1.0
        if st.feasible:
            assert st.scores["time"] == st.on_time_probability
    assert evaluate(world).best.on_time_probability == ev.best.on_time_probability


# ---- Pareto + sensitivity ---------------------------------------------------------
def test_pareto_labels(world):
    ev = evaluate(world)
    feasible = [s for s in ev.strategies if s.feasible]
    front = [s for s in feasible if s.pareto]
    assert ev.best.pareto
    for s in front:
        assert not any(o.cost <= s.cost and o.arrival_time <= s.arrival_time
                       and (o.cost < s.cost or o.arrival_time < s.arrival_time) for o in feasible)
    by_label = {s.pareto_label: s for s in front if s.pareto_label}
    assert by_label["cheapest"].cost == min(s.cost for s in front)
    if "fastest" in by_label:
        assert by_label["fastest"].arrival_time == min(s.arrival_time for s in front)
    opts = ev.pareto_options
    assert [o["strategy_id"] for o in opts] and opts[0]["tradeoff"] == "cheapest option"
    assert {o["strategy_id"] for o in opts} == {s.id for s in front}


def test_sensitivity_structure(world):
    ev = evaluate(world)
    sens = ev.sensitivity
    assert sens["step"] == config.SENSITIVITY_STEP
    assert len(sens["checks"]) == 2 * len(ev.weights)
    for comp in ev.weights:
        assert sorted(c["change"] for c in sens["checks"] if c["component"] == comp) == \
            [-config.SENSITIVITY_STEP, config.SENSITIVITY_STEP]
    assert sens["stable"] == all(c["recommended_id"] == ev.best.id for c in sens["checks"])
    front_ids = {s.id for s in ev.strategies if s.pareto}
    assert all(c["recommended_id"] in front_ids for c in sens["checks"])


def test_auto_execute_needs_on_time_probability(world):
    s = world["shipments"]["SHP-501"]
    s.priority = "critical"
    mk = lambda p: re_.Strategy(id="piggyback:X", type="piggyback", feasible=True,  # noqa: E731
                                score=90, on_time_probability=p)
    assert re_.determine_recovery_mode(s, [mk(0.97)]) == "auto_executed"
    assert re_.determine_recovery_mode(s, [mk(0.90)]) == "pending_approval"
