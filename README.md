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

Commands are for Windows PowerShell (Python 3, Node.js and Docker Desktop installed).

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

### Demo logins
| User | Password | Role |
|---|---|---|
| `admin` | `admin123` | ADMIN |
| `operator` | `operator123` | LOGISTICS_OPERATOR |
| `driver101` … `driver104` | `driver123` | DRIVER (TRUCK-101 … 104) |

## Demo script (Module 7 scenario)
1. Log in as `operator`. SHP-501 (🟠 High, 120 kg) is flagged `wrong_hub` at Warangal
   (it should have gone Hyderabad → Vijayawada directly).
2. Click **DEMO SIMULATION**. Trucks go live, and the banner shows **PIGGYBACK OPPORTUNITY
   DETECTED: SHP-501 → TRUCK-102** with pickup/delivery ETA, free capacity, cost and saving.
3. Open **Simulation** and set TRUCK-102's next stop to Visakhapatnam (or slow it down).
   Within ~5 s the recommendation switches to TRUCK-104 and gives the reason.
4. Open the banner, review the scoring breakdown, press **Explain recommendation**, then
   **Approve**. The assignment locks and SHP-501 is tracked to Vijayawada.
5. Use **Trigger misplacement** for more cases (wrong hub / wrong vehicle / stuck);
   🔴 critical shipments scoring > 85 are auto-executed.

LIVE GPS: switch the toggle to **LIVE GPS**, log in as a driver on a phone and open
`/driver`. Browsers only allow geolocation on HTTPS or localhost.

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
| 1 Anomaly detection | `backend/engines/anomaly_detector.py` |
| 2 Piggyback matching | `backend/engines/piggyback_matcher.py` |
| 3 Recovery strategies + autonomy | `backend/engines/recovery_engine.py` |
| 4 Time-expanded graph | `backend/engines/graph_network.py` |
| 5 Simulation / engine tick | `backend/engines/simulation.py`, `backend/engines/fleet_progress.py` |
| 6 LLM decision agent | `backend/engines/decision_agent.py` |
| 7 Real-time layer | `backend/realtime/*` |

Every tunable threshold is in `backend/config.py`. Values marked `ASSUMPTION` are not
specified by the implementation plan and were chosen as demo defaults.
