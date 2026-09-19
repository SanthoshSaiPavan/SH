"""Serialize the time-expanded graph (Module 4) for the 3D graph view.

Read-only: takes the graph the recommendation loop already built and turns it
into JSON nodes/edges. The demo view keeps only one route's vehicles and hubs.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import networkx as nx

VEHICLE_KINDS = ("arr", "dep")


def node_id(key: tuple) -> str:
    return "|".join(v.isoformat() if isinstance(v, datetime) else str(v) for v in key)


def _keep(data: dict, route_id: str | None, route_hubs: set | None, until: datetime) -> bool:
    if data.get("time") is None or data["time"] > until:
        return False
    if route_id is None:
        return True
    if data["kind"] in VEHICLE_KINDS:
        return data.get("route_id") == route_id
    return data["hub"] in route_hubs


def serialize(graph: nx.DiGraph, hubs: dict, hours: float, route=None,
              recommendations: list | None = None) -> dict:
    """{now, hubs, nodes, edges, recommendations} for nodes within `hours` of graph time.

    `route` limits the view to that route's vehicles and hub timelines (demo mode).
    `recommendations` are [{shipment_id, hub, time, legs}] with legs as in Strategy.legs.
    """
    now = graph.graph["now"]
    until = now + timedelta(hours=hours)
    route_id = route.id if route is not None else None
    route_hubs = set(route.hub_sequence) if route is not None else None

    kept = {n: d for n, d in graph.nodes(data=True) if _keep(d, route_id, route_hubs, until)}
    nodes = []
    for key, d in kept.items():
        node = {"id": node_id(key), "kind": d["kind"], "hub": d["hub"],
                "t": (d["time"] - now).total_seconds() / 3600}
        if d["kind"] in VEHICLE_KINDS:
            node["vehicle_id"] = d["vehicle_id"]
            node["variant"] = key[3]
            node["remaining_kg"] = round(d["remaining_kg"], 1)
            node["total_kg"] = d["total_kg"]
        nodes.append(node)

    edges = []
    for u, v, d in graph.edges(data=True):
        if u not in kept or v not in kept:
            continue
        edge = {"source": node_id(u), "target": node_id(v), "kind": d["kind"]}
        if "vehicle_id" in d:
            edge["vehicle_id"] = d["vehicle_id"]
        if d["kind"] == "leg":
            edge["km"] = round(d["km"], 1)
            edge["detour"] = u[3] != "main"
        edges.append(edge)

    used_hubs = {n["hub"] for n in nodes} | (route_hubs or set())
    recs = []
    for r in recommendations or []:
        legs = [{"vehicle_id": leg["vehicle_id"], "from_hub": leg["from_hub"],
                 "to_hub": leg["to_hub"],
                 "dep_t": (leg["departure_time"] - now).total_seconds() / 3600,
                 "arr_t": (leg["arrival_time"] - now).total_seconds() / 3600}
                for leg in r["legs"]]
        if route is not None and not all(leg["from_hub"] in route_hubs and leg["to_hub"] in route_hubs
                                         for leg in legs):
            continue
        entry_t = (r["time"] - now).total_seconds() / 3600 if r["time"] else 0.0
        recs.append({"shipment_id": r["shipment_id"], "hub": r["hub"],
                     "t": max(0.0, entry_t), "legs": legs})
        if r["hub"]:
            used_hubs.add(r["hub"])

    return {
        "now": now.isoformat(),
        "hours": hours,
        "route_id": route_id,
        "hubs": [{"id": h.id, "name": h.name, "lat": h.lat, "lng": h.lng}
                 for hid, h in sorted(hubs.items()) if hid in used_hubs],
        "nodes": nodes,
        "edges": edges,
        "recommendations": recs,
    }
