"""Module 1 scan-based detection on in-memory seed objects (no database needed)."""
from datetime import timedelta

import pytest

import config
from database.seed_data import build_seed
from engines import anomaly_detector as ad
from engines.fleet_progress import record_scan, short_targets
from utils import clock


@pytest.fixture()
def world():
    hubs, routes, vehicles, shipments, _ = build_seed()
    return {"hubs": {h.id: h for h in hubs}, "vehicles": {v.id: v for v in vehicles},
            "shipments": {s.id: s for s in shipments}, "now": clock.now()}


def detect(world, s, with_vehicles=True):
    return ad.detect_shipment(s, world["hubs"], world["now"],
                              world["vehicles"] if with_vehicles else None)


def test_seed_scans_and_manifests(world):
    for s in world["shipments"].values():
        assert s.scans, s.id
        if s.current_vehicle_id:
            assert s.manifest_vehicle_id == s.current_vehicle_id
            assert (s.scans[0].event_type, s.scans[0].hub_id) == ("load", s.origin_hub_id)
    shp_501 = world["shipments"]["SHP-501"]
    assert [(e.event_type, e.hub_id, e.expected) for e in shp_501.scans] == [
        ("hub_scan", "HUB-HYD-01", True), ("excess", "HUB-WGL-01", False)]


def test_seed_flags_only_the_excess_scan(world):
    for vehicles in (world["vehicles"], None):
        results = ad.detect_anomalies(world["shipments"].values(), world["hubs"], world["now"],
                                      vehicles)
        assert [(r.shipment_id, r.misplacement_type) for r in results] == [("SHP-501", "wrong_hub")]
        assert "Excess at hub" in results[0].reason


def test_load_onto_wrong_vehicle_is_a_manifest_mismatch(world):
    s = world["shipments"]["SHP-311"]
    wrong = world["vehicles"]["VEH-VAN-0011"]  # Mumbai–Pune shuttle never reaches Vijayawada
    record_scan(s, "load", world["now"], None, wrong.id,
                expected=ad.vehicle_serves(wrong, "HUB-VJA-01"))
    for with_vehicles in (True, False):  # live route, or the loading scanner's own verdict
        result = detect(world, s, with_vehicles)
        assert result.misplacement_type == "wrong_vehicle"
        assert "VEH-VAN-0011" in result.reason and "HUB-VJA-01" in result.reason
        assert "TRUCK-102" in result.reason  # the manifest


def test_load_onto_a_vehicle_that_serves_the_next_hub_is_fine(world):
    s = world["shipments"]["SHP-311"]
    record_scan(s, "load", world["now"], "HUB-NAG-01", "TRUCK-102")
    assert detect(world, s) is None


def test_manifest_check_uses_the_vehicles_current_route(world):
    s = world["shipments"]["SHP-311"]
    world["vehicles"]["TRUCK-102"].planned_route = ["HUB-NAG-01", "HUB-HYD-01"]  # rerouted
    assert detect(world, s).misplacement_type == "wrong_vehicle"
    assert detect(world, s, with_vehicles=False) is None  # the load scan itself was fine


def test_short_at_unload_flags_stuck(world):
    s = world["shipments"]["SHP-311"]
    s.current_vehicle_id = None  # ground truth: left behind at Nagpur
    targets = short_targets("TRUCK-102", "HUB-VJA-01", [s])
    assert targets == [s]
    record_scan(s, "short", world["now"], "HUB-VJA-01", "TRUCK-102", expected=False)
    assert short_targets("TRUCK-102", "HUB-VJA-01", [s]) == []  # one short per hub
    result = detect(world, s)
    assert result.misplacement_type == "stuck"
    assert result.reason == ("Short at unload: not aboard TRUCK-102 when it reached HUB-VJA-01; "
                             "last scanned at HUB-NAG-01")


def test_no_short_for_parcels_aboard_or_due_elsewhere(world):
    s = world["shipments"]["SHP-311"]
    assert short_targets("TRUCK-102", "HUB-VJA-01", [s]) == []  # aboard
    s.current_vehicle_id = None
    assert short_targets("TRUCK-102", "HUB-WGL-01", [s]) == []  # not its next hub
    assert short_targets("TRUCK-104", "HUB-VJA-01", [s]) == []  # not its manifest vehicle
    s.recovery_strategy = "piggyback"
    assert short_targets("TRUCK-102", "HUB-VJA-01", [s]) == []  # in recovery


def test_scan_gap_only_for_parcels_scanned_off_a_vehicle(world):
    old = world["now"] - timedelta(hours=config.MAX_SCAN_GAP_HOURS + 1)
    aboard = world["shipments"]["SHP-311"]
    aboard.last_scan_at = aboard.scans[-1].scanned_at = old
    assert not ad.check_scan_gap(aboard, world["now"])
    at_hub = world["shipments"]["SHP-501"]
    at_hub.actual_route = ["HUB-HYD-01"]
    at_hub.last_scan_at = old
    result = detect(world, at_hub)
    assert result.misplacement_type == "stuck" and result.reason.startswith("Scan gap")


def test_parcel_position_is_not_evidence(world):
    s = world["shipments"]["SHP-311"]
    s.current_lat, s.current_lng = 8.5, 77.0  # far off any expected path
    s.current_vehicle_id = "VEH-VAN-0011"
    s.current_hub_id = "HUB-MUM-01"
    assert detect(world, s) is None
