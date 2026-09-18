"""Joint assignment (engines.assignment), pure and in-memory."""
from engines import assignment
from engines.recovery_engine import Strategy


def opt(kind, score, vehicle=None, vehicles=None, pareto=False, sid=None):
    vehicles = vehicles if vehicles is not None else ([vehicle] if vehicle else [])
    return Strategy(id=sid or (f"{kind}:{vehicle}" if vehicle else kind), type=kind,
                    feasible=True, score=score, vehicle_id=vehicle, vehicles=vehicles,
                    pareto=pareto)


def ship(priority, kg=100.0, cbm=1.0):
    return {"priority": priority, "weight_kg": kg, "volume_cbm": cbm}


def test_last_capacity_goes_to_higher_priority():
    shipments = {"SHP-A": ship("medium"), "SHP-B": ship("critical")}
    options = {sid: [opt("piggyback", 80, "T1"), opt("dedicated", 50)] for sid in shipments}
    result = assignment.assign(shipments, options, {"T1": (150.0, 10.0)}, {})
    assert result["SHP-B"].vehicle_id == "T1"
    assert result["SHP-A"].type == "dedicated"


def test_cbm_constraint_also_binds():
    shipments = {"SHP-A": ship("high", kg=10, cbm=6), "SHP-B": ship("low", kg=10, cbm=6)}
    options = {sid: [opt("piggyback", 80, "T1"), opt("dedicated", 50)] for sid in shipments}
    result = assignment.assign(shipments, options, {"T1": (1000.0, 10.0)}, {})
    assert result["SHP-A"].vehicle_id == "T1"
    assert result["SHP-B"].type == "dedicated"


def test_multi_vehicle_option_consumes_every_vehicle():
    shipments = {"SHP-A": ship("critical"), "SHP-B": ship("medium")}
    options = {"SHP-A": [opt("piggyback", 90, "T1", vehicles=["T1", "T2"])],
               "SHP-B": [opt("piggyback", 80, "T2"), opt("dedicated", 40)]}
    result = assignment.assign(shipments, options, {"T1": (500.0, 9.0), "T2": (150.0, 9.0)}, {})
    assert result["SHP-A"].vehicles == ["T1", "T2"]
    assert result["SHP-B"].type == "dedicated"


def test_current_option_is_sticky_within_margin():
    shipments = {"SHP-A": ship("medium")}
    current = {"SHP-A": ("piggyback", "T1")}
    capacity = {"T1": (500.0, 9.0), "T2": (500.0, 9.0)}
    close = {"SHP-A": [opt("piggyback", 64, "T2"), opt("piggyback", 60, "T1")]}
    assert assignment.assign(shipments, close, capacity, current)["SHP-A"].vehicle_id == "T1"
    tie = {"SHP-A": [opt("piggyback", 65, "T2"), opt("piggyback", 60, "T1")]}
    assert assignment.assign(shipments, tie, capacity, current)["SHP-A"].vehicle_id == "T1"
    beaten = {"SHP-A": [opt("piggyback", 66, "T2"), opt("piggyback", 60, "T1")]}
    assert assignment.assign(shipments, beaten, capacity, current)["SHP-A"].vehicle_id == "T2"


def test_pareto_option_beats_dominated_one():
    shipments = {"SHP-A": ship("medium")}
    options = {"SHP-A": [opt("reroute", 80), opt("dedicated", 50, pareto=True)]}
    assert assignment.assign(shipments, options, {}, {})["SHP-A"].type == "dedicated"


def test_option_with_unknown_vehicle_is_unusable():
    shipments = {"SHP-A": ship("medium"), "SHP-B": ship("medium")}
    options = {"SHP-A": [opt("piggyback", 90, "GONE"), opt("dedicated", 40)],
               "SHP-B": [opt("piggyback", 90, "GONE")]}
    result = assignment.assign(shipments, options, {}, {})
    assert result["SHP-A"].type == "dedicated"
    assert result["SHP-B"] is None


def test_shipment_without_options_gets_none():
    shipments = {"SHP-A": ship("medium"), "SHP-B": ship("low")}
    result = assignment.assign(shipments, {"SHP-B": [opt("dedicated", 40)]}, {}, {})
    assert result["SHP-A"] is None
    assert result["SHP-B"].type == "dedicated"


def test_infeasible_options_are_ignored():
    bad = Strategy(id="hold", type="hold", feasible=False, score=99)
    result = assignment.assign({"SHP-A": ship("low")}, {"SHP-A": [bad]}, {}, {})
    assert result["SHP-A"] is None


def test_greedy_fallback_is_feasible(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("solver unavailable")

    monkeypatch.setattr(assignment, "milp", broken)
    shipments = {"SHP-A": ship("medium"), "SHP-B": ship("critical"), "SHP-C": ship("high")}
    options = {sid: [opt("piggyback", 80, "T1"), opt("dedicated", 50)] for sid in shipments}
    capacity = {"T1": (150.0, 10.0)}
    result = assignment.assign(shipments, options, capacity, {})
    assert result["SHP-B"].vehicle_id == "T1"
    assert result["SHP-A"].type == result["SHP-C"].type == "dedicated"
    assert assignment._fits([(s, o, 0) for s, o in result.items()], shipments, capacity)


def test_greedy_fallback_when_milp_reports_failure(monkeypatch):
    class Failed:
        success, x, message = False, None, "failed"

    monkeypatch.setattr(assignment, "milp", lambda *a, **k: Failed())
    shipments = {"SHP-A": ship("low"), "SHP-B": ship("low")}
    options = {sid: [opt("piggyback", 80, "T1"), opt("dedicated", 50)] for sid in shipments}
    result = assignment.assign(shipments, options, {"T1": (150.0, 10.0)}, {})
    assert sorted(o.type for o in result.values()) == ["dedicated", "piggyback"]
    assert result == assignment.assign(shipments, options, {"T1": (150.0, 10.0)}, {})


def test_displaced_by_names_the_winner():
    shipments = {"SHP-A": ship("medium"), "SHP-B": ship("critical")}
    options = {sid: [opt("piggyback", 80, "T1"), opt("dedicated", 50)] for sid in shipments}
    capacity = {"T1": (150.0, 10.0)}
    result = assignment.assign(shipments, options, capacity, {})
    wanted = assignment.preferred(options["SHP-A"], "medium", None, capacity)
    assert wanted.vehicle_id == "T1"
    assert assignment.displaced_by("SHP-A", wanted, result, shipments, capacity) == \
        ("T1", "SHP-B")
    assert assignment.displaced_by("SHP-B", result["SHP-B"], result, shipments, capacity) is None
