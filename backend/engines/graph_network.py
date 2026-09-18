"""MODULE 4: Time-expanded network model.

Node kinds (every node carries `hub` and `time` attributes, i.e. it is a
(hub, time) pair; the tuple key only keeps same-(hub,time) nodes distinct):
    ("hub", hub_id, time)            hub timeline: where a shipment can wait
    ("dep", vehicle_id, idx, variant) vehicle departing stop idx
    ("arr", vehicle_id, idx, variant) vehicle arriving at stop idx
    ("entry", shipment_id)           synthetic entry node for a misplaced shipment
    ("sink", hub_id)                 added per search, collects destination nodes

Edge kinds:
    leg      dep -> arr     vehicle travelling between two hubs (capacity-limited)
    onboard  arr -> dep     staying on the same vehicle through a stop
    unload   arr -> hub     getting off onto the hub timeline
    board    hub -> dep     boarding; the hub node sits HANDLING_BUFFER before departure,
                            so a vehicle that already left simply has no reachable board edge
    wait     hub -> hub     waiting at a hub (holding cost)
    entry    entry -> hub   bringing the shipment onto the nearest hub timeline

`variant` is "main" for a vehicle's planned schedule, or a detour: a copy of its
remaining schedule shifted by a stop at an off-route hub within MAX_DETOUR_KM of
the road. Two detour kinds:
    "detour:<idx>:<hub>"   on the leg between remaining stops idx and idx+1
    "detour:live:<hub>"    on the leg the vehicle is driving now, for hubs ahead of it
Every node and edge of a detour chain carries `detour=True`. A detour that makes a
shipment aboard the vehicle (`cargo_aboard`) miss a deadline it would otherwise
meet is not added (no-harm rule); it is recorded in `g.graph["rejected_detours"]`.
Edge costs are computed per shipment at search time.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache

import networkx as nx

import config
from engines import detours as dt
from engines.detours import cargo_aboard_from  # noqa: F401  (public: realtime loop, benchmark)
from utils import roads
from utils.geo import haversine, point_to_line_distance

HAZMAT_PREFIX = "hazmat_"


def road_km(a, b) -> float:
    """Road km between two hubs (cached OSRM distance, else great-circle × factor)."""
    return roads.hub_km(a, b)


@lru_cache(maxsize=4096)
def _distance_to_leg_km(a_id, b_id, hub_id, hub_pt, a_pt, b_pt) -> float:
    """km from a hub to the road between hubs a and b (straight segment if not cached).

    Cached because it runs for every leg × hub on every graph rebuild; hubs don't move.
    """
    path = roads.road_path(a_id, b_id) or [a_pt, b_pt]
    return min(point_to_line_distance(hub_pt, p, q) for p, q in zip(path, path[1:]))


def _hours(km: float, speed: float) -> timedelta:
    return timedelta(hours=km / max(speed, 1.0))


def vehicle_schedule(vehicle, hubs: dict, now: datetime, position=None) -> list[dict]:
    """Remaining stops [{idx, hub, arrive, depart}] derived from position and speed."""
    route = vehicle.planned_route or []
    idx = vehicle.current_stop_index or 0
    if idx >= len(route) or vehicle.status == "completed":
        return []
    lat, lng = position or (vehicle.current_lat, vehicle.current_lng)
    dwell = timedelta(minutes=config.HUB_DWELL_MINUTES)
    first = hubs[route[idx]]
    if vehicle.status == "at_hub":
        arrive = now
    else:
        prev_id = route[idx - 1] if idx > 0 else None
        arrive = now + _hours(roads.km_to_hub(prev_id, first, lat, lng), vehicle.speed_kmh)
    stops = []
    for i in range(idx, len(route)):
        if i > idx:
            arrive = stops[-1]["depart"] + _hours(
                road_km(hubs[route[i - 1]], hubs[route[i]]), vehicle.speed_kmh)
        stops.append({"idx": i, "hub": route[i], "arrive": arrive, "depart": arrive + dwell})
    return stops


class _Builder:
    def __init__(self, hubs, routes, now, cargo_hazmat, cargo_aboard):
        self.g = nx.DiGraph(now=now)
        self.hubs = hubs
        self.routes = routes
        self.now = now
        self.cargo_hazmat = cargo_hazmat
        self.cargo_aboard = cargo_aboard
        self.rejected: list[dict] = []
        self.timeline: dict[str, set] = defaultdict(set)
        self.horizon = now + timedelta(hours=config.GRAPH_HORIZON_HOURS)
        self.buffer = timedelta(minutes=config.HANDLING_BUFFER_MINUTES)
        self.dwell = timedelta(minutes=config.HUB_DWELL_MINUTES)

    def hub_node(self, hub_id: str, time: datetime):
        node = ("hub", hub_id, time)
        if node not in self.g:
            self.g.add_node(node, hub=hub_id, time=time, kind="hub")
            self.timeline[hub_id].add(time)
        return node

    def vehicle_attrs(self, v):
        route = self.routes.get(v.route_id)
        return {
            "vehicle_id": v.id,
            "route_id": v.route_id,
            "cost_per_km": route.cost_per_km if route else config.DEDICATED_COST_PER_KM,
            "remaining_kg": max(0.0, v.total_capacity_kg - v.used_capacity_kg),
            "remaining_cbm": max(0.0, v.total_capacity_cbm - v.used_capacity_cbm),
            "total_kg": v.total_capacity_kg,
            "total_cbm": v.total_capacity_cbm,
            "hazmat_certifications": list(v.hazmat_certifications or []),
            "cargo_hazmat": sorted(self.cargo_hazmat.get(v.id, set())),
        }

    def add_chain(self, v, stops, variant, detour_km=0.0):
        """Add one vehicle schedule chain. The first stop is boardable only (no inbound leg)."""
        attrs = {**self.vehicle_attrs(v), "detour": variant != "main"}
        flag = attrs["detour"]
        for pos, stop in enumerate(stops):
            key = (v.id, stop["idx"], variant)
            arr, dep = ("arr",) + key, ("dep",) + key
            is_last = pos == len(stops) - 1
            self.g.add_node(arr, hub=stop["hub"], time=stop["arrive"], kind="arr", **attrs)
            self.g.add_edge(arr, self.hub_node(stop["hub"], stop["arrive"]), kind="unload",
                            vehicle_id=v.id, detour=flag)
            if is_last or stop["depart"] > self.horizon:
                continue
            self.g.add_node(dep, hub=stop["hub"], time=stop["depart"], kind="dep", **attrs)
            self.g.add_edge(arr, dep, kind="onboard", vehicle_id=v.id, detour=flag)
            board_time = stop["depart"] - self.buffer
            if board_time >= self.now:
                self.g.add_edge(self.hub_node(stop["hub"], board_time), dep, kind="board",
                                vehicle_id=v.id, detour=flag,
                                detour_km=detour_km if pos == 0 and flag else 0.0,
                                cost_per_km=attrs["cost_per_km"])
            nxt = stops[pos + 1]
            self.g.add_edge(dep, ("arr", v.id, nxt["idx"], variant), kind="leg",
                            from_hub=stop["hub"], to_hub=nxt["hub"],
                            departure_time=stop["depart"], arrival_time=nxt["arrive"],
                            km=road_km(self.hubs[stop["hub"]], self.hubs[nxt["hub"]]), **attrs)

    def add_detour(self, v, stops, hub, arrive_h: datetime, rest: list[dict], h_to_next: float,
                   idx_tag: str, variant: str, detour_km: float):
        """Stop at `hub` at arrive_h, then drive on to rest[0] and shift every remaining stop."""
        shift = (arrive_h + self.dwell + _hours(h_to_next, v.speed_kmh)) - rest[0]["arrive"]
        chain = [{"idx": idx_tag, "hub": hub.id, "arrive": arrive_h, "depart": arrive_h + self.dwell}]
        chain += [{**s, "arrive": s["arrive"] + shift, "depart": s["depart"] + shift} for s in rest]
        victims = dt.harmed(self.cargo_aboard.get(v.id, ()), stops, chain)
        if victims:
            self.rejected.append({"vehicle_id": v.id, "detour_hub": hub.id,
                                  "detour_km": round(detour_km, 1), "victims": victims,
                                  "continues_to": [s["hub"] for s in rest]})
            return
        self.add_chain(v, chain, variant, detour_km=detour_km)

    def add_detours(self, v, stops):
        route_hubs = set(v.planned_route or [])
        for pos in range(len(stops) - 1):
            a, b = self.hubs[stops[pos]["hub"]], self.hubs[stops[pos + 1]["hub"]]
            for hub in self.hubs.values():
                if hub.id in route_hubs:
                    continue
                if _distance_to_leg_km(a.id, b.id, hub.id, (hub.lat, hub.lng),
                                       (a.lat, a.lng), (b.lat, b.lng)) > config.MAX_DETOUR_KM:
                    continue
                to_h, h_to_b, direct = road_km(a, hub), road_km(hub, b), road_km(a, b)
                self.add_detour(v, stops, hub, stops[pos]["depart"] + _hours(to_h, v.speed_kmh),
                                stops[pos + 1:], h_to_b, f"{stops[pos]['idx']}d",
                                f"detour:{stops[pos]['idx']}:{hub.id}",
                                max(0.0, to_h + h_to_b - direct))

    def add_live_detours(self, v, stops, position):
        """Detours on the leg being driven now, to off-route hubs ahead of the vehicle."""
        if v.status == "at_hub":
            return
        route = v.planned_route or []
        idx = stops[0]["idx"]
        prev_id = route[idx - 1] if idx > 0 else None
        nxt = self.hubs[stops[0]["hub"]]
        pos = position or (v.current_lat, v.current_lng)
        prev = self.hubs.get(prev_id)
        near = [h for h in self.hubs.values() if h.id not in set(route) and (  # whole-leg prefilter
            _distance_to_leg_km(prev.id, nxt.id, h.id, (h.lat, h.lng), (prev.lat, prev.lng),
                                (nxt.lat, nxt.lng))
            if prev else point_to_line_distance((h.lat, h.lng), pos, (nxt.lat, nxt.lng))
        ) <= config.MAX_DETOUR_KM]
        if not near:
            return
        ahead, scale = dt.road_ahead(prev_id, nxt, pos)
        direct = roads.km_to_hub(prev_id, nxt, *pos)
        for hub in near:
            to_h = dt.km_along_to(ahead, scale, hub)
            if to_h is None:
                continue
            h_to_b = road_km(hub, nxt)
            self.add_detour(v, stops, hub, self.now + _hours(to_h, v.speed_kmh), stops, h_to_b,
                            f"{idx}p", f"detour:live:{hub.id}", max(0.0, to_h + h_to_b - direct))

    def link_timelines(self):
        for hub_id, times in self.timeline.items():
            ordered = sorted(times)
            for t1, t2 in zip(ordered, ordered[1:]):
                self.g.add_edge(("hub", hub_id, t1), ("hub", hub_id, t2), kind="wait")


def build_time_expanded_graph(hubs, vehicles, routes, current_time: datetime,
                              live_positions: dict | None = None,
                              exclude_vehicle_ids: set | None = None,
                              cargo_hazmat: dict | None = None,
                              cargo_aboard: dict | None = None) -> nx.DiGraph:
    """Build the (hub, time) node graph with scheduled-leg edges.

    `hubs`/`routes` may be lists or {id: obj} dicts. `live_positions` maps
    vehicle_id -> (lat, lng) from Redis; `exclude_vehicle_ids` drops offline
    vehicles; `cargo_hazmat` maps vehicle_id -> hazmat classes already aboard;
    `cargo_aboard` maps vehicle_id -> [{shipment_id, drop_hub, deadline, priority}]
    protected by the no-harm rule (see `cargo_aboard_from`).
    """
    hubs = hubs if isinstance(hubs, dict) else {h.id: h for h in hubs}
    routes = routes if isinstance(routes, dict) else {r.id: r for r in routes}
    b = _Builder(hubs, routes, current_time, cargo_hazmat or {}, cargo_aboard or {})
    b.g.graph["hubs"] = hubs
    for v in vehicles:
        if exclude_vehicle_ids and v.id in exclude_vehicle_ids:
            continue
        pos = (live_positions or {}).get(v.id)
        stops = vehicle_schedule(v, hubs, current_time, pos)
        if not stops:
            continue
        b.add_chain(v, stops, "main")
        b.add_detours(v, stops)
        b.add_live_detours(v, stops, pos)
    b.link_timelines()
    b.g.graph["rejected_detours"] = b.rejected
    return b.g


def nearest_hub(hubs: dict, lat: float, lng: float):
    return min(hubs.values(), key=lambda h: haversine(lat, lng, h.lat, h.lng))


def add_shipment_entry_node(graph: nx.DiGraph, shipment, detection_time: datetime) -> nx.DiGraph:
    """Copy of `graph` with a synthetic entry node for the shipment.

    The entry node is created at detection time (no ops-confirmation lag).
    A shipment not at a hub is first brought to the nearest hub by local
    pickup, which costs LOCAL_PICKUP_COST_PER_KM and takes travel time.
    """
    g = graph.copy()
    hubs = g.graph["hubs"]
    if shipment.current_hub_id and shipment.current_hub_id in hubs:
        hub, km = hubs[shipment.current_hub_id], 0.0
    else:
        hub = nearest_hub(hubs, shipment.current_lat, shipment.current_lng)
        km = haversine(shipment.current_lat, shipment.current_lng, hub.lat, hub.lng) \
            * config.ROAD_DISTANCE_FACTOR
    at_hub = detection_time + _hours(km, config.LOCAL_PICKUP_SPEED_KMH)
    entry = ("entry", shipment.id)
    g.add_node(entry, hub=hub.id, time=detection_time, kind="entry")
    hub_entry = ("hub", hub.id, at_hub)
    g.add_node(hub_entry, hub=hub.id, time=at_hub, kind="hub")
    g.add_edge(entry, hub_entry, kind="entry", km=km)
    later = sorted(n for n in g.nodes if n[0] == "hub" and n[1] == hub.id and n[2] > at_hub)
    if later:
        g.add_edge(hub_entry, later[0], kind="wait")
    g.graph["entry"] = entry
    return g


def _shipment_hazmat(shipment) -> set:
    return {f for f in (shipment.handling_flags or []) if f.startswith(HAZMAT_PREFIX)}


def edge_allowed_by_capacity(shipment, data) -> bool:
    if data.get("kind") != "leg":
        return True
    return (shipment.weight_kg <= data["remaining_kg"]
            and shipment.volume_cbm <= data["remaining_cbm"])


def edge_allowed_by_handling(shipment, data) -> bool:
    """Hazmat shipments may only use certified vehicles not carrying another class.

    ASSUMPTION: any two different hazmat classes are treated as incompatible.
    """
    if data.get("kind") != "leg":
        return True
    classes = _shipment_hazmat(shipment)
    if not classes:
        return True
    certified = set(data.get("hazmat_certifications") or [])
    aboard = set(data.get("cargo_hazmat") or [])
    return classes <= certified and not (aboard - classes)


def filter_by_capacity(graph, shipment) -> nx.DiGraph:
    return nx.subgraph_view(graph, filter_edge=lambda u, v: edge_allowed_by_capacity(
        shipment, graph.edges[u, v]))


def filter_by_handling(graph, shipment) -> nx.DiGraph:
    return nx.subgraph_view(graph, filter_edge=lambda u, v: edge_allowed_by_handling(
        shipment, graph.edges[u, v]))


def capacity_share(shipment, data) -> float:
    """Fraction of the vehicle the shipment occupies (drives its share of leg cost)."""
    return max(shipment.weight_kg / max(data["total_kg"], 1e-9),
               shipment.volume_cbm / max(data["total_cbm"], 1e-9))


def edge_cost(shipment, u_data, v_data, data) -> float:
    """₹ cost for this shipment to traverse one edge."""
    kind = data["kind"]
    if kind == "leg":
        return data["km"] * data["cost_per_km"] * capacity_share(shipment, data)
    if kind == "board":
        return config.HANDLING_COST_PER_TRANSFER + data.get("detour_km", 0.0) * data["cost_per_km"]
    if kind == "wait":
        hours = (v_data["time"] - u_data["time"]).total_seconds() / 3600
        return config.HOLDING_COST_PER_HOUR * hours
    if kind == "entry":
        return data.get("km", 0.0) * config.LOCAL_PICKUP_COST_PER_KM
    return 0.0


def _weight_fn(graph, shipment, objective: str):
    def weight(u, v, data):
        if v[0] == "sink":
            return 0.0
        u_data, v_data = graph.nodes[u], graph.nodes[v]
        hours = max(0.0, (v_data["time"] - u_data["time"]).total_seconds() / 3600)
        cost = edge_cost(shipment, u_data, v_data, data)
        if objective == "fastest":
            return hours + cost * 1e-6
        if objective == "cheapest":
            return cost + hours * 1e-3
        return cost + hours * config.VALUE_OF_TIME_PER_HOUR
    return weight


def _with_sink(graph, dest_hub_id):
    g = nx.DiGraph(graph)
    sink = ("sink", dest_hub_id)
    g.add_node(sink, hub=dest_hub_id, time=None, kind="sink")
    for n, d in graph.nodes(data=True):
        if d.get("kind") == "hub" and d["hub"] == dest_hub_id:
            g.add_edge(n, sink, kind="sink")
    return g, sink


def summarize_path(graph, shipment, path) -> dict:
    """Turn a node path into legs, times, and costs."""
    nodes = [n for n in path if n[0] != "sink"]
    legs, cost, detour_km, first_departure, board_hubs = [], 0.0, 0.0, None, []
    for u, v in zip(nodes, nodes[1:]):
        data = graph.edges[u, v]
        cost += edge_cost(shipment, graph.nodes[u], graph.nodes[v], data)
        if data["kind"] == "board":
            detour_km += data.get("detour_km", 0.0)
            board_hubs.append(graph.nodes[u]["hub"])
            if first_departure is None:
                first_departure = graph.nodes[v]["time"]
        elif data["kind"] == "leg":
            legs.append({
                "vehicle_id": data["vehicle_id"], "route_id": data["route_id"],
                "from_hub": data["from_hub"], "to_hub": data["to_hub"],
                "departure_time": data["departure_time"], "arrival_time": data["arrival_time"],
                "km": round(data["km"], 1), "remaining_kg": data["remaining_kg"],
                "remaining_cbm": data["remaining_cbm"], "total_kg": data["total_kg"],
                "total_cbm": data["total_cbm"],
            })
    start = graph.nodes[nodes[0]]["time"]
    arrival = legs[-1]["arrival_time"] if legs else start
    hubs_visited = [legs[0]["from_hub"]] + [leg["to_hub"] for leg in legs] if legs else []
    vehicles = list(dict.fromkeys(leg["vehicle_id"] for leg in legs))
    return {
        "nodes": nodes,
        "legs": legs,
        "vehicles": vehicles,
        "hubs": hubs_visited,
        "transfers": max(0, len(board_hubs) - 1),
        "arrival_time": arrival,
        "cost": round(cost, 2),
        "detour_km": round(detour_km, 1),
        "first_hop_wait_hours": ((first_departure - start).total_seconds() / 3600
                                 if first_departure else 0.0),
        "distance_km": round(sum(leg["km"] for leg in legs) + detour_km, 1),
    }


def find_recovery_path(graph, entry_node, dest_hub_id, objective: str, shipment) -> dict | None:
    """Best path from entry to any node at the destination hub, or None."""
    g, sink = _with_sink(graph, dest_hub_id)
    try:
        path = nx.dijkstra_path(g, entry_node, sink, weight=_weight_fn(g, shipment, objective))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    return summarize_path(g, shipment, path)


def find_candidate_paths(graph, entry_node, dest_hub_id, objective: str, shipment) -> list[dict]:
    """Best path per distinct first vehicle boarded (one candidate per vehicle)."""
    g, sink = _with_sink(graph, dest_hub_id)
    weight = _weight_fn(g, shipment, objective)
    try:
        dist_from_entry, path_from_entry = nx.single_source_dijkstra(g, entry_node, weight=weight)
    except nx.NodeNotFound:
        return []
    entry_hub = g.nodes[entry_node]["hub"]
    best: dict[str, tuple[float, list]] = {}
    for u in path_from_entry:
        if u[0] != "hub" or u[1] != entry_hub:
            continue
        for _, v, data in g.out_edges(u, data=True):
            if data["kind"] != "board":
                continue
            try:
                d_rest, rest = nx.single_source_dijkstra(g, v, sink, weight=weight)
            except nx.NetworkXNoPath:
                continue
            total = dist_from_entry[u] + weight(u, v, data) + d_rest
            vid = data["vehicle_id"]
            if vid not in best or total < best[vid][0]:
                best[vid] = (total, path_from_entry[u] + rest)
    ranked = sorted(best.values(), key=lambda item: item[0])
    return [summarize_path(g, shipment, path) for _, path in ranked]


def find_fastest_path(graph, entry_node, dest_hub_id, shipment):
    return find_recovery_path(graph, entry_node, dest_hub_id, "fastest", shipment)


def find_cheapest_path(graph, entry_node, dest_hub_id, shipment):
    return find_recovery_path(graph, entry_node, dest_hub_id, "cheapest", shipment)


def find_weighted_path(graph, entry_node, dest_hub_id, shipment):
    return find_recovery_path(graph, entry_node, dest_hub_id, "weighted", shipment)


def get_hub_connectivity(hub_id: str, graph: nx.DiGraph) -> dict:
    """Scheduled legs boardable from a hub's timeline, earliest first."""
    departures = []
    for u, v, data in graph.edges(data=True):
        if data.get("kind") == "board" and u[0] == "hub" and u[1] == hub_id:
            for _, _, leg in graph.out_edges(v, data=True):
                if leg.get("kind") == "leg":
                    departures.append({
                        "vehicle_id": leg["vehicle_id"], "to_hub": leg["to_hub"],
                        "departure_time": leg["departure_time"],
                        "arrival_time": leg["arrival_time"],
                        "remaining_kg": leg["remaining_kg"], "remaining_cbm": leg["remaining_cbm"],
                    })
    departures.sort(key=lambda d: d["departure_time"])
    timeline = sorted(n[2] for n in graph.nodes if n[0] == "hub" and n[1] == hub_id)
    return {"hub_id": hub_id, "timeline_nodes": len(timeline), "departures": departures}


def build_hub_network(hubs, routes) -> nx.Graph:
    """Static hub-to-hub road network from active routes (used by the reroute strategy)."""
    hubs = hubs if isinstance(hubs, dict) else {h.id: h for h in hubs}
    g = nx.Graph()
    for r in routes:
        if not r.active:
            continue
        seq = r.hub_sequence
        for a, b in zip(seq, seq[1:]):
            km = road_km(hubs[a], hubs[b])
            if not g.has_edge(a, b) or g.edges[a, b]["km"] > km:
                g.add_edge(a, b, km=km, cost_per_km=r.cost_per_km,
                           speed_kmh=r.distance_km / max(r.estimated_time_hours, 1e-9),
                           route_id=r.id)
    return g
