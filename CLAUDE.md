# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PiggyShip: misplaced-shipment detection + piggyback recovery (SIH 2026, SH-205). The source spec is
`llm_implementation_plan (1).md`; where it contradicted itself, the decisions below were made
with the user and override it.

## Commands

```bash
docker/ : docker compose up -d                       # Postgres :5432 + Redis :6379 (podman: systemctl --user start podman.socket first)
backend/: .venv/bin/python -m database.seed_data     # drop + reseed DB and clear Redis vehicle:* keys
backend/: .venv/bin/uvicorn app:socket_app --port 8000   # the ASGI app is socket_app, not app
backend/: .venv/bin/pytest -q                        # engine tests, in-memory (no DB)
backend/: .venv/bin/python -m scripts.benchmark      # reproducible replay benchmark (~20 s)
backend/: .venv/bin/pytest -q tests/test_engines.py::test_demo_piggyback_candidates
frontend/: npm run dev                               # :5173, proxies /api and /socket.io to :8000
frontend/: npm run build                             # tsc -b + vite build (type check)
frontend/: npx oxlint src
```

Backend modules import from `backend/` as the root (`import config`, `from engines import …`);
run everything from `backend/` (pytest.ini sets `pythonpath = .`).

## Decisions made with the user (do not revert without asking)
- PostgreSQL + Redis (not SQLite). Frontend is TypeScript throughout, MapLibre (not Leaflet).
- Module 6 uses Ollama `gemma4:31b-cloud`. `decision_agent` falls back to a grounded template when Ollama fails.
- Module 3 uses per-tier weight sets (`config.STRATEGY_WEIGHTS`) instead of the plan's additive `0.20 × priority_multiplier`.
- Schema additions: `vehicles.hazmat_certifications`, `vehicles.fleet_id`, `shipments.last_scan_at`, `users` table,
  plus `shipments.current_vehicle_id` (normal carriage assignment).
- Seed = the plan's 15 national hubs + HUB-WGL-01/HUB-VJA-01 + route RT-09 for the TRUCK-101..104 / SHP-501 demo,
  plus RT-10 (NAG→VJA, through Warangal): TRUCK-102 rides it carrying SHP-311 (critical), so the no-harm rule rejects
  TRUCK-102 for SHP-501 and TRUCK-104 is the pick.
- Level-up (from the level-up report, items 1–6): detection is scan-based (`scan_events` table,
  `shipments.manifest_vehicle_id`; no parcel geofence). The no-harm rule is a hard rule: a detour that makes any
  shipment aboard the host vehicle lose its deadline is not added to the graph. P(on-time) (Monte Carlo,
  `engines/on_time.py`) replaces the Module 3 time component; tier thresholds `ONTIME_THRESHOLD` gate auto-execution.
  The recommendation is the best score on the cost × arrival Pareto front. All misplaced shipments are assigned
  jointly each cycle (`engines/assignment.py`, scipy milp). No CO₂ metric. Handover pack / photo intake / loading
  block / root-cause board were not selected.
- The user wants to be asked before any feature is added beyond the plan.

## Architecture

One process: FastAPI REST + python-socketio (`app.py`), with four background asyncio tasks started in `lifespan`:
1. `engines/simulation.engine_loop` (every 2 s): in DEMO mode advances the sim clock, moves vehicles, and tops up
   in-transit shipments to `SIM_TARGET_ACTIVE_SHIPMENTS` (loaded onto vehicles dwelling at hubs; emits `shipment:created`); then
   Module 1 detection → rebuilds the time-expanded graph → advances reroute/dedicated recoveries → `simulation:tick`.
2. `realtime/recommendation_loop.run` (every 5 s): re-evaluates *dirty* misplaced shipments (Modules 2→3), then assigns
   ALL misplaced shipments jointly (`engines/assignment.assign`: per-vehicle kg/cbm limits; stickiness via `SWITCH_MARGIN`
   so a pick only switches if beaten by the margin, became infeasible, or lost capacity to a higher-priority shipment).
   It also executes auto (critical > 85 and P(on-time) ≥ threshold) recoveries and unlocks locked recoveries whose vehicle
   can no longer pick up. Graph builds, evaluations and assignment run in `asyncio.to_thread` with their own sessions;
   every execution path takes a per-shipment lock and re-reads the shipment (no double execution), and `approve`
   re-evaluates on the current graph.
3. `location_service.flush_loop`: batches GPS history into `vehicle_locations`.
4. `location_service.status_loop`: live/delayed/offline from Redis `vehicle:{id}:last_seen`. Offline vehicles are excluded from the graph.

**Single ingest path.** Every position, whether from the demo simulator (`realtime/gps_simulator.py`, service-account
DRIVER claims) or a real driver socket, goes through `location_service.ingest`. That function validates the update,
writes Redis, broadcasts to rooms, and calls `fleet_progress.on_position`, which handles hub arrival/departure,
shipment scans and deliveries, and recovery pickup/unload following the legs stored on `RecoveryAction.recovery_route`.

**Clock.** `utils/clock.now()` is simulated time in DEMO mode (2 sim-min per tick × speed) and wall time in LIVE mode.
All engine timestamps are naive UTC. Staleness (`last_seen`) uses wall time.

**Time-expanded graph (`engines/graph_network.py`).** Nodes are keyed tuples (`hub`/`dep`/`arr`/`entry`/`sink`), and each
carries `hub` + `time` attrs. Boarding edges come from a hub-timeline node at departure minus `HANDLING_BUFFER`, so legs
that already departed are unreachable by construction. Detours are shifted copies of a vehicle's remaining schedule
(`variant="detour:<idx>:<hub>"`, or `"detour:live:<hub>"` for a stop on the leg being driven); every detour node/edge has
`detour=True` and `hold` never uses one. No-harm rule (`engines/detours.py`): `cargo_aboard` shipments that meet their
deadline on the planned schedule but not the detoured one make the detour rejected (`g.graph["rejected_detours"]`). Edge costs are computed per shipment at search time (`edge_cost`). Module 2 returns one candidate
per distinct first vehicle (`find_candidate_paths`). Vehicle schedules are *derived* from position, speed and
`ROAD_DISTANCE_FACTOR × haversine`; nothing is stored.

**Road geometry.** `backend/data/road_routes.json` holds OSRM road paths + distances for every hub pair (committed; refresh with
`.venv/bin/python -m scripts.fetch_road_routes`, which only fetches missing pairs). `utils/roads.py` serves it: graph leg km,
ETAs, detour geometry, simulator movement and seed positions all use road geometry, falling back to great-circle ×
`ROAD_DISTANCE_FACTOR` for uncached pairs. The map fetches paths on demand via `GET /api/road-routes?pairs=A|B,…`.

**Shipment lifecycle.** in_transit → (detected) misplaced → (executed) piggybacked | in_transit with `recovery_strategy` set
→ recovered. Detection skips shipments with `recovery_strategy` set. Detection reads only scans (`Shipment.scans`) and
manifests, never a parcel's position: excess scan → wrong_hub, load onto a vehicle that doesn't serve the next hub →
wrong_vehicle, short (manifest vehicle unloads without it) / time / scan gap → stuck. `fleet_progress` writes the scans.

**Frontend.** `hooks/useLiveData.tsx` is the store: REST once on load/reconnect, then socket events only (no polling).
`hooks/useSocket.tsx` does the JWT handshake and re-joins rooms on reconnect. API responses are Zod-validated
(`lib/schemas.ts`); the backend's snake_case shapes are mirrored there. maplibre must be imported from `src/lib/maplibre.ts`,
which sets the Vite-bundled worker URL; importing `maplibre-gl` directly silently breaks all GeoJSON layers.
Chart series colours (`STRATEGY_CHART_COLORS`) are a CVD-validated palette, separate from the UI accent colours.

## Conventions
- Tunables live in `backend/config.py`. Mark any value the plan does not specify as `# ASSUMPTION`.
- Server→client socket events go to rooms (`fleet:FLEET-MAIN`, `vehicle:{id}`, `shipment:{id}`) via `emit_fleet`/`emit_to_rooms`, never a global broadcast.
- The LLM never produces scores. It only phrases `decision_agent.fact_sheet` data.
