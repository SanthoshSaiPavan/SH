"""MODULE 2: Piggyback matching as a constrained search over the Module 4 graph.

Hard filters (handling, capacity) prune the graph; transfer-timing is
structural in the time-expanded graph. Each candidate is the best path that
starts by boarding a distinct vehicle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import networkx as nx

import config
from engines import graph_network as gn
from utils import clock
from utils.scoring import clamp01, weighted_score


@dataclass
class PiggybackCandidate:
    vehicle_id: str
    vehicles: list
    hubs: list
    legs: list
    arrival_time: datetime
    cost: float
    detour_km: float
    distance_km: float
    transfers: int
    first_hop_wait_hours: float
    pickup_time: datetime | None
    available_capacity_kg: float
    scores: dict = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "vehicle_id": self.vehicle_id,
            "vehicles": self.vehicles,
            "hubs": self.hubs,
            "legs": [{**leg, "departure_time": leg["departure_time"].isoformat(),
                      "arrival_time": leg["arrival_time"].isoformat()} for leg in self.legs],
            "arrival_time": self.arrival_time.isoformat(),
            "pickup_time": self.pickup_time.isoformat() if self.pickup_time else None,
            "cost": self.cost,
            "detour_km": self.detour_km,
            "distance_km": self.distance_km,
            "transfers": self.transfers,
            "first_hop_wait_hours": round(self.first_hop_wait_hours, 2),
            "available_capacity_kg": self.available_capacity_kg,
            "scores": {k: round(v, 3) for k, v in self.scores.items()},
            "score": self.score,
        }


def is_oversized(shipment) -> bool:
    return "oversized" in (shipment.handling_flags or [])


def apply_hard_filters(shipment, graph: nx.DiGraph) -> nx.DiGraph:
    """Subgraph of edges the shipment may use (handling + capacity)."""
    return nx.subgraph_view(graph, filter_edge=lambda u, v: (
        gn.edge_allowed_by_handling(shipment, graph.edges[u, v])
        and gn.edge_allowed_by_capacity(shipment, graph.edges[u, v])))


def check_capacity_fit(shipment, edge) -> tuple[bool, float]:
    """(fits, fit_score). fit_score = fraction of the free space the shipment fills.

    Higher is a better use of spare capacity; values near 1.0 leave little slack
    (Module 6 flags that as capacity risk).
    """
    kg, cbm = edge["remaining_kg"], edge["remaining_cbm"]
    fits = shipment.weight_kg <= kg and shipment.volume_cbm <= cbm
    if not fits:
        return False, 0.0
    return True, clamp01(max(shipment.weight_kg / max(kg, 1e-9),
                             shipment.volume_cbm / max(cbm, 1e-9)))


def remaining_expected_hubs(shipment) -> list:
    expected = shipment.expected_route or []
    scanned = [h for h in (shipment.actual_route or []) if h in expected]
    if not scanned:
        return list(expected)
    return expected[expected.index(scanned[-1]) + 1:]


def calculate_route_overlap(shipment_route, path_hubs) -> float:
    """Share of the shipment's remaining expected hubs that the path also visits."""
    if not shipment_route:
        return 1.0
    return len(set(shipment_route) & set(path_hubs)) / len(shipment_route)


def calculate_path_cost(path: dict) -> float:
    return path["cost"]


def dedicated_cost(shipment, hubs: dict) -> tuple[float, float]:
    """(₹ cost, road km) of a dedicated vehicle straight to the destination."""
    dest = hubs[shipment.destination_hub_id]
    if shipment.current_hub_id in hubs:
        origin = hubs[shipment.current_hub_id]
        lat, lng = origin.lat, origin.lng
    else:
        lat, lng = shipment.current_lat, shipment.current_lng
    km = gn.haversine(lat, lng, dest.lat, dest.lng) * config.ROAD_DISTANCE_FACTOR
    return km * config.DEDICATED_COST_PER_KM, km


def composite_score(proximity, capacity, deadline, overlap, cost) -> float:
    return weighted_score(
        {"proximity": proximity, "capacity": capacity, "deadline": deadline,
         "overlap": overlap, "cost": cost},
        config.PIGGYBACK_WEIGHTS,
    )


def score_path(shipment, path: dict, hubs: dict, now: datetime) -> PiggybackCandidate:
    fits = [check_capacity_fit(shipment, leg)[1] for leg in path["legs"]]
    capacity = max(fits) if fits else 0.0
    proximity = 1.0 - clamp01(path["first_hop_wait_hours"] / config.MAX_FIRST_HOP_WAIT_HOURS)
    window_h = max((shipment.deadline - now).total_seconds() / 3600, 1e-6)
    buffer_h = (shipment.deadline - path["arrival_time"]).total_seconds() / 3600
    deadline = clamp01(buffer_h / window_h)
    overlap = calculate_route_overlap(remaining_expected_hubs(shipment), path["hubs"])
    baseline, _ = dedicated_cost(shipment, hubs)
    savings = clamp01(1 - calculate_path_cost(path) / baseline) if baseline > 0 else 0.0
    first_leg = path["legs"][0] if path["legs"] else None
    candidate = PiggybackCandidate(
        vehicle_id=path["vehicles"][0] if path["vehicles"] else "",
        vehicles=path["vehicles"], hubs=path["hubs"], legs=path["legs"],
        arrival_time=path["arrival_time"], cost=path["cost"], detour_km=path["detour_km"],
        distance_km=path["distance_km"], transfers=path["transfers"],
        first_hop_wait_hours=path["first_hop_wait_hours"],
        pickup_time=first_leg["departure_time"] if first_leg else None,
        available_capacity_kg=first_leg["remaining_kg"] if first_leg else 0.0,
        scores={"proximity": proximity, "capacity": capacity, "deadline": deadline,
                "overlap": overlap, "cost_savings": savings},
    )
    candidate.score = composite_score(proximity, capacity, deadline, overlap, savings)
    return candidate


def search_candidate_paths(shipment, graph, objective: str) -> list[dict]:
    entry = graph.graph.get("entry") or ("entry", shipment.id)
    return gn.find_candidate_paths(graph, entry, shipment.destination_hub_id, objective, shipment)


def find_piggyback_matches(shipment, graph: nx.DiGraph, now=None) -> list[PiggybackCandidate]:
    """Ranked piggyback candidates for a misplaced shipment.

    `graph` is the base time-expanded graph (without an entry node).
    Oversized shipments return no candidates (Module 3 routes them to dedicated).
    """
    if is_oversized(shipment):
        return []
    now = now or clock.now()
    hubs = graph.graph["hubs"]
    with_entry = gn.add_shipment_entry_node(graph, shipment, now)
    filtered = apply_hard_filters(shipment, with_entry)
    filtered.graph.update(with_entry.graph)
    objective = config.PRIORITY_OBJECTIVE.get(shipment.priority, "weighted")
    paths = search_candidate_paths(shipment, filtered, objective)
    if shipment.priority == "critical":
        # 🔴 takes the fastest feasible path directly, and only if it is near-instant.
        paths = [p for p in paths[:1]
                 if p["first_hop_wait_hours"] <= config.CRITICAL_MAX_WAIT_HOURS]
        return [score_path(shipment, p, hubs, now) for p in paths]
    candidates = [score_path(shipment, p, hubs, now) for p in paths]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[: config.MAX_PIGGYBACK_CANDIDATES]
