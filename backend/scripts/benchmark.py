"""Replay benchmark (level-up report §6): PiggyShip vs three baselines on seeded scenarios.

Run from backend/:  .venv/bin/python -m scripts.benchmark [--n 500] [--seed 2026] [--batch 3]

Each scenario takes the seeded hub/route network, scatters every seeded vehicle to a random
point on its route with a random load, puts 1–3 protected shipments aboard each vehicle, and
misplaces `--batch` shipments at hubs at the same moment. Every policy rescues the same batch:

  carrier_default   hold for the next scheduled vehicle straight to the destination
                    (what carriers do today), else a dedicated vehicle
  always_dedicated  a dedicated vehicle every time
  greedy_nearest    the piggyback with the earliest pickup, no no-harm rule and no shared
                    capacity check across the batch (what a naive matcher does), else dedicated
  piggyship         Modules 2–4 with the no-harm rule, then the joint assignment

Metrics per rescue: ₹ cost, expected on-time rate (mean Monte Carlo P(on-time)), mean delay
past the deadline at planned speeds, extra truck-km driven (dedicated trip or detour km),
collateral lateness (shipments already aboard a host vehicle that its detour makes late) and
capacity overflows (vehicles given more weight/volume than they have free).
Everything runs in memory on a frozen clock, so a given --n/--seed/--batch always prints the
same numbers.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from types import SimpleNamespace

import config
from database.seed_data import PRIORITY_MIX, _position_between, build_seed
from engines import assignment
from engines import graph_network as gn
from engines import recovery_engine as re_
from utils import clock

POLICIES = ("carrier_default", "always_dedicated", "greedy_nearest", "piggyship")
FROZEN_NOW = datetime(2026, 1, 15, 6, 0)
CARGO_SLACK_HOURS = (0.1, 4.0)  # protected cargo is due this long after its planned arrival
DEADLINE_FACTOR = (1.1, 3.0)  # misplaced deadline = dedicated trip hours × factor
ON_ROUTE_SHARE = 0.7  # share of misplacements placed on some vehicle's remaining route


# ---- scenario generation -------------------------------------------------------------
def _vehicle(v, hubs, routes, rng):
    route = list(routes[v.route_id].hub_sequence)
    if rng.random() < 0.5:
        route.reverse()
    idx = rng.randint(1, len(route) - 1)
    lat, lng = _position_between(hubs, route, idx, rng.uniform(0.05, 0.95))
    used = rng.uniform(0.3, 0.9)
    return SimpleNamespace(
        id=v.id, route_id=v.route_id, planned_route=route, current_stop_index=idx,
        current_lat=lat, current_lng=lng, status="in_transit", speed_kmh=v.speed_kmh,
        total_capacity_kg=v.total_capacity_kg, used_capacity_kg=round(v.total_capacity_kg * used, 1),
        total_capacity_cbm=v.total_capacity_cbm,
        used_capacity_cbm=round(v.total_capacity_cbm * used, 2),
        hazmat_certifications=[])


def _cargo(vehicles, hubs, now, rng, tag):
    """Protected shipments aboard each vehicle, due shortly after their planned arrival."""
    out = []
    for v in vehicles:
        stops = gn.vehicle_schedule(v, hubs, now)
        for k in range(rng.randint(1, 3)):
            stop = rng.choice(stops)
            out.append(SimpleNamespace(
                id=f"{tag}-C-{v.id}-{k}", current_vehicle_id=v.id, status="in_transit",
                destination_hub_id=stop["hub"], priority=rng.choice(PRIORITY_MIX),
                deadline=stop["arrive"] + timedelta(hours=rng.uniform(*CARGO_SLACK_HOURS))))
    return out


def _misplaced(vehicles, hubs, now, rng, tag, n):
    ids = sorted(hubs)
    out = []
    for k in range(n):
        v = rng.choice(vehicles)
        remaining = v.planned_route[v.current_stop_index:]
        if rng.random() < ON_ROUTE_SHARE and len(remaining) >= 2:
            i = rng.randrange(len(remaining) - 1)
            at, dest = remaining[i], rng.choice(remaining[i + 1:])
        else:
            at, dest = rng.sample(ids, 2)
        origin = rng.choice([h for h in ids if h not in (at, dest)])
        km = gn.road_km(hubs[at], hubs[dest])
        trip_h = config.DEDICATED_DISPATCH_HOURS + km / config.DEDICATED_SPEED_KMH
        weight = round(rng.uniform(20, 400), 1)
        out.append(SimpleNamespace(
            id=f"{tag}-M{k}", priority=rng.choice(PRIORITY_MIX), weight_kg=weight,
            volume_cbm=round(weight / rng.uniform(150, 300), 2),
            deadline=now + timedelta(hours=trip_h * rng.uniform(*DEADLINE_FACTOR)),
            current_hub_id=at, current_lat=hubs[at].lat, current_lng=hubs[at].lng,
            destination_hub_id=dest, origin_hub_id=origin, expected_route=[origin, dest],
            actual_route=[origin, at], handling_flags=[], status="misplaced",
            misplacement_type="wrong_hub", current_vehicle_id=None))
    return out


# ---- policies --------------------------------------------------------------------------
def _dedicated(ev):
    return ev.strategy("dedicated")


def carrier_default(evs, **_):
    return {sid: (ev.strategy("hold") if ev.strategy("hold") and ev.strategy("hold").feasible
                  else _dedicated(ev)) for sid, ev in evs.items()}


def always_dedicated(evs, **_):
    return {sid: _dedicated(ev) for sid, ev in evs.items()}


def greedy_nearest(evs, **_):
    out = {}
    for sid, ev in evs.items():
        pigs = [s for s in ev.strategies if s.type == "piggyback" and s.feasible and s.legs]
        out[sid] = (min(pigs, key=lambda s: (s.legs[0]["departure_time"], s.id)) if pigs
                    else _dedicated(ev))
    return out


def piggyship(evs, shipments, capacity, **_):
    info = {s.id: {"priority": s.priority, "weight_kg": s.weight_kg,
                   "volume_cbm": s.volume_cbm} for s in shipments}
    options = {sid: [s for s in ev.strategies if s.feasible] for sid, ev in evs.items()}
    chosen = assignment.assign(info, options, capacity, {})
    return {sid: chosen.get(sid) or _dedicated(evs[sid]) for sid in evs}


# ---- metrics ------------------------------------------------------------------------------
def _collateral(strategy, harmful: dict) -> list[dict]:
    victims = {}
    for leg in strategy.legs or []:
        for v in harmful.get((leg["vehicle_id"], leg.get("variant", "main")), []):
            victims[v["shipment_id"]] = v
    return list(victims.values())


def _truck_km(strategy) -> float:
    if strategy.type == "dedicated":
        return strategy.distance_km
    return strategy.detour_km if strategy.type == "piggyback" else 0.0


def _overflows(chosen: dict, shipments, capacity: dict) -> int:
    load = defaultdict(lambda: [0.0, 0.0])
    by_id = {s.id: s for s in shipments}
    for sid, st in chosen.items():
        for vid in set(st.vehicles or []):
            load[vid][0] += by_id[sid].weight_kg
            load[vid][1] += by_id[sid].volume_cbm
    return sum(1 for vid, (kg, cbm) in load.items()
               if vid in capacity and (kg > capacity[vid][0] + 1e-9 or cbm > capacity[vid][1] + 1e-9))


def run(n: int, seed: int, batch: int) -> dict:
    clock.set_sim_time(FROZEN_NOW)
    now = clock.now()
    hubs_l, routes, base_vehicles, _, _ = build_seed()
    hubs = {h.id: h for h in hubs_l}
    route_map = {r.id: r for r in routes}
    rng = random.Random(seed)
    rows = {p: [] for p in POLICIES}
    overflow = Counter()
    for i in range(n):
        tag = f"S{i:04d}"
        vehicles = [_vehicle(v, hubs, route_map, rng) for v in base_vehicles]
        cargo = _cargo(vehicles, hubs, now, rng, tag)
        shipments = _misplaced(vehicles, hubs, now, rng, tag, batch)
        aboard = gn.cargo_aboard_from(cargo)
        safe = gn.build_time_expanded_graph(hubs, vehicles, routes, now, cargo_aboard=aboard)
        naive = gn.build_time_expanded_graph(hubs, vehicles, routes, now, cargo_aboard=aboard,
                                             enforce_no_harm=False)
        harmful = naive.graph.get("harmful_detours", {})
        capacity = {v.id: (v.total_capacity_kg - v.used_capacity_kg,
                           v.total_capacity_cbm - v.used_capacity_cbm) for v in vehicles}
        evs_safe = {s.id: re_.evaluate_shipment(s, safe, routes, now=now) for s in shipments}
        evs_naive = {s.id: re_.evaluate_shipment(s, naive, routes, now=now) for s in shipments}
        picks = {
            "carrier_default": carrier_default(evs_safe),
            "always_dedicated": always_dedicated(evs_safe),
            "greedy_nearest": greedy_nearest(evs_naive),
            "piggyship": piggyship(evs_safe, shipments=shipments, capacity=capacity),
        }
        by_id = {s.id: s for s in shipments}
        for policy, chosen in picks.items():
            overflow[policy] += _overflows(chosen, shipments, capacity)
            for sid, st in chosen.items():
                late = max(0.0, (st.arrival_time - by_id[sid].deadline).total_seconds() / 3600)
                victims = _collateral(st, harmful)
                rows[policy].append({
                    "type": st.type, "cost": st.cost, "p_on_time": st.on_time_probability,
                    "delay_h": late, "truck_km": _truck_km(st), "victims": len(victims),
                    "victim_hours": sum(v["late_hours"] for v in victims)})
    return {"n_scenarios": n, "batch": batch, "seed": seed, "rescues": n * batch,
            "policies": {p: _summary(rows[p], overflow[p]) for p in POLICIES}}


def _summary(rows: list[dict], overflows: int) -> dict:
    k = max(len(rows), 1)
    mix = Counter(r["type"] for r in rows)
    return {
        "cost_per_rescue": round(sum(r["cost"] for r in rows) / k, 2),
        "expected_on_time_pct": round(100 * sum(r["p_on_time"] for r in rows) / k, 1),
        "mean_delay_h": round(sum(r["delay_h"] for r in rows) / k, 2),
        "extra_truck_km_per_rescue": round(sum(r["truck_km"] for r in rows) / k, 1),
        "collateral_late_shipments": sum(r["victims"] for r in rows),
        "collateral_late_hours": round(sum(r["victim_hours"] for r in rows), 2),
        "capacity_overflows": overflows,
        "strategy_mix_pct": {t: round(100 * c / k, 1) for t, c in sorted(mix.items())},
    }


def print_table(result: dict) -> None:
    cols = [("cost_per_rescue", "₹/rescue"), ("expected_on_time_pct", "on-time %"),
            ("mean_delay_h", "delay h"), ("extra_truck_km_per_rescue", "truck-km"),
            ("collateral_late_shipments", "collateral late"),
            ("capacity_overflows", "overflows")]
    print(f"{result['n_scenarios']} scenarios × {result['batch']} misplacements "
          f"= {result['rescues']} rescues, seed {result['seed']}\n")
    print("| policy | " + " | ".join(c[1] for c in cols) + " | mix |")
    print("|---" * (len(cols) + 2) + "|")
    for p, s in result["policies"].items():
        mix = ", ".join(f"{t} {v}%" for t, v in s["strategy_mix_pct"].items())
        print(f"| {p} | " + " | ".join(str(s[c[0]]) for c in cols) + f" | {mix} |")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--batch", type=int, default=3)
    ap.add_argument("--json", help="also write the full result to this file")
    args = ap.parse_args(argv)
    t0 = time.time()
    result = run(args.n, args.seed, args.batch)
    print_table(result)
    print(f"\n({time.time() - t0:.0f} s)", file=sys.stderr)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
