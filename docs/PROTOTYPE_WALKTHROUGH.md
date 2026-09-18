# PiggyShip: Prototype Walkthrough (Plain English)

## 1. What problem does this solve?

A courier company moves thousands of parcels ("shipments") between cities through
warehouses called **hubs**. Sometimes a parcel goes wrong:

- It gets dropped at the **wrong hub**.
- It gets loaded on the **wrong truck**.
- It **sits still** for too long, or nobody scans it for hours.

Normally, someone has to notice this, then arrange an expensive special truck.

**PiggyShip does three things automatically:**

1. **Notices** a parcel is lost or misplaced.
2. **Finds the best way to rescue it**. The favourite trick is *piggybacking*: put the
   parcel on another truck that is already going the right way and has spare space.
3. **Shows it all live** on a control-tower dashboard, so a human can approve the fix.

(This is for Smart India Hackathon 2026, problem SH-205.)

---

## 2. The big picture

```
   Browser (React app)  <---- live updates (Socket.IO) ---->  Backend (Python / FastAPI)
   Dashboard, map,                                              |  detects problems
   shipments, etc.                                              |  finds rescue options
                                                                |  scores and picks the best
                                                   PostgreSQL <-+  (permanent data)
                                                   Redis      <-+  (fast live truck positions)
                                                   Ollama AI  <-+  (writes the "why" in words)
```

| Piece | What it is | Plain meaning |
|---|---|---|
| `backend/` | Python, FastAPI | The brain. Does all the thinking. |
| `frontend/` | React + TypeScript | The screens you look at. |
| PostgreSQL | Database | Stores hubs, trucks, shipments, rescue actions. |
| Redis | Fast memory store | Holds each truck's latest GPS position and "last seen" time. |
| Ollama (`gemma4:31b-cloud`) | AI model | Only *writes the explanation* in words. It never picks scores. |
| `docker/` | Docker file | Starts PostgreSQL and Redis with one command. |

---

## 3. The demo world (fake data we made)

When you run the seed script, it builds a small pretend country:

- **15 national hubs** (big Indian cities), plus two extra ones, **Warangal** and **Vijayawada**.
- **Trucks** with names like TRUCK-101 to TRUCK-104 (and more), each with capacity and a fleet.
- **About 30 shipments** in transit, each with a priority: 🔴 critical, 🟠 high, 🟡 medium, 🟢 low.
- **Users**: `admin`, `operator`, and drivers `driver101` to `driver104`.
- **Real road paths** between every pair of hubs (saved in `backend/data/road_routes.json`),
  so trucks drive along real roads on the map instead of straight lines.

**The star of the demo:** shipment **SHP-501** was supposed to go Hyderabad → Vijayawada,
but ended up at **Warangal** (wrong hub). TRUCK-101 to TRUCK-104 are the trucks around it.

---

## 4. The seven "modules" (how the brain works)

The original plan split the brain into 7 modules. Here is each one in simple words.

### Module 1: Spot the problem (`engines/anomaly_detector.py`)
Every 2 seconds it checks every shipment. A parcel has no GPS, so the checks only use
**scans** (what hub and truck crews record) and the **manifest** (which truck the parcel is
booked on). Checks run in this order, and the first one that fails decides the problem type:

| Check | What it looks for | Label |
|---|---|---|
| Excess scan | Parcel was scanned at a hub that is not on its planned route | `wrong_hub` |
| Manifest mismatch | Parcel was scanned onto a truck that doesn't go to its next hub | `wrong_vehicle` |
| Short scan | Its booked truck unloaded at the next hub and the parcel wasn't there | `stuck` |
| Time check | Parcel is taking 1.5× longer than expected | `stuck` |
| Scan check | No scan for over 6 hours | `stuck` |

Each problem gets a **severity** (based on how bad the type is and how urgent the parcel is).

### Module 2: Find piggyback rides (`engines/piggyback_matcher.py`)
Looks for trucks that could carry the lost parcel to its destination. It scores each
truck on: how soon it can pick up, spare space, deadline, route overlap, and cost.
It returns up to **5 candidates**, one per different first truck.

### Module 3: Compare all rescue strategies (`engines/recovery_engine.py`)
Four ways to rescue a parcel:

| Strategy | Meaning |
|---|---|
| **Piggyback** | Put it on a truck already going that way. Cheap. |
| **Reroute** | Send it on the next regular carrier service. |
| **Dedicated** | Send a special truck just for this parcel. Fast but costly. |
| **Hold** | Keep it at the hub and wait. |

Each is scored on **cost, time, spare capacity, reliability**. **Priority changes the
weights:** for a 🔴 critical parcel, time counts most (60%). For a 🟢 low parcel, cost
counts most (45%).

**Autonomy rule:** if the best score is **above 85** and the parcel is 🔴 critical, the system
does the rescue **by itself**. Otherwise, it waits for a human to press **Approve**.

### Module 4: The route map in maths (`engines/graph_network.py`)
A "time-expanded graph": think of it as a timetable of every truck leg and every hub visit.
A parcel can only board a truck if it can reach the hub **30 minutes before departure**, so
trucks that already left can never be chosen. It also allows small **detours** (up to 40 km).
Truck schedules are worked out from live position and speed; nothing is stored.

### Module 5: The simulator (`engines/simulation.py`, `fleet_progress.py`)
In DEMO mode, the app pretends time is passing. Trucks drive, arrive at hubs, load and
unload, and shipments get scanned and delivered. New shipments keep appearing (target: 30 active).
Once in a while it **randomly misplaces** a shipment so there is always something to rescue.
You can change speed (1×, 2×, 5×, 10×).

### Module 6: The AI explainer (`engines/decision_agent.py`)
A button called **Explain recommendation**. It sends the real numbers to the Ollama AI, which
writes a plain sentence such as "TRUCK-104 is best because...". **The AI never computes scores.**
If Ollama is offline, it falls back to a fixed template built from the same numbers.

### Module 7: Live updates (`realtime/`)
Uses Socket.IO so the screen updates without refreshing. Messages go only to the right
"rooms" (fleet, vehicle, shipment), never to everyone.

---

## 5. What runs in the background (4 loops)

| Loop | How often | Job |
|---|---|---|
| Engine loop | every 2 s | Move trucks (demo), detect problems, rebuild the graph, advance rescues. |
| Recommendation loop | every 5 s | Re-check misplaced parcels. Switch the recommendation only if the new one is clearly better. Auto-run the critical ones. |
| GPS save loop | regularly | Saves batches of truck positions to the database. |
| Status loop | every 3 s | Marks trucks **live / delayed / offline** (10 s stale, 30 s offline). Offline trucks are ignored. |

**One entrance for GPS:** whether a position is from the simulator or a real phone, it goes through
one function (`location_service.ingest`). It checks the data, saves it, tells the screens, and handles
hub arrivals, scans, pickups and deliveries.

---

## 6. The screens (frontend tour)

There is no login page. You are signed in as **admin** automatically. Use the **user icon (top right)** to
switch between Admin, Operator and Driver.

| Page | URL | What you see |
|---|---|---|
| **Dashboard** | `/` | Summary numbers, alerts, and the **PIGGYBACK OPPORTUNITY DETECTED** banner. |
| **Map** | `/map` | Live map (MapLibre + OpenStreetMap). Hubs 🏢, trucks moving on real roads. |
| **Shipments** | `/shipments` | List of all shipments as cards, with status and priority. |
| **Recovery** | `/recovery` | Active and past rescues. Open one to see options, scores, Approve / Reject. |
| **Analytics** | `/analytics` | Charts: recovery rate, cost savings, strategy usage, heatmap. |
| **Simulation** | `/simulation` | Controls: start/stop, speed, DEMO vs LIVE GPS, trigger a misplacement, edit a truck. |
| **Driver** | `/driver` | Phone-style view for a driver. Sends the phone's real GPS in LIVE mode. |

The **Recovery popup** shows every strategy, its score breakdown (gauges), and the buttons
**Explain recommendation**, **Approve**, **Reject**.

---

## 7. A shipment's life

```
in_transit --(problem detected)--> misplaced --(rescue approved)--> piggybacked or in_transit (with a plan) --> recovered
```

---

## 8. Roles (who can do what)

| Role | For | Notes |
|---|---|---|
| ADMIN | Full control | Default sign-in. |
| LOGISTICS_OPERATOR | Control tower staff | Approves rescues. |
| DRIVER | One truck each (101 to 104) | Sends GPS from a phone. |

The backend gives each account a JWT token and enforces the role, even without a login page.

---

## 9. How to run it

```bash
# 1. Databases
cd docker && docker compose up -d

# 2. Backend
cd backend
.venv/bin/python -m database.seed_data        # fresh demo data
.venv/bin/uvicorn app:socket_app --port 8000  # note: socket_app, not app

# 3. Frontend (new terminal)
cd frontend && npm run dev                    # open http://localhost:5173
```

Tests: `cd backend && .venv/bin/pytest -q` (no database needed). Frontend check: `npm run build`.

---

## 10. The demo script (try this!)

1. Choose **Operator** from the user menu. SHP-501 is flagged `wrong_hub` at Warangal.
2. Click **DEMO SIMULATION**. Trucks start moving. A banner appears:
   **PIGGYBACK OPPORTUNITY DETECTED: SHP-501 → TRUCK-104**, with the chance of arriving on time,
   pickup time, free space, cost, and savings.
3. Open the banner. TRUCK-102 is listed as **rejected by the no-harm rule**: it would be faster, but
   stopping at Warangal would make SHP-311 (🔴 critical, already on TRUCK-102) late.
   Go to **Simulation** and change TRUCK-104's next stop (or slow it down). In about 5 seconds the
   recommendation **switches** and tells you why.
4. Open the banner, read the scores, click **Explain recommendation**, then **Approve**.
   The assignment locks and SHP-501 is tracked to Vijayawada.
5. Press **Trigger misplacement** to create more problems. 🔴 critical ones scoring over 85 rescue themselves.

**LIVE GPS mode:** switch the toggle, open the app on a phone, pick a Driver. The truck on the map now follows
the phone. (Browsers only allow location on HTTPS or localhost.)

---

## 11. Decisions we made (please don't undo without asking)

- PostgreSQL + Redis, not SQLite.
- TypeScript everywhere in the frontend; MapLibre, not Leaflet.
- The AI uses Ollama `gemma4:31b-cloud`, with a template fallback.
- Strategy scoring uses **different weights per priority** (the original plan's formula could not change rankings).
- Extra database fields were added (vehicle hazmat/fleet, shipment last scan/current vehicle, users table).
- Any feature beyond the plan needs the user's OK first.

---

## 12. Where to find things

| I want to change... | Look in |
|---|---|
| Any number or threshold | `backend/config.py` (guesses are marked `ASSUMPTION`) |
| How problems are detected | `backend/engines/anomaly_detector.py` |
| How rescues are scored | `backend/engines/recovery_engine.py` |
| Truck and route logic | `backend/engines/graph_network.py`, `backend/utils/roads.py` |
| API endpoints | `backend/routes/*.py` |
| Live sockets and GPS | `backend/realtime/*.py` |
| Screens | `frontend/src/pages/*.tsx` |
| Map | `frontend/src/components/LiveMap.tsx` |
| Live data store | `frontend/src/hooks/useLiveData.tsx` |

## 13. Honest limits

- It is a **prototype**: the data is fake and many numbers are educated guesses (see `ASSUMPTION` in `config.py`).
- The AI explanation needs Ollama and internet. Without them, you get the simple template text.
- Road routes are cached, so new hubs need `python -m scripts.fetch_road_routes` to fetch their roads.
