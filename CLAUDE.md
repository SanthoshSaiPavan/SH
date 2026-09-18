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
- Seed = the plan's 15 national hubs + HUB-WGL-01/HUB-VJA-01 + route RT-09 for the TRUCK-101..104 / SHP-501 demo.
- The user wants to be asked before any feature is added beyond the plan.

## Architecture

One process: FastAPI REST + python-socketio (`app.py`), with four background asyncio tasks started in `lifespan`:
1. `engines/simulation.engine_loop` (every 2 s): in DEMO mode advances the sim clock, moves vehicles, and tops up
   in-transit shipments to `SIM_TARGET_ACTIVE_SHIPMENTS` (loaded onto vehicles dwelling at hubs; emits `shipment:created`); then
   Module 1 detection → rebuilds the time-expanded graph → advances reroute/dedicated recoveries → `simulation:tick`.
2. `realtime/recommendation_loop.run` (every 5 s): re-evaluates *dirty* misplaced shipments (Modules 2→3) and applies
   the switching rules (switch only if a new score beats the current one by `SWITCH_MARGIN`, or the current one became
   infeasible). It also executes auto (critical > 85) recoveries and unlocks locked recoveries whose vehicle can no longer pick up.
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
(`variant="detour:<hub>"`). Edge costs are computed per shipment at search time (`edge_cost`). Module 2 returns one candidate
per distinct first vehicle (`find_candidate_paths`). Vehicle schedules are *derived* from position, speed and
`ROAD_DISTANCE_FACTOR × haversine`; nothing is stored.

**Shipment lifecycle.** in_transit → (detected) misplaced → (executed) piggybacked | in_transit with `recovery_strategy` set
→ recovered. Detection skips shipments with `recovery_strategy` set. Scan-gap detection only applies to shipments not aboard a vehicle.

**Frontend.** `hooks/useLiveData.tsx` is the store: REST once on load/reconnect, then socket events only (no polling).
`hooks/useSocket.tsx` does the JWT handshake and re-joins rooms on reconnect. API responses are Zod-validated
(`lib/schemas.ts`); the backend's snake_case shapes are mirrored there. maplibre must be imported from `src/lib/maplibre.ts`,
which sets the Vite-bundled worker URL; importing `maplibre-gl` directly silently breaks all GeoJSON layers.
Chart series colours (`STRATEGY_CHART_COLORS`) are a CVD-validated palette, separate from the UI accent colours.

## Conventions
- Tunables live in `backend/config.py`. Mark any value the plan does not specify as `# ASSUMPTION`.
- Server→client socket events go to rooms (`fleet:FLEET-MAIN`, `vehicle:{id}`, `shipment:{id}`) via `emit_fleet`/`emit_to_rooms`, never a global broadcast.
- The LLM never produces scores. It only phrases `decision_agent.fact_sheet` data.
