# PiggyShip — Intelligent Shipment Piggybacking System

*Don't lose shipments. Rescue them.* — Smart India Hackathon 2026, problem SH-205.

PiggyShip detects misplaced shipments, searches a time-expanded graph of in-transit
vehicles for piggyback opportunities, scores four recovery strategies (piggyback,
reroute, dedicated vehicle, hold-at-hub), and streams everything to a control-tower
dashboard in real time over Socket.IO.

## Stack
FastAPI + python-socketio · PostgreSQL · Redis · NetworkX · React + TypeScript (Vite) ·
Tailwind · MapLibre GL + OpenStreetMap · Recharts · Zod · Ollama (`gemma4:31b-cloud`) for
the explanation agent.

## Setup

Commands are for Windows PowerShell (Python 3.10+, Node.js and Docker Desktop installed).

```powershell
# 1. PostgreSQL + Redis (Docker Desktop must be running)
cd docker
docker compose up -d
cd ..

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m database.seed_data   # drop + reseed demo data (also clears Redis state)
.venv\Scripts\uvicorn app:socket_app --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                                    # http://localhost:5173 (proxies /api and /socket.io)
```

The decision agent calls Ollama at `OLLAMA_URL` (default `http://localhost:11434`) with
`OLLAMA_MODEL` (default `gemma4:31b-cloud`, which needs internet). If Ollama is unreachable,
the agent returns a deterministic explanation built from the same scores.

### Demo accounts
There is no login page. The app signs in as `admin` on first load, and the user icon in the top
right switches between Admin, Operator and Driver (TRUCK-101 … 104). The backend still issues a
JWT per account and enforces roles.

| User | Password | Role |
|---|---|---|
| `admin` | `admin123` | ADMIN |
| `operator` | `operator123` | LOGISTICS_OPERATOR |
| `driver101` … `driver104` | `driver123` | DRIVER (TRUCK-101 … 104) |

## Demo script (Module 7 scenario)
1. Pick **Operator** from the user menu (top right). SHP-501 (🟠 High, 120 kg) is flagged `wrong_hub`:
   it was scanned as *excess* at Warangal, which is not on its Hyderabad → Vijayawada route.
   Detection uses scans and manifests only; a parcel has no GPS.
2. Click **DEMO SIMULATION**. Trucks go live, and the banner shows **PIGGYBACK OPPORTUNITY
   DETECTED: SHP-501 → TRUCK-104** with P(on-time), pickup/delivery ETA, free capacity, cost and saving.
3. Open the banner. **Rejected by the no-harm rule**: TRUCK-102 (Nagpur → Vijayawada, the road
   runs through Warangal) would arrive sooner, but stopping at Warangal makes SHP-311 (🔴 critical,
   aboard TRUCK-102) late. The Pareto strip shows the trade-offs ("+₹X buys Y h") and the
   sensitivity line shows the pick holds with each weight moved ±20%.
4. Open **Simulation** and reroute TRUCK-104 (or slow it down). Within ~5 s the recommendation
   switches and gives the reason.
5. Press **Explain recommendation**, then **Approve**. The assignment locks and SHP-501 is
   tracked to Vijayawada. Approving the same shipment twice is refused.
6. Use **Trigger misplacement** for more cases: wrong hub (excess scan), wrong vehicle
   (manifest mismatch at the loading scan), stuck (short when its truck unloads without it).
   🔴 critical shipments scoring > 85 with P(on-time) ≥ 95% are auto-executed.

LIVE GPS: switch the toggle to **LIVE GPS**, open the app on a phone and pick a
**Driver** from the user menu. Browsers only allow geolocation on HTTPS or localhost.

## Benchmark
`cd backend; .venv\Scripts\python -m scripts.benchmark` replays 500 seeded scenarios
(3 simultaneous misplacements each) against carrier default (hold for the next direct vehicle,
else dedicated), always-dedicated and greedy nearest-truck. The clock and seed are fixed, so the
output is reproducible; `--n`, `--seed`, `--batch`, `--json` change it.

## Tests
```powershell
cd backend
.venv\Scripts\pytest -q                       # engine tests (no DB needed)
cd ..\frontend
npm run build
npx oxlint src
```

## Where the logic lives
| Module | File |
|---|---|
| 1 Anomaly detection (scan-based) | `backend/engines/anomaly_detector.py`; scans are written in `fleet_progress.py` |
| 2 Piggyback matching | `backend/engines/piggyback_matcher.py` |
| 3 Recovery strategies + autonomy | `backend/engines/recovery_engine.py`, P(on-time) in `on_time.py`, joint assignment in `assignment.py` |
| 4 Time-expanded graph + no-harm rule | `backend/engines/graph_network.py`, `backend/engines/detours.py` |
| 5 Simulation / engine tick | `backend/engines/simulation.py`, `backend/engines/fleet_progress.py` |
| 6 LLM decision agent | `backend/engines/decision_agent.py` |
| 7 Real-time layer | `backend/realtime/*` |

Every tunable threshold is in `backend/config.py`. Values marked `ASSUMPTION` are not
specified by the implementation plan and were chosen as demo defaults.

## Road routes
Vehicles drive, and the map draws routes, along real roads. Road paths and distances for
every pair of hubs were fetched once from [OSRM](https://project-osrm.org/) (road data
© OpenStreetMap contributors, ODbL) and are cached in `backend/data/road_routes.json`, so
the demo needs no routing service at runtime. After adding hubs, fetch the new pairs with:

```powershell
cd backend
.venv\Scripts\python -m scripts.fetch_road_routes    # set OSRM_URL to use your own OSRM server
```
