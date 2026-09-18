"""Smoke test for the replay benchmark (scripts/benchmark.py)."""
from scripts import benchmark


def test_benchmark_small_run_is_reproducible_and_harmless():
    a = benchmark.run(n=4, seed=11, batch=3)
    b = benchmark.run(n=4, seed=11, batch=3)
    assert a == b
    assert a["rescues"] == 12 and set(a["policies"]) == set(benchmark.POLICIES)
    ours = a["policies"]["piggyship"]
    assert ours["collateral_late_shipments"] == 0  # the no-harm rule
    assert ours["capacity_overflows"] == 0  # the joint assignment
    assert a["policies"]["always_dedicated"]["strategy_mix_pct"] == {"dedicated": 100.0}
    for s in a["policies"].values():
        assert 0 <= s["expected_on_time_pct"] <= 100
