"""MODULE 3: Recovery strategy generation, scoring, and autonomy rule.

Strategies: one "piggyback:<vehicle>" per Module 2 candidate, plus reroute,
dedicated and hold. All are scored with the same tier-weighted formula so they
are comparable:
    score = Σ tier_weight[k] × component[k]  (k = cost, time, capacity, reliability)
The time component is P(on-time) (engines.on_time). The priority tier shifts the
weights (config.STRATEGY_WEIGHTS) instead of the plan's additive
`0.20 × priority_multiplier`, which could not change ranking.

Weights only rank within the cost × arrival-time Pareto front: strategies are
ordered by (feasible, on the front, score), so the recommendation is never an
option another one beats on both cost and arrival. `sensitivity` re-ranks the
front with each weight moved ±SENSITIVITY_STEP.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import networkx as nx
from sqlalchemy import func
from sqlalchemy.orm import Session

import config
from database.models import RecoveryAction, Shipment, Vehicle
from engines import graph_network as gn
from engines import piggyback_matcher as pm
from engines.on_time import on_time_probability
from utils import clock
from utils.scoring import clamp01, weighted_score


@dataclass
class Strategy:
    id: str
    type: str
    feasible: bool
    cost: float = 0.0
    arrival_time: datetime | None = None
    duration_hours: float = 0.0
    distance_km: float = 0.0
    detour_km: float = 0.0
    vehicle_id: str | None = None
    hubs: list = field(default_factory=list)
    legs: list = field(default_factory=list)
    deadline_met: bool = False
    buffer_hours: float = 0.0
    details: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    score: float = 0.0
    # Vehicles whose capacity this strategy consumes (piggyback: every leg's vehicle;
    # hold: its vehicle; reroute/dedicated: none). Used by the joint assignment.
    vehicles: list = field(default_factory=list)
    on_time_probability: float = 0.0  # Monte Carlo P(arrival <= deadline)
    pareto: bool = False  # on this shipment's cost × arrival-time Pareto front
    pareto_label: str | None = None  # 'fastest' | 'cheapest' | 'balanced' | None

    def to_dict(self) -> dict:
        legs = [{**leg, "departure_time": leg["departure_time"].isoformat(),
                 "arrival_time": leg["arrival_time"].isoformat()} for leg in self.legs]
        return {
            "id": self.id, "type": self.type, "feasible": self.feasible,
            "cost": round(self.cost, 2),
            "arrival_time": self.arrival_time.isoformat() if self.arrival_time else None,
            "duration_hours": round(self.duration_hours, 2),
            "distance_km": round(self.distance_km, 1), "detour_km": round(self.detour_km, 1),
            "vehicle_id": self.vehicle_id, "hubs": self.hubs, "legs": legs,
            "deadline_met": self.deadline_met, "buffer_hours": round(self.buffer_hours, 2),
            "details": self.details, "scores": {k: round(v, 3) for k, v in self.scores.items()},
            "score": self.score, "vehicles": self.vehicles,
            "on_time_probability": round(self.on_time_probability, 3),
            "pareto": self.pareto, "pareto_label": self.pareto_label,
        }


@dataclass
class Evaluation:
    shipment_id: str
    strategies: list  # ranked, best first
    recovery_mode: str
    piggyback_candidates: list
    dedicated_cost: float
    evaluated_at: datetime
    weights: dict = field(default_factory=dict)
    # [{strategy_id, label, cost, arrival_time (iso), on_time_probability, tradeoff}]
    pareto_options: list = field(default_factory=list)
    # Detours the no-harm rule refused for this shipment's pickup hub:
    # [{vehicle_id, detour_hub, detour_km, reason, victims: [{shipment_id, priority, late_hours}]}]
    rejected_options: list = field(default_factory=list)
    # {stable: bool, step: float, checks: [{component, change, recommended_id}]}
    sensitivity: dict = field(default_factory=dict)

    @property
    def best(self) -> Strategy | None:
        return self.strategies[0] if self.strategies else None

    def strategy(self, strategy_id: str) -> Strategy | None:
        return next((s for s in self.strategies if s.id == strategy_id), None)

    def to_dict(self) -> dict:
        return {
            "shipment_id": self.shipment_id,
            "recovery_mode": self.recovery_mode,
            "recommended": self.best.to_dict() if self.best else None,
            "strategies": [s.to_dict() for s in self.strategies],
            "piggyback_candidates": [c.to_dict() for c in self.piggyback_candidates],
            "dedicated_cost": round(self.dedicated_cost, 2),
            "evaluated_at": self.evaluated_at.isoformat(),
            "weights": self.weights,
            "piggyback_weights": config.PIGGYBACK_WEIGHTS,
            "pareto_options": self.pareto_options,
            "rejected_options": self.rejected_options,
            "sensitivity": self.sensitivity,
            "ontime_threshold": config.ONTIME_THRESHOLD,
        }


def _timed(strategy: Strategy, shipment, now: datetime) -> Strategy:
    if strategy.arrival_time is not None:
        strategy.duration_hours = (strategy.arrival_time - now).total_seconds() / 3600
        strategy.buffer_hours = (shipment.deadline - strategy.arrival_time).total_seconds() / 3600
        strategy.deadline_met = strategy.buffer_hours >= 0
    return strategy


def _start_hub(shipment, hubs):
    if shipment.current_hub_id in hubs:
        return hubs[shipment.current_hub_id]
    return gn.nearest_hub(hubs, shipment.current_lat, shipment.current_lng)


def piggyback_strategies(shipment, candidates, now) -> list[Strategy]:
    """One strategy per piggyback candidate (id "piggyback:<first vehicle>")."""
    if not candidates:
        return [Strategy(id="piggyback", type="piggyback", feasible=False,
                         details={"reason": "No vehicle with a feasible path and spare capacity"})]
    return [_timed(Strategy(
        id=f"piggyback:{c.vehicle_id}", type="piggyback", feasible=True, cost=c.cost,
        arrival_time=c.arrival_time, distance_km=c.distance_km, detour_km=c.detour_km,
        vehicle_id=c.vehicle_id, hubs=c.hubs, legs=c.legs, vehicles=list(c.vehicles),
        details={"piggyback_match_score": c.score, "match_scores": c.scores,
                 "pickup_time": c.pickup_time.isoformat() if c.pickup_time else None,
                 "available_capacity_kg": c.available_capacity_kg,
                 "transfers": c.transfers, "vehicles": c.vehicles},
    ), shipment, now) for c in candidates]


def hold_strategy(shipment, graph, now) -> Strategy:
    """Wait at the current (or nearest) hub for the next vehicle going straight to destination.

    Only planned schedules count: every detour chain is excluded.
    """
    with_entry = gn.add_shipment_entry_node(graph, shipment, now)
    no_detours = nx.subgraph_view(with_entry, filter_edge=lambda u, v: (
        not with_entry.edges[u, v].get("detour", False)
        and gn.edge_allowed_by_capacity(shipment, with_entry.edges[u, v])
        and gn.edge_allowed_by_handling(shipment, with_entry.edges[u, v])))
    paths = gn.find_candidate_paths(no_detours, with_entry.graph["entry"],
                                    shipment.destination_hub_id, "cheapest", shipment)
    direct = [p for p in paths if p["transfers"] == 0 and p["legs"]]
    if not direct:
        return Strategy(id="hold", type="hold", feasible=False,
                        details={"reason": "No scheduled vehicle to the destination within "
                                           f"{config.GRAPH_HORIZON_HOURS} h"})
    nxt = min(direct, key=lambda p: p["legs"][0]["departure_time"])
    first = nxt["legs"][0]
    return _timed(Strategy(
        id="hold", type="hold", feasible=True, cost=nxt["cost"], arrival_time=nxt["arrival_time"],
        distance_km=nxt["distance_km"], vehicle_id=first["vehicle_id"], hubs=nxt["hubs"],
        legs=nxt["legs"], vehicles=[first["vehicle_id"]],
        details={"hold_hub": first["from_hub"], "wait_hours": round(nxt["first_hop_wait_hours"], 2),
                 "next_vehicle_departure": first["departure_time"].isoformat()},
    ), shipment, now)


def reroute_strategy(shipment, hubs, routes, now) -> Strategy:
    network = gn.build_hub_network(hubs, routes)
    start = _start_hub(shipment, hubs)
    try:
        path = nx.shortest_path(network, start.id, shipment.destination_hub_id, weight="km")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return Strategy(id="reroute", type="reroute", feasible=False,
                        details={"reason": "No route-network path to destination"})
    km = cost = hours = 0.0
    for a, b in zip(path, path[1:]):
        edge = network.edges[a, b]
        km += edge["km"]
        cost += edge["km"] * edge["cost_per_km"] * config.REROUTE_RATE_FACTOR
        hours += edge["km"] / edge["speed_kmh"]
    hours += config.REROUTE_BOOKING_HOURS
    return _timed(Strategy(
        id="reroute", type="reroute", feasible=True, cost=cost,
        arrival_time=now + timedelta(hours=hours), distance_km=km, hubs=path,
        details={"via": path[1:-1], "carrier_rate_factor": config.REROUTE_RATE_FACTOR,
                 "booking_delay_hours": config.REROUTE_BOOKING_HOURS},
    ), shipment, now)


def dedicated_strategy(shipment, hubs, now) -> Strategy:
    cost, km = pm.dedicated_cost(shipment, hubs)
    hours = config.DEDICATED_DISPATCH_HOURS + km / config.DEDICATED_SPEED_KMH
    start = _start_hub(shipment, hubs)
    return _timed(Strategy(
        id="dedicated", type="dedicated", feasible=True, cost=cost,
        arrival_time=now + timedelta(hours=hours), distance_km=km,
        hubs=[start.id, shipment.destination_hub_id],
        details={"direct_km": round(km, 1), "dispatch_hours": config.DEDICATED_DISPATCH_HOURS},
    ), shipment, now)


def strategy_reliability(db: Session | None) -> dict:
    """Historical success rate per strategy, blended with a prior."""
    rates = dict(config.DEFAULT_RELIABILITY)
    if db is None:
        return rates
    rows = (db.query(RecoveryAction.action_type, RecoveryAction.status, func.count())
            .filter(RecoveryAction.status.in_(("completed", "failed")))
            .group_by(RecoveryAction.action_type, RecoveryAction.status).all())
    counts: dict = {}
    for action_type, status, n in rows:
        counts.setdefault(action_type, {"completed": 0, "failed": 0})[status] = n
    w = config.RELIABILITY_PRIOR_WEIGHT
    for action_type, c in counts.items():
        prior = rates.get(action_type, 0.8)
        rates[action_type] = (c["completed"] + prior * w) / (c["completed"] + c["failed"] + w)
    return rates


def score_strategy(strategy: Strategy, shipment, baseline_cost: float, now: datetime,
                   reliability: dict) -> float:
    strategy.on_time_probability = on_time_probability(strategy, shipment, now)
    if not strategy.feasible:
        strategy.scores, strategy.score = {}, 0.0
        return 0.0
    ceiling = max(baseline_cost * config.COST_CEILING_FACTOR, 1e-6)
    strategy.scores = {
        "cost": clamp01(1 - strategy.cost / ceiling),
        "time": strategy.on_time_probability,
        "capacity": config.CAPACITY_EFFICIENCY[strategy.type],
        "reliability": reliability.get(strategy.type, 0.8),
    }
    strategy.score = weighted_score(strategy.scores, tier_weights(shipment))
    return strategy.score


def tier_weights(shipment) -> dict:
    return config.STRATEGY_WEIGHTS.get(shipment.priority, config.STRATEGY_WEIGHTS["medium"])


def _rank_key(s: Strategy):
    return (s.feasible, s.pareto, s.score)


def compare_strategies(strategies: list[Strategy]) -> Strategy | None:
    ranked = sorted(strategies, key=_rank_key, reverse=True)
    return ranked[0] if ranked else None


def mark_pareto(strategies: list[Strategy]) -> list[Strategy]:
    """Flag the feasible strategies no other one beats on both cost and arrival; label them."""
    options = [s for s in strategies if s.feasible and s.arrival_time is not None]
    for s in strategies:
        s.pareto, s.pareto_label = False, None
    front = [s for s in options if not any(
        o.cost <= s.cost and o.arrival_time <= s.arrival_time
        and (o.cost < s.cost or o.arrival_time < s.arrival_time) for o in options)]
    for s in front:
        s.pareto = True
    if not front:
        return front
    cheapest = min(front, key=lambda s: (s.cost, s.arrival_time, -s.score))
    cheapest.pareto_label = "cheapest"
    fastest = min(front, key=lambda s: (s.arrival_time, s.cost, -s.score))
    if fastest is not cheapest:
        fastest.pareto_label = "fastest"
    rest = [s for s in front if s.pareto_label is None]
    if rest:
        max(rest, key=lambda s: s.score).pareto_label = "balanced"
    return front


def _money(value: float) -> str:
    return f"₹{value:,.0f}"


def pareto_options(front: list[Strategy]) -> list[dict]:
    """Front members, cheapest first, with the trade-off against the cheapest written out."""
    if not front:
        return []
    ordered = sorted(front, key=lambda s: (s.cost, s.arrival_time))
    base = ordered[0]
    out = []
    for s in ordered:
        extra = s.cost - base.cost
        saved_h = (base.arrival_time - s.arrival_time).total_seconds() / 3600
        if s is base:
            tradeoff = "cheapest option"
        elif round(extra) == 0 and round(saved_h, 1) == 0:
            tradeoff = "same cost and arrival as cheapest"
        else:
            tradeoff = f"+{_money(extra)} buys {saved_h:.1f} h vs cheapest"
        out.append({"strategy_id": s.id, "label": s.pareto_label, "cost": round(s.cost, 2),
                    "arrival_time": s.arrival_time.isoformat(),
                    "on_time_probability": round(s.on_time_probability, 3), "tradeoff": tradeoff})
    return out


def rejected_options(shipment, graph) -> list[dict]:
    """No-harm rejections for detours to this shipment's pickup hub that reach its destination."""
    start = _start_hub(shipment, graph.graph["hubs"]).id
    out, seen = [], set()
    for r in graph.graph.get("rejected_detours", ()):
        key = (r["vehicle_id"], r["detour_hub"])
        if r["detour_hub"] != start or shipment.destination_hub_id not in r.get("continues_to", ()) \
                or key in seen:
            continue
        seen.add(key)
        victims = ", ".join(f"{v['shipment_id']} ({v['priority']}) {v['late_hours']:.2f} h late"
                            for v in r["victims"])
        out.append({"vehicle_id": r["vehicle_id"], "detour_hub": r["detour_hub"],
                    "detour_km": r["detour_km"], "victims": r["victims"],
                    "reason": f"Detour to {r['detour_hub']} makes {victims}"})
    return out


def sensitivity(strategies: list[Strategy], weights: dict, best: Strategy | None) -> dict:
    """Recommendation with each tier weight moved ±SENSITIVITY_STEP (renormalised)."""
    step = config.SENSITIVITY_STEP
    pool = [s for s in strategies if s.pareto]  # already in rank order
    checks = []
    for component in weights:
        for change in (step, -step):
            w = dict(weights)
            w[component] *= 1 + change
            total = sum(w.values())
            w = {k: v / total for k, v in w.items()}
            pick = max(pool, key=lambda s: weighted_score(s.scores, w)) if pool else None
            checks.append({"component": component, "change": change,
                           "recommended_id": pick.id if pick else None})
    best_id = best.id if best and best.feasible else None
    return {"stable": all(c["recommended_id"] == best_id for c in checks), "step": step,
            "checks": checks}


def determine_recovery_mode(shipment, ranked: list[Strategy]) -> str:
    """'auto_executed' | 'pending_approval' | 'escalated' (confidence-threshold rule).

    Auto-execution also needs the top strategy's P(on-time) to meet the tier threshold.
    """
    top = ranked[0] if ranked else None
    has_alternative = any(s.feasible for s in ranked if s.type in ("piggyback", "reroute"))
    if top is None or not top.feasible or not has_alternative \
            or top.score < config.LOW_CONFIDENCE_THRESHOLD:
        return "escalated"
    if shipment.priority == "critical" and top.score > config.AUTO_EXECUTE_THRESHOLD \
            and top.on_time_probability >= config.ONTIME_THRESHOLD[shipment.priority]:
        return "auto_executed"
    return "pending_approval"


def generate_recovery_strategies(shipment, piggyback_candidates, graph, routes=None,
                                 now=None, db: Session | None = None) -> Evaluation:
    """Generate, score and rank all strategies for a misplaced shipment."""
    now = now or clock.now()
    hubs = graph.graph["hubs"]
    baseline, _ = pm.dedicated_cost(shipment, hubs)
    strategies = piggyback_strategies(shipment, piggyback_candidates, now) + [
        reroute_strategy(shipment, hubs, routes or [], now),
        dedicated_strategy(shipment, hubs, now),
        hold_strategy(shipment, graph, now),
    ]
    reliability = strategy_reliability(db)
    for s in strategies:
        score_strategy(s, shipment, baseline, now, reliability)
    front = mark_pareto(strategies)
    ranked = sorted(strategies, key=_rank_key, reverse=True)
    weights = tier_weights(shipment)
    return Evaluation(shipment.id, ranked, determine_recovery_mode(shipment, ranked),
                      piggyback_candidates, baseline, now, weights,
                      pareto_options=pareto_options(front),
                      rejected_options=rejected_options(shipment, graph),
                      sensitivity=sensitivity(ranked, weights, ranked[0] if ranked else None))


def evaluate_shipment(shipment, graph, routes, db=None, now=None) -> Evaluation:
    """Module 2 → Module 3 for one shipment."""
    now = now or clock.now()
    candidates = pm.find_piggyback_matches(shipment, graph, now)
    return generate_recovery_strategies(shipment, candidates, graph, routes, now, db)


def _insert_detour_stop(vehicle: Vehicle, strategy: Strategy) -> None:
    """Make the vehicle actually visit the detour pickup hub.

    Any off-route pickup is a detour, even one of ~0 km. For a detour on the leg being
    driven (vehicle in transit), the pickup hub becomes the vehicle's next stop.
    """
    if not strategy.legs or strategy.legs[0]["vehicle_id"] != vehicle.id:
        return
    pickup, next_hub = strategy.legs[0]["from_hub"], strategy.legs[0]["to_hub"]
    route = list(vehicle.planned_route)
    idx = vehicle.current_stop_index
    if pickup in route[idx:] or next_hub not in route[idx:]:
        return
    insert_at = route.index(next_hub, idx)
    if vehicle.status == "at_hub" and insert_at == idx:
        insert_at += 1
    route.insert(insert_at, pickup)
    vehicle.planned_route = route


def execute_recovery(db: Session, shipment: Shipment, strategy: Strategy, mode: str,
                     dedicated_cost: float) -> RecoveryAction:
    """Persist the chosen strategy: shipment/vehicle updates + a recovery_actions row."""
    from engines.fleet_progress import detach_for_recovery

    now = clock.now()
    if strategy.hubs and shipment.current_hub_id != strategy.hubs[0]:
        detach_for_recovery(db, shipment, strategy.hubs[0])
    action = RecoveryAction(
        id=f"RA-{uuid.uuid4().hex[:10]}", shipment_id=shipment.id, action_type=strategy.type,
        matched_vehicle_id=strategy.vehicle_id,
        original_route=list(shipment.expected_route or []),
        recovery_route={"hubs": strategy.hubs, "legs": strategy.to_dict()["legs"],
                        "start_time": now.isoformat(), "dedicated_cost": round(dedicated_cost, 2),
                        "arrival_time": strategy.arrival_time.isoformat()
                        if strategy.arrival_time else None},
        detour_km=strategy.detour_km, additional_cost=round(strategy.cost, 2),
        time_impact_hours=round(strategy.duration_hours, 2),
        capacity_fit_score=strategy.scores.get("capacity"),
        deadline_risk_score=round(1 - strategy.scores.get("time", 0.0), 3),
        overall_score=strategy.score, status="in_progress",
    )
    db.add(action)
    shipment.recovery_strategy = strategy.type
    shipment.recovery_score = strategy.score
    shipment.recovery_mode = mode
    shipment.recovery_vehicle_id = strategy.vehicle_id
    shipment.status = "piggybacked" if strategy.type == "piggyback" else "in_transit"
    if strategy.vehicle_id and strategy.type in ("piggyback", "hold"):
        vehicle = db.get(Vehicle, strategy.vehicle_id)
        if vehicle is not None:
            vehicle.used_capacity_kg += shipment.weight_kg
            vehicle.used_capacity_cbm += shipment.volume_cbm
            vehicle.piggybacked_shipments = list(vehicle.piggybacked_shipments or []) + [shipment.id]
            _insert_detour_stop(vehicle, strategy)
    db.commit()
    return action
