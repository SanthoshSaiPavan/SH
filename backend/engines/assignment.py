"""Joint assignment of misplaced shipments to recovery options (report C3 / K4).

Every recommendation cycle all misplaced shipments are assigned together so that no
vehicle is recommended to more shipments than its remaining kg / cbm allows:

    maximise Σ PRIORITY_MULTIPLIER[priority] × (score + PARETO_BONUS·pareto
                                                + SWITCH_MARGIN·[option is the current pick])
    s.t.     each shipment gets at most one option (exactly one whenever capacity allows)
             Σ weight_kg / volume_cbm of shipments using vehicle v ≤ remaining capacity of v

Solved as a binary program with scipy.optimize.milp; a deterministic greedy pass is the
fallback if the solver fails.
"""
from __future__ import annotations

import logging

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

import config

log = logging.getLogger(__name__)

# Covering a shipment always beats any objective difference between options.
_COVER_BONUS = 1e5
# Tie-breakers (well below any meaningful score difference, above the solver's 1e-6 gap):
# an exact tie at SWITCH_MARGIN keeps the current pick, other ties follow the ranking.
_STICKY_EPS = 1e-3
_RANK_EPS = 1e-4


def identity(strategy) -> tuple | None:
    return (strategy.type, strategy.vehicle_id) if strategy is not None else None


def usable(option, capacity: dict) -> bool:
    return option.feasible and all(v in capacity for v in option.vehicles)


def option_value(option, priority: str, current_identity, rank: int = 0, n: int = 1) -> float:
    base = option.score + (config.PARETO_BONUS if option.pareto else 0.0)
    if current_identity is not None and identity(option) == current_identity:
        base += config.SWITCH_MARGIN + _STICKY_EPS
    base += _RANK_EPS * (n - rank) / max(n, 1)
    return config.PRIORITY_MULTIPLIER.get(priority, 1.0) * base


def preferred(options: list, priority: str, current_identity, capacity: dict):
    """Best usable option ignoring what other shipments take (the unconstrained pick)."""
    scored = [(option_value(o, priority, current_identity, i, len(options)), -i, o)
              for i, o in enumerate(options) if usable(o, capacity)]
    return max(scored, key=lambda t: t[:2])[2] if scored else None


def _candidates(shipments, options, capacity, current):
    """[(sid, option, value)] of usable options, in deterministic order."""
    out = []
    for sid in sorted(shipments):
        opts = options.get(sid) or []
        prio = shipments[sid].get("priority", "medium")
        for i, o in enumerate(opts):
            if usable(o, capacity):
                out.append((sid, o, option_value(o, prio, current.get(sid), i, len(opts))))
    return out


def _fits(chosen: list, shipments: dict, capacity: dict) -> bool:
    used: dict = {}
    for sid, o, _ in chosen:
        for v in set(o.vehicles):
            kg, cbm = used.get(v, (0.0, 0.0))
            used[v] = (kg + shipments[sid]["weight_kg"], cbm + shipments[sid]["volume_cbm"])
    return all(kg <= capacity[v][0] + 1e-9 and cbm <= capacity[v][1] + 1e-9
               for v, (kg, cbm) in used.items())


def _solve_milp(cands, shipments, capacity) -> list | None:
    if not cands:
        return []
    sids = sorted({sid for sid, _, _ in cands})
    vehicles = sorted({v for _, o, _ in cands for v in o.vehicles})
    n = len(cands)
    c = -np.array([value + _COVER_BONUS for _, _, value in cands])
    rows, lb, ub = [], [], []
    for sid in sids:
        rows.append([1.0 if s == sid else 0.0 for s, _, _ in cands])
        lb.append(0.0)
        ub.append(1.0)
    for v in vehicles:
        for k, key in enumerate(("weight_kg", "volume_cbm")):
            rows.append([shipments[s][key] if v in o.vehicles else 0.0 for s, o, _ in cands])
            lb.append(-np.inf)
            ub.append(capacity[v][k])
    res = milp(c, constraints=LinearConstraint(np.array(rows), lb, ub),
               integrality=np.ones(n), bounds=Bounds(0, 1), options={"mip_rel_gap": 0.0})
    if not res.success or res.x is None:
        log.warning("Assignment milp failed: %s", res.message)
        return None
    chosen = [cand for cand, x in zip(cands, res.x) if x > 0.5]
    return chosen if _fits(chosen, shipments, capacity) else None


def _greedy(cands, shipments, capacity) -> list:
    """Priority multiplier desc, then value desc; each option taken only if it still fits."""
    order = sorted(cands, key=lambda t: (
        -config.PRIORITY_MULTIPLIER.get(shipments[t[0]].get("priority", "medium"), 1.0),
        -t[2], t[0]))
    left = {v: list(cap) for v, cap in capacity.items()}
    chosen, done = [], set()
    for sid, o, value in order:
        if sid in done:
            continue
        kg, cbm = shipments[sid]["weight_kg"], shipments[sid]["volume_cbm"]
        vs = set(o.vehicles)
        if all(left[v][0] + 1e-9 >= kg and left[v][1] + 1e-9 >= cbm for v in vs):
            for v in vs:
                left[v][0] -= kg
                left[v][1] -= cbm
            chosen.append((sid, o, value))
            done.add(sid)
    return chosen


def assign(shipments: dict, options: dict, capacity: dict, current: dict) -> dict:
    """{sid: chosen Strategy | None}. See module docstring for the model.

    shipments[sid] = {"priority", "weight_kg", "volume_cbm"}; options[sid] = feasible
    strategies (ranked best first); capacity[vehicle_id] = (remaining kg, remaining cbm);
    current[sid] = (type, vehicle_id) of the current recommendation.
    """
    cands = _candidates(shipments, options, capacity, current)
    try:
        chosen = _solve_milp(cands, shipments, capacity)
    except Exception:
        log.exception("Assignment milp raised")
        chosen = None
    if chosen is None:
        chosen = _greedy(cands, shipments, capacity)
    result = {sid: None for sid in shipments}
    for sid, o, _ in chosen:
        result[sid] = o
    return result


def displaced_by(sid: str, wanted, assignment: dict, shipments: dict,
                 capacity: dict) -> tuple[str, str] | None:
    """(vehicle_id, other_sid) when `wanted` does not fit for `sid` because of what the
    assignment gave other shipments; other_sid is the highest-priority user of that vehicle."""
    if wanted is None:
        return None
    need = shipments[sid]
    for v in sorted(set(wanted.vehicles)):
        if v not in capacity:
            continue
        others = [s for s, o in assignment.items()
                  if s != sid and o is not None and v in o.vehicles]
        kg = sum(shipments[s]["weight_kg"] for s in others)
        cbm = sum(shipments[s]["volume_cbm"] for s in others)
        if others and (kg + need["weight_kg"] > capacity[v][0] + 1e-9
                       or cbm + need["volume_cbm"] > capacity[v][1] + 1e-9):
            top = max(others, key=lambda s: (config.PRIORITY_MULTIPLIER.get(
                shipments[s].get("priority", "medium"), 1.0), s))
            return v, top
    return None
