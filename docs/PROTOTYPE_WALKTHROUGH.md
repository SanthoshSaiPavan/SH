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
Every 2 seconds it checks every shipment. Checks run in this order, and the first one
that fails decides the problem type:

| Check | What it looks for | Label |
|---|---|---|
| Route check | Parcel is at a hub that is not on its planned route | `wrong_hub` |
| Distance check | Parcel is more than 50 km from where it should be | `wrong_vehicle` |
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
| **Driver** | `/driver` | Phone-style view for a driver. Sends the phone's real GPS in LIVE mode. Right now only `driver101` may open it (a testing rule). |

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
| DRIVER | One truck each (101 to 104) | Sends GPS from a phone. The driver page is currently open to `driver101` only. |

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
   **PIGGYBACK OPPORTUNITY DETECTED: SHP-501 → TRUCK-102**, with pickup time, free space, cost, and savings.
3. Go to **Simulation** and change TRUCK-102's next stop (or slow it down). In about 5 seconds the
   recommendation **switches to TRUCK-104** and tells you why.
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

---

# Part 2: How the UI works, piece by piece

## 14. The frontend in one picture

```
main.tsx
 └─ App.tsx
     ├─ AuthProvider        who am I? (signs in automatically, holds the token)
     ├─ SocketProvider      one live connection to the backend
     ├─ LiveDataProvider    the shared "store" of hubs, trucks, shipments, alerts...
     └─ Router
         ├─ OperatorShell   (Navbar on top + a page + toasts)  ->  Dashboard, Map, Shipments,
         │                                                         Recovery, Analytics, Simulation
         └─ DriverShell     (only for drivers)                  ->  Driver page
```

Think of it as three layers stacked on each other. Each one needs the one above it:

1. **Auth** answers "who is logged in?"
2. **Socket** uses that login to open a live line to the server.
3. **Live data** listens on that line and keeps everything up to date.

Every page and component then just **reads** from the live data. They rarely fetch by themselves.

## 15. The three "hooks" that run everything (`src/hooks/`)

A *hook* is a small piece of shared logic. These three are the engine of the UI.

### `useAuth`: "Who am I?"
- There is **no login page**. On first load it signs in as `admin` using the demo accounts list in `lib/constants.ts`.
- It saves the token and user in the browser session (`session` in `lib/api.ts`).
- If the backend is down, it shows "Signing in..." and **retries every 3 seconds**.
- `switchUser("driver101")` clears the session and signs in as someone else (used by the user menu).
- `isOperator` is true for Admin and Operator. It decides which shell you see.

### `useSocket`: "The live line"
- Opens **one** Socket.IO connection, sending the token as a handshake.
- Reconnects on its own (waits 1 s, growing up to 10 s).
- Remembers which "rooms" you joined and **re-joins them after a reconnect**.
- `connectionId` goes up by one on every (re)connect. This tells other code "refetch the state once now".
- `useSocketEvent("name", handler)` is a helper: "run this function whenever the server sends this event". It cleans up by itself.
- If the server says the token is invalid, it signs in again.

### `useLiveData`: "The store" (the most important file)
It keeps these lists in memory: **hubs, vehicles, shipments, recommendations, active recoveries, progress, alerts, dashboard numbers, simulation status, toasts**.

How it stays fresh (**no polling, no timers**):

1. **On load (and after every reconnect):** it asks the REST API once for hubs, vehicles, shipments and opportunities.
2. **After that:** it only reacts to socket events.

| Event from server | What the UI does |
|---|---|
| `vehicle:location:update` | Moves the truck: new position, load, speed. |
| `vehicle:status` | Marks the truck live / delayed / offline. |
| `shipment:alert` | Adds an alert to the list, plays a beep (higher pitch for critical), refreshes that shipment and the dashboard numbers. |
| `shipment:created` | Fetches the new shipment. |
| `piggyback:recommendation` | Saves the newest recommendation. Shows a blue toast if it changed (e.g. "switched to TRUCK-104 because..."). |
| `recovery:started` | Removes the recommendation, shows a toast ("Auto-executed" or "Recovery started"). |
| `recovery:progress` | Updates the progress bar. Refetches the shipment only at hub or vehicle hand-offs. |
| `recovery:completed` | Plays a success beep, shows "recovered, saved ₹...", sets progress to 100%. |
| `simulation:tick` | Updates the clock, mode, running state and speed. |

Extra details:
- **Every reply from the API is checked with Zod** (`lib/schemas.ts`). If the backend sends something unexpected, the UI ignores it instead of crashing.
- If you open the page late, it **rebuilds alerts** for shipments already misplaced ("...(before this session)").
- `useShipments({...})` gives you a filtered, sorted list (by status, priority, hub type, search text).
- `useEngineNow()` gives "the current time" as the engine sees it: **simulated time in DEMO mode**, real time in LIVE mode. Deadlines and countdowns use this, so they match the simulation.

## 16. Small helper files (`src/lib/`)

| File | What it does |
|---|---|
| `api.ts` | `api.get / post / patch`: sends the token, checks the reply with Zod, throws a clear `ApiError` on failure. Also stores the session. |
| `schemas.ts` | The Zod shapes of everything the backend sends (copies of the backend's snake_case fields). |
| `constants.ts` | Colours and labels: priority (🔴🟠🟡🟢), status colours, the four strategy icons, connection colours, the map style, demo accounts. |
| `format.ts` | Turns raw values into readable text: `inr` (₹1,23,456), `pct`, `time`, `hours` (2h 05m), `title` (`wrong_hub` becomes `Wrong Hub`). |
| `maplibre.ts` | Sets up the map library. **Always import the map from here**, never from `maplibre-gl` directly, or the route lines silently break. |
| `roads.ts` | Fetches real road paths between hubs from the backend when the map needs them. |

## 17. The shared building blocks (`src/components/`)

### Navbar (top bar, on every operator page)
- Logo, then links: Dashboard, Map, Shipments, Recovery, Analytics, Simulation. The current page is highlighted.
- On the right: the **mode toggle**, the **engine clock** (⏱), a **connection light** (green "Live" / red "Reconnecting..."), a **🔔/🔇 sound button**, and the **user menu**.

### ModeToggle (`LIVE GPS | DEMO SIMULATION`)
- Clicking DEMO tells the backend to switch to demo mode **and start it**. Clicking LIVE switches to real phone GPS.
- Shows "(paused)" when demo is selected but stopped.
- It is the same control as on the Simulation page.

### UserMenu (round icon, top right)
- Shows your role and truck (e.g. "Driver TRUCK-101").
- Opens a dropdown of the 6 demo accounts. Picking one calls `switchUser`. Closes on outside click or Esc.

### StatsCard
A big number tile: icon, label, value, small hint, and a soft coloured glow. The Dashboard shows five of them.

### AlertPanel
A scrolling list of alerts. Each has a **coloured left edge by severity**, the shipment ID, the problem type, the time, and a message. **Clicking** one opens that shipment.

### Toasts
Small pop-ups at the bottom right (max 4 at a time, each vanishes after 6 s, or click to dismiss). Blue = info, green = success, red = error.

### ShipmentCard
One shipment as a card: priority emoji, ID, status badge, `origin → destination`, weight, **time left to deadline** (turns red under 2 h), and the problem type. It also shows:
- a **★ recommendation line** ("★ Piggyback → TRUCK-102 · 87/100"), and "escalated" if a human is needed;
- a **green progress bar** if a rescue is already running.

### ScoreGauge and ScoreBar
- **ScoreGauge:** a circular 0-100 dial. **Green ≥ 85** (auto-run level), **purple ≥ 50**, **amber below 50**, red at 0. It animates when the score changes.
- **ScoreBar:** a thin bar showing one score part (cost, time, capacity, reliability) from 0 to 1.

### Sidebar (filters, used on the Map page)
Tick boxes for **Hub type**, **Priority** and **Status**, plus a Clear button.

### LiveMap (the map, the biggest component)
Built with MapLibre on dark OpenStreetMap tiles. It draws:

| On the map | How |
|---|---|
| 🏢 **Hubs** | One marker per hub with the city name. Click for a popup (name, type, capacity). |
| 🚚 **Trucks** | One marker per truck, with a small **arrow showing heading** and a **coloured dot** (green live, amber delayed, red offline). Click for a popup (next stop, load %, speed). |
| 📦 **Shipments** | Only misplaced or recovering ones, with a **border in the priority colour**. Click to open the recovery popup. If a shipment is on a truck, it sits at the truck's position. |
| **Dashed indigo lines** | The planned route of every truck (remaining stops only). |
| **Purple glowing lines** | Recovery routes of rescues that are running. |
| **Cyan line** | A route you asked to "View on map". |

Smooth movement: the server sends positions every ~2 s. Instead of jumping, each truck marker **glides** to its new spot over 2 seconds (`MARKER_ANIMATION_MS`) using an animation loop.

It can also **fly to** a point (used when you click a shipment elsewhere). A small legend sits at the bottom-left.

### RecoveryModal (the decision popup, the heart of the UI)
Opens when you click a misplaced shipment. It is a big window.

**Top:** the shipment ID, priority, time left, weight/volume, problem type, destination, and a badge showing the mode: **Auto executed / Pending approval / Escalated**.

**Middle: one row per strategy** (Piggyback, Reroute, Dedicated, Hold). Each row has:
- a **ScoreGauge**, and a **★ RECOMMENDED** label with a purple glow on the best one;
- cost, savings vs dedicated, arrival time, deadline status (**✅ Safe / ⚠️ Tight (under 2 h spare) / 🔴 WILL MISS**), distance and detour, pickup time, free capacity;
- four small **score bars** with their weights (for example "Time ×0.6");
- buttons: **View on map**, **Approve** (operators only), **What if?** (on non-recommended rows);
- greyed out with the reason if the strategy is **not possible**.

**Reject:** type an optional reason and press **Reject & escalate** (hidden when already escalated).

**Piggyback candidates table:** the trucks Module 2 found, with pickup, arrival, detour, cost, each sub-score, and the final match score. The formula is printed above the table.

**Decision agent box:** press **Explain recommendation** to get the AI's plain sentence, plus three coloured chips (deadline risk, capacity risk, route risk), the difference vs a dedicated truck, and any warnings. There is also a box to **ask a question** ("why was this truck selected?"). If the AI is offline, it says "grounded template".

**Audit trail box:** press **Load** to see every logged decision for this shipment (time, operator decision, score, explanation).

**How it stays live:**
- It **joins the shipment's own socket room** while open and leaves when closed.
- If a new recommendation arrives for that shipment, it **reloads the scores**.
- When a recovery starts, it **closes itself**.
- **Approve** sends the chosen strategy to the backend, then closes.

## 18. The pages, one by one

### Dashboard (`/`)
1. **5 stat tiles:** active shipments, misplaced today (and how many still waiting), piggybacked now, recovery rate, cost saved today (and total).
2. **Opportunity banners** (top 3 by score) for misplaced shipments. Each shows a gauge, the headline ("PIGGYBACK OPPORTUNITY DETECTED" or "RECOMMENDED: REROUTE"), pickup and delivery ETA (with ✅/🔴), free capacity, cost and saving. If the AI switches trucks, an amber "↻ reason" line appears. **Click = open the RecoveryModal.**
3. **Alerts panel** (left) and **Active recoveries** (right). Each recovery shows shipment, truck, score, status, ETA (with time left), cost and a progress bar.
4. Clicking a **misplaced** shipment opens the popup. Clicking any **other** shipment jumps to the Map, focused on it.

### Map (`/map`)
- Left: the **Sidebar filters**. Right: the **LiveMap**, full height.
- It shows only shipments that are misplaced or being recovered, and respects the filters.
- All running recovery routes are drawn in purple automatically.
- It can be opened from another page with a target ("go to SHP-501" or "highlight this route"). It applies the target once, then clears it so a page reload does not repeat it. A **Clear highlighted route** button removes the cyan line.

### Shipments (`/shipments`)
- Search by ID or tracking number, plus filters for status and priority.
- Shows shipments as a list and lets you click one for the RecoveryModal.
- The count in the title updates as you filter.

### Recovery (`/recovery`)
Three columns, like a to-do board:
1. **⚠ Awaiting decision:** misplaced shipments, best score first. Click to decide.
2. **🔄 In progress:** rescues running, with progress bars.
3. **📜 History:** finished rescues: strategy, truck, score, cost, and how much was **saved vs a dedicated truck**. Reloaded whenever the set of active recoveries changes.

### Analytics (`/analytics`)
Charts made with Recharts, all reloaded when a recovery starts or ends (not on a timer):
- **Recovery outcomes** (donut): completed / failed / in progress, with a success rate.
- **Cost savings** (line): saved per day; shows last 24 h, week, month.
- **Strategy usage** (bars): share of each strategy.
- **Average recovery time** (bars): hours per strategy.
- **Misplacement heatmap:** a small map with circles per hub (bigger and darker = more misplacements) and a table below it.

The strategy colours here are a special colour-blind-friendly palette, separate from the rest of the app.

### Simulation (`/simulation`)
The remote control for the demo:
- **Mode:** LIVE GPS or DEMO SIMULATION.
- **Engine:** ▶ Start, ■ Stop, speed buttons (1×, 2×, 5×, 10×), an **Auto-recovery** tick box (auto-approves pending recommendations), and the tick counter.
- **Trigger misplacement:** pick a shipment (or random) and a type (or random 30/40/30), then press **⚠ Misplace**.
- **Vehicles table:** for each truck you see status, route (the next stop is highlighted), load %, and can **type a new speed or pick a new next stop, then Apply**. This is how the demo makes the recommendation switch trucks.

### Driver (`/driver`)
A simple phone screen for one truck:
- Big truck icon, the truck ID, socket status.
- **Start LIVE GPS / Stop sharing** button.
- Once on, it reads the phone's location and **sends it about every 2 seconds** (position, speed, heading).
- It shows the latest position, speed and how many updates were sent, or a "Rejected: ..." message if the server refuses one.
- If GPS is unavailable, it sends nothing, and the server will mark the truck delayed, then offline.
- **Test exception:** for `driver101` only, it keeps re-sending the last known position (a laptop with no GPS), so the truck stays online.
- Other drivers currently see an **Access denied** screen.

## 19. Quick guide to the look and feel

- **Dark theme** with cards, glass panels and soft glows.
- **Colour meaning is consistent everywhere:**
  - Priority: 🔴 critical, 🟠 high, 🟡 medium, 🟢 low.
  - Strategy: purple = piggyback, blue = reroute, amber = dedicated, grey = hold.
  - Truck connection: green = live, amber = delayed, red = offline.
  - Score dial: green ≥ 85, purple ≥ 50, amber below 50.
- Numbers are written the Indian way (₹1,23,456) and times use the engine's clock.
- New cards and toasts slide in.

## 20. One example: what happens when you click "Approve"

1. RecoveryModal sends `POST /api/recovery/execute` with the shipment and the chosen strategy.
2. The backend starts the rescue and emits `recovery:started`.
3. `useLiveData` hears it, removes the recommendation, shows a toast, and refreshes the shipment, the active list and the dashboard numbers.
4. The RecoveryModal also hears it and closes.
5. The Dashboard's "Active recoveries" and the Recovery page's "In progress" column show the new item.
6. As the truck moves, `recovery:progress` events fill the progress bar. On arrival, `recovery:completed` plays a chime and shows "recovered, saved ₹...".
7. The Analytics page reloads its charts.

No page refresh was needed at any step.
