"""Engine tests on in-memory seed objects (no database needed)."""
from datetime import timedelta

import pytest

import config
from database.seed_data import build_seed
from engines import anomaly_detector as ad
from engines import graph_network as gn
from engines import piggyback_matcher as pm
from engines import recovery_engine as re_
from utils import clock
from utils.geo import haversine, point_to_line_distance
from utils.scoring import inverse_normalize, normalize, weighted_score


@pytest.fixture()
def world():
    hubs, routes, vehicles, shipments, _ = build_seed()
    now = clock.now()
    return {
        "hubs": {h.id: h for h in hubs}, "routes": routes,
        "vehicles": {v.id: v for v in vehicles},
        "shipments": {s.id: s for s in shipments}, "now": now,
    }


def graph_for(world, **kw):
    return gn.build_time_expanded_graph(world["hubs"], list(world["vehicles"].values()),
                                        world["routes"], world["now"], **kw)


# ---- utils -----------------------------------------------------------------
def test_haversine_delhi_mumbai():
    assert 1140 < haversine(28.6139, 77.2090, 19.0760, 72.8777) < 1160


def test_point_to_line_distance_on_and_off_segment():
    assert point_to_line_distance((17.0, 78.5), (17.0, 78.0), (17.0, 79.0)) < 0.01
    assert 100 < point_to_line_distance((18.0, 78.5), (17.0, 78.0), (17.0, 79.0)) < 115


def test_scoring_helpers():
    assert normalize(5, 0, 10) == 0.5
    assert normalize(20, 0, 10) == 1.0
    assert inverse_normalize(0, 0, 10) == 1.0
    assert weighted_score({"a": 1.0, "b": 0.0}, {"a": 0.6, "b": 0.4}) == 60.0
    assert weighted_score({"a": 2.0}, {"a": 1.0}) == 100.0  # clamped


# ---- Module 1 ------------------------------------------------------------------
def test_seed_only_flags_scripted_shipment(world):
    results = ad.detect_anomalies(world["shipments"].values(), world["hubs"], world["now"],
                                  vehicles=world["vehicles"])
    assert [(r.shipment_id, r.misplacement_type) for r in results] == [("SHP-501", "wrong_hub")]
    assert results[0].reason.startswith("Excess at hub: scanned at HUB-WGL-01")


def test_scan_gap_flags_idle_shipment_at_hub(world):
    s = world["shipments"]["SHP-501"]
    s.current_hub_id = "HUB-HYD-01"
    s.actual_route = ["HUB-HYD-01"]
    s.last_scan_at = world["now"] - timedelta(hours=config.MAX_SCAN_GAP_HOURS + 1)
    result = ad.detect_shipment(s, world["hubs"], world["now"])
    assert result is not None and result.misplacement_type == "stuck"


def test_manifest_mismatch_flags_wrong_vehicle(world):
    from engines.fleet_progress import record_scan

    s = world["shipments"]["SHP-311"]  # manifested on TRUCK-102, next hub HUB-VJA-01
    record_scan(s, "load", world["now"], "HUB-MUM-01", "VEH-VAN-0011")  # Mumbai–Pune shuttle
    result = ad.detect_shipment(s, world["hubs"], world["now"], world["vehicles"])
    assert result is not None and result.misplacement_type == "wrong_vehicle"
    assert result.reason.startswith("Manifest mismatch at loading: scanned onto VEH-VAN-0011")


def test_severity_bands():
    assert ad.calculate_severity("critical", 0, "wrong_vehicle") == 100.0
    assert ad.severity_label(ad.calculate_severity("low", 100, "stuck")) == "low"


# ---- Module 4 ------------------------------------------------------------------
def test_departed_leg_is_not_boardable(world):
    g = graph_for(world)
    buffer = timedelta(minutes=config.HANDLING_BUFFER_MINUTES)
    for u, v, d in g.edges(data=True):
        if d["kind"] == "board":
            assert g.nodes[u]["time"] >= world["now"]
            assert g.nodes[v]["time"] - g.nodes[u]["time"] == buffer
        if d["kind"] in ("leg", "wait", "onboard"):
            assert g.nodes[v]["time"] >= g.nodes[u]["time"]


def test_offline_vehicle_excluded(world):
    g = graph_for(world, exclude_vehicle_ids={"TRUCK-102"})
    assert not any(d.get("vehicle_id") == "TRUCK-102" for _, _, d in g.edges(data=True))


def test_capacity_and_hazmat_filters(world):
    s = world["shipments"]["SHP-501"]
    leg = {"kind": "leg", "remaining_kg": 100, "remaining_cbm": 10,
           "hazmat_certifications": [], "cargo_hazmat": []}
    assert not gn.edge_allowed_by_capacity(s, leg)  # 120 kg > 100 kg
    s.handling_flags = ["hazmat_class_3"]
    leg["remaining_kg"] = 1000
    assert not gn.edge_allowed_by_handling(s, leg)
    leg["hazmat_certifications"] = ["hazmat_class_3"]
    assert gn.edge_allowed_by_handling(s, leg)
    leg["cargo_hazmat"] = ["hazmat_class_8"]
    assert not gn.edge_allowed_by_handling(s, leg)


# ---- Module 2 ------------------------------------------------------------------
def test_demo_piggyback_candidates(world):
    s = world["shipments"]["SHP-501"]
    candidates = pm.find_piggyback_matches(s, graph_for(world), world["now"])
    assert [c.vehicle_id for c in candidates][:2] == ["TRUCK-102", "TRUCK-104"]
    top = candidates[0]
    assert top.hubs == ["HUB-WGL-01", "HUB-VJA-01"]
    assert 0 <= top.score <= 100
    assert top.arrival_time < s.deadline


def test_oversized_skips_piggyback(world):
    s = world["shipments"]["SHP-501"]
    s.handling_flags = ["oversized"]
    assert pm.find_piggyback_matches(s, graph_for(world), world["now"]) == []


def test_critical_requires_near_instant_match(world):
    s = world["shipments"]["SHP-501"]
    s.priority = "critical"
    candidates = pm.find_piggyback_matches(s, graph_for(world), world["now"])
    assert all(c.first_hop_wait_hours <= config.CRITICAL_MAX_WAIT_HOURS for c in candidates)
    assert len(candidates) <= 1


# ---- Module 3 ------------------------------------------------------------------
def test_strategies_ranked_and_bounded(world):
    s = world["shipments"]["SHP-501"]
    ev = re_.evaluate_shipment(s, graph_for(world), world["routes"], now=world["now"])
    assert {st.type for st in ev.strategies} == {"piggyback", "reroute", "dedicated", "hold"}
    scores = [st.score for st in ev.strategies]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= x <= 100 for x in scores)
    assert ev.best.type == "piggyback" and ev.best.vehicle_id == "TRUCK-102"
    assert ev.recovery_mode == "pending_approval"


def test_tier_weights_shift_ranking(world):
    s = world["shipments"]["SHP-501"]
    g = graph_for(world)
    s.priority = "low"
    low = re_.evaluate_shipment(s, g, world["routes"], now=world["now"])
    s.priority = "critical"
    crit = re_.evaluate_shipment(s, g, world["routes"], now=world["now"])
    def gap(ev):  # dedicated (fast, costly) minus reroute (slow, cheap)
        by_type = {x.type: x.score for x in ev.strategies}
        return by_type["dedicated"] - by_type["reroute"]

    assert gap(crit) > gap(low)  # time matters more for critical, cost for low


def test_recovery_mode_rules(world):
    s = world["shipments"]["SHP-501"]
    mk = lambda t, sc: re_.Strategy(id=t, type=t, feasible=True, score=sc)  # noqa: E731
    s.priority = "critical"
    assert re_.determine_recovery_mode(s, [mk("piggyback", 90)]) == "auto_executed"
    s.priority = "high"
    assert re_.determine_recovery_mode(s, [mk("piggyback", 90)]) == "pending_approval"
    assert re_.determine_recovery_mode(s, [mk("piggyback", 40)]) == "escalated"
    assert re_.determine_recovery_mode(s, [mk("dedicated", 70)]) == "escalated"


# ---- Module 5: continuous shipment generation ---------------------------------
def test_generated_shipment_rides_vehicle_from_its_hub(world):
    import random

    from database.seed_data import carried_shipment

    v = world["vehicles"]["VEH-TRK-0001"]
    idx = v.current_stop_index
    hub = world["hubs"][v.planned_route[idx]]
    v.status, v.current_lat, v.current_lng = "at_hub", hub.lat, hub.lng  # as fleet_progress.arrive does
    s = carried_shipment(random.Random(1), world["now"], world["hubs"], v, idx,
                         "SHP-T-0001", "PGST0001", "medium", world["now"])
    assert s.origin_hub_id == v.planned_route[idx] == s.expected_route[0]
    assert s.destination_hub_id in v.planned_route[idx + 1:]
    assert s.current_vehicle_id == v.id and s.status == "in_transit"
    assert s.deadline > world["now"]
    # A freshly loaded shipment on its planned vehicle is not an anomaly.
    assert ad.detect_shipment(s, world["hubs"], world["now"]) is None


# ---- OSRM road geometry ----------------------------------------------------------------
def test_road_cache_directions_and_distance(world):
    from utils import roads

    fwd, back = roads.road_path("HUB-HYD-01", "HUB-WGL-01"), roads.road_path("HUB-WGL-01", "HUB-HYD-01")
    assert fwd and back == fwd[::-1]
    hyd, wgl = world["hubs"]["HUB-HYD-01"], world["hubs"]["HUB-WGL-01"]
    assert haversine(*fwd[0], hyd.lat, hyd.lng) < 2 and haversine(*fwd[-1], wgl.lat, wgl.lng) < 2
    assert roads.hub_km(hyd, wgl) == roads.road_distance_km("HUB-WGL-01", "HUB-HYD-01")
    assert gn.road_km(hyd, wgl) == roads.hub_km(hyd, wgl)  # the graph uses road km
    mid = roads.point_along_path(fwd, 0.5)
    assert abs(roads.km_to_hub("HUB-HYD-01", wgl, *mid) - roads.hub_km(hyd, wgl) / 2) < 10


def test_simulator_follows_the_road(world):
    from realtime.gps_simulator import GpsSimulator
    from utils import roads

    v = world["vehicles"]["TRUCK-102"]  # HYD → WGL leg
    path = roads.road_path("HUB-HYD-01", "HUB-WGL-01")
    sim = GpsSimulator()
    for _ in range(20):
        pos = sim.next_position(v, world["hubs"], 10, world["now"])
        v.current_lat, v.current_lng = pos["lat"], pos["lng"]
        off_road = min(point_to_line_distance((v.current_lat, v.current_lng), p, q)
                       for p, q in zip(path, path[1:]))
        assert off_road < 0.5
    wgl = world["hubs"]["HUB-WGL-01"]
    assert haversine(v.current_lat, v.current_lng, wgl.lat, wgl.lng) < 2  # reached Warangal
