"""P(on-time): Monte Carlo probability that a strategy arrives by the deadline.

Arrival times from Module 4 assume constant speed. Here each strategy is
replayed ONTIME_SAMPLES times with random travel-time multipliers (lognormal,
median TRAVEL_TIME_MEDIAN_FACTOR), random extra dwell at intermediate stops, and
random booking / dispatch delays. A transfer between two vehicles fails when the
inbound vehicle arrives later than the outbound one departs minus the handling
buffer. The RNG is seeded per (shipment, strategy) so re-evaluations are stable.
"""
from __future__ import annotations

import zlib
from datetime import datetime, timedelta

import numpy as np

import config


def _hours(t: datetime, now: datetime) -> float:
    return (t - now).total_seconds() / 3600


def _multiplier(rng, n: int):
    return rng.lognormal(np.log(config.TRAVEL_TIME_MEDIAN_FACTOR), config.TRAVEL_TIME_SIGMA, n)


def _vehicle_arrivals(legs: list, now: datetime, rng, n: int):
    """(arrival hours from now, transfer-ok mask) for a chain of vehicle legs."""
    buffer_h = config.HANDLING_BUFFER_MINUTES / 60
    ok = np.ones(n, dtype=bool)
    t = None
    for i, leg in enumerate(legs):
        new_vehicle = i == 0 or leg["vehicle_id"] != legs[i - 1]["vehicle_id"]
        if new_vehicle:
            depart = max(_hours(leg["departure_time"], now), 0.0) * _multiplier(rng, n)
            if t is not None:
                ok &= t <= depart - buffer_h
            t = depart
        else:
            planned_dwell = max(_hours(leg["departure_time"], legs[i - 1]["arrival_time"]), 0.0)
            t = t + planned_dwell + rng.exponential(config.DWELL_DELAY_MEAN_MINUTES / 60, n)
        t = t + _hours(leg["arrival_time"], leg["departure_time"]) * _multiplier(rng, n)
    return t, ok


def _direct_arrivals(strategy, delay_range: tuple, nominal_delay: float, rng, n: int):
    """Reroute / dedicated: uniform booking or dispatch delay + travel × multiplier."""
    travel = max(strategy.duration_hours - nominal_delay, 0.0)
    return rng.uniform(*delay_range, n) + travel * _multiplier(rng, n), np.ones(n, dtype=bool)


def on_time_probability(strategy, shipment, now: datetime) -> float:
    """P(arrival <= deadline); also stores the p90 arrival in strategy.details."""
    if not strategy.feasible or strategy.arrival_time is None:
        return 0.0
    rng = np.random.default_rng(zlib.crc32(f"{shipment.id}|{strategy.id}".encode()))
    n = config.ONTIME_SAMPLES
    if strategy.type == "reroute":
        arrival, ok = _direct_arrivals(strategy, config.REROUTE_BOOKING_RANGE_HOURS,
                                       config.REROUTE_BOOKING_HOURS, rng, n)
    elif strategy.type == "dedicated":
        arrival, ok = _direct_arrivals(strategy, config.DEDICATED_DISPATCH_RANGE_HOURS,
                                       config.DEDICATED_DISPATCH_HOURS, rng, n)
    elif strategy.legs:
        arrival, ok = _vehicle_arrivals(strategy.legs, now, rng, n)
    else:
        return 0.0
    strategy.details["arrival_p90"] = (
        now + timedelta(hours=float(np.percentile(arrival, 90)))).isoformat()
    on_time = ok & (arrival <= _hours(shipment.deadline, now))
    return float(on_time.mean())
