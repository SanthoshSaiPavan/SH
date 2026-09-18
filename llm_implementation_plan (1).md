# 🧠 LLM Implementation Prompt — Intelligent Shipment Piggybacking System
## Copy this entire document and paste it into any LLM to build the application

---

## 🎯 PROJECT OVERVIEW

**Project Name:** PiggyShip — Intelligent Shipment Piggybacking System  
**Hackathon:** Smart India Hackathon 2026  
**Problem Statement:** SH-205  
**Domain:** Procurement & Logistics

### What to Build
Build a **full-stack web application** that acts as an intelligent shipment recovery system. The system must:
1. **Detect** misplaced or lost shipments in real-time using anomaly detection
2. **Find** opportunities to piggyback those shipments onto existing in-transit vehicles
3. **Evaluate** multiple recovery strategies by scoring them on cost, time, capacity, priority, and deadlines
4. **Recommend** the optimal recovery action — piggyback, reroute, dedicated vehicle, or hold-at-hub
5. **Visualize** everything on a real-time control tower dashboard with an interactive map

### Tech Stack
| Layer | Technology |
|-------|-----------|
| **Frontend** | React.js + TypeScript (Vite), Tailwind CSS |
| **Backend** | Python (FastAPI) — single backend for API, real-time layer, and engines |
| **Database** | PostgreSQL (SQLAlchemy ORM) — includes GPS location history |
| **Real-time state** | Redis — latest location/status of every active vehicle |
| **Maps** | MapLibre GL JS (open-source, no API token needed) with OpenStreetMap tiles |
| **Graphs/Charts** | Recharts |
| **Algorithm** | Python (NetworkX for graph algorithms, NumPy/SciPy for optimization) |
| **Real-time** | Socket.IO (python-socketio on the server, socket.io-client in React) — no polling |
| **Auth** | JWT, roles: ADMIN, LOGISTICS_OPERATOR, DRIVER |
| **Validation** | Pydantic (backend), Zod (frontend) |
| **Local infra** | Docker Compose for PostgreSQL + Redis |
| **Simulation** | GPS simulator with LIVE GPS / DEMO SIMULATION toggle (see Module 7) |

**Why one Python backend:** the recovery engines depend on NetworkX and the time-expanded graph (Module 4). Running a separate Node.js server only for sockets would mean two backends, two languages, and an extra service boundary to debug during the demo. python-socketio provides the same Socket.IO protocol, rooms, and reconnection behaviour, so the React client works exactly as it would against a Node server.

---

## 📐 APPLICATION ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │
│  │ Dashboard │ │ Live Map │ │ Alerts   │ │ Analytics/Reports  │ │
│  │ (Control  │ │ (Leaflet │ │ Panel    │ │ (Charts, KPIs,     │ │
│  │  Tower)   │ │  + OSM)  │ │          │ │  Recovery Metrics) │ │
│  └──────┬───┘ └────┬─────┘ └────┬─────┘ └─────────┬──────────┘ │
│         └──────────┼────────────┼──────────────────┘            │
│                    │  REST API + WebSocket                      │
├────────────────────┼───────────────────────────────────────────-┤
│                    │      BACKEND (FastAPI / Flask)             │
│  ┌─────────────────┼─────────────────────────────────────────┐ │
│  │  ┌──────────────▼──────────────┐                          │ │
│  │  │      API Gateway            │                          │ │
│  │  └──────────────┬──────────────┘                          │ │
│  │       ┌─────────┼─────────┬──────────┬──────────┐         │ │
│  │  ┌────▼───┐ ┌───▼────┐ ┌─▼──────┐ ┌─▼───────┐ ┌▼──────┐ │ │
│  │  │Anomaly │ │Piggy-  │ │Recovery│ │Route &  │ │Simula-│ │ │
│  │  │Detect  │ │back    │ │Strategy│ │Hub Graph│ │tion   │ │ │
│  │  │Engine  │ │Matcher │ │Engine  │ │Network  │ │Engine │ │ │
│  │  └────────┘ └────────┘ └────────┘ └─────────┘ └───────┘ │ │
│  └───────────────────────────────────────────────────────────┘ │
│                         │                                      │
│              ┌──────────▼──────────┐                           │
│              │   SQLite Database   │                           │
│              └─────────────────────┘                           │
└────────────────────────────────────────────────────────────────┘
```

---

## 📁 FOLDER STRUCTURE

```
piggyship/
├── backend/
│   ├── app.py                    # Main FastAPI app entry point (mounts Socket.IO)
│   ├── config.py                 # Configuration and constants
│   ├── requirements.txt          # Python dependencies
│   ├── database/
│   │   ├── db.py                 # Database connection and setup
│   │   ├── models.py             # ORM models (Shipment, Vehicle, Hub, Route)
│   │   └── seed_data.py          # Demo seed data for hackathon
│   ├── engines/
│   │   ├── anomaly_detector.py   # MODULE 1: Misplaced shipment detection
│   │   ├── piggyback_matcher.py  # MODULE 2: Piggyback matching algorithm
│   │   ├── recovery_engine.py    # MODULE 3: Recovery strategy scoring
│   │   ├── graph_network.py      # MODULE 4: Time-expanded graph (NetworkX)
│   │   ├── simulation.py         # MODULE 5: Simulation engine for demo
│   │   └── decision_agent.py     # MODULE 6: LLM recovery decision agent
│   ├── routes/
│   │   ├── shipments.py          # CRUD + status endpoints for shipments
│   │   ├── vehicles.py           # Vehicle tracking and capacity endpoints
│   │   ├── recovery.py           # Recovery action endpoints
│   │   ├── analytics.py          # Dashboard metrics and KPIs
│   │   ├── simulation.py         # Simulation control endpoints
│   │   └── agent.py              # LLM agent endpoints (explain, query, what-if, audit)
│   ├── realtime/                 # MODULE 7: Real-time tracking layer
│   │   ├── socket_server.py      # python-socketio server, rooms, event handlers
│   │   ├── location_service.py   # Validation, Redis state, batched history writes
│   │   ├── recommendation_loop.py# Throttled re-evaluation + switching rules
│   │   ├── gps_simulator.py      # TRUCK-101..104 demo routes
│   │   └── auth.py               # JWT + role checks (HTTP and socket handshake)
│   └── utils/
│       ├── scoring.py            # Weighted scoring utility functions
│       └── geo.py                # Haversine distance, geofence utilities
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── src/
│   │   ├── App.jsx               # Main app with routing
│   │   ├── main.jsx              # Entry point
│   │   ├── index.css             # Global styles and design system
│   │   ├── components/
│   │   │   ├── Navbar.jsx        # Top navigation bar
│   │   │   ├── Sidebar.jsx       # Left sidebar with filters
│   │   │   ├── LiveMap.tsx       # MapLibre map with animated vehicle/shipment markers
│   │   │   ├── ShipmentCard.jsx  # Individual shipment status card
│   │   │   ├── AlertPanel.jsx    # Real-time alert notifications
│   │   │   ├── RecoveryModal.jsx # Recovery strategy comparison modal
│   │   │   ├── StatsCard.jsx     # KPI stat card component
│   │   │   └── ScoreGauge.jsx    # Visual gauge for recovery scores
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx     # Main control tower dashboard
│   │   │   ├── Shipments.jsx     # All shipments list with filters
│   │   │   ├── Recovery.jsx      # Active recovery operations
│   │   │   ├── Analytics.jsx     # Charts, graphs, performance metrics
│   │   │   └── Simulation.jsx    # Simulation controls for demo
│   │   ├── hooks/
│   │   │   ├── useSocket.ts      # Socket.IO connection, auth, auto-reconnect, room joins
│   │   │   └── useShipments.js   # Shipment data fetching hook
│   │   └── utils/
│   │       ├── api.js            # Axios/fetch API client
│   │       └── constants.js      # Status colors, map config
│   └── public/
│       └── favicon.ico
├── docker/
│   └── docker-compose.yml        # PostgreSQL + Redis for local development
└── README.md
```

---

## 📊 DATABASE SCHEMA

### Table: `shipments`
```sql
CREATE TABLE shipments (
    id TEXT PRIMARY KEY,                    -- e.g., "SHP-20260918-0042"
    tracking_number TEXT UNIQUE NOT NULL,
    origin_hub_id TEXT NOT NULL,            -- FK to hubs
    destination_hub_id TEXT NOT NULL,       -- FK to hubs
    current_hub_id TEXT,                    -- FK to hubs (where it currently is)
    expected_route TEXT NOT NULL,           -- JSON array of hub IDs in order
    actual_route TEXT,                      -- JSON array of scanned hub IDs so far
    status TEXT NOT NULL DEFAULT 'in_transit',
    -- status ENUM: 'at_origin', 'in_transit', 'misplaced', 'piggybacked',
    --              'recovered', 'delivered', 'delayed'
    priority TEXT NOT NULL DEFAULT 'medium',-- 'critical', 'high', 'medium', 'low' (🔴🟠🟡🟢 — see Priority Tiers)
    handling_flags TEXT,                   -- JSON array, e.g. ["hazmat_class_3", "oversized", "fragile"]
    weight_kg REAL NOT NULL,
    volume_cbm REAL NOT NULL,              -- cubic meters
    deadline TIMESTAMP NOT NULL,           -- delivery deadline
    current_lat REAL,
    current_lng REAL,
    misplacement_type TEXT,                -- 'wrong_hub', 'wrong_vehicle', 'stuck', NULL
    misplacement_detected_at TIMESTAMP,
    recovery_strategy TEXT,                -- 'piggyback', 'reroute', 'dedicated', 'hold'
    recovery_vehicle_id TEXT,              -- FK to vehicles (if piggybacked)
    recovery_score REAL,                   -- 0-100 score of chosen recovery
    recovery_mode TEXT,                    -- 'auto_executed', 'pending_approval', 'escalated' (see Module 3)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Priority Tiers (color-coded)

`priority` and `handling_flags` are deliberately separate: priority is the cost-vs-speed tradeoff; handling_flags are hard eligibility rules (a hazmat or oversized shipment isn't "medium priority," it's filtered out of the standard piggyback matcher entirely regardless of urgency).

| Tier | Maps to | priority_multiplier | Effect |
|------|---------|---------------------|--------|
| 🔴 Critical | Emergency/life-saving | 2.0 | Time weight ↑ to ~0.6, cost weight ↓ to ~0.1. Skip piggyback search if no near-instant match — go straight to dedicated. |
| 🟠 High | Perishables, high-value/security, JIT industrial | 1.5 | Favor speed; accept higher-cost piggyback/dedicated if it saves meaningful time. |
| 🟡 Medium | Fragile, standard general cargo | 1.0 | Baseline weights (0.30 cost / 0.30 time as originally planned). |
| 🟢 Low | Bulk/raw material, deferred/economy | 0.5 | Bias toward cost; hold-at-hub is a fine outcome. |

Hazmat and oversized cargo are handled via `handling_flags`, checked as a hard filter *before* Module 2 scoring runs (see Module 2).

### Table: `vehicles`
```sql
CREATE TABLE vehicles (
    id TEXT PRIMARY KEY,                    -- e.g., "VEH-TRK-0012"
    vehicle_type TEXT NOT NULL,             -- 'truck', 'van', 'trailer', 'rail'
    carrier_name TEXT NOT NULL,
    current_lat REAL NOT NULL,
    current_lng REAL NOT NULL,
    route_id TEXT,                          -- FK to routes
    planned_route TEXT NOT NULL,            -- JSON array of hub IDs
    current_stop_index INTEGER DEFAULT 0,
    total_capacity_kg REAL NOT NULL,
    used_capacity_kg REAL NOT NULL DEFAULT 0,
    total_capacity_cbm REAL NOT NULL,
    used_capacity_cbm REAL NOT NULL DEFAULT 0,
    speed_kmh REAL DEFAULT 60,
    status TEXT NOT NULL DEFAULT 'in_transit',
    -- status ENUM: 'idle', 'loading', 'in_transit', 'at_hub', 'completed'
    eta_destination TIMESTAMP,
    piggybacked_shipments TEXT,            -- JSON array of shipment IDs piggybacked on
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: `hubs`
```sql
CREATE TABLE hubs (
    id TEXT PRIMARY KEY,                    -- e.g., "HUB-DEL-01"
    name TEXT NOT NULL,                     -- e.g., "Delhi North Distribution Center"
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    hub_type TEXT NOT NULL,                 -- 'origin', 'distribution', 'transfer', 'destination'
    capacity_packages INTEGER NOT NULL,
    current_load INTEGER NOT NULL DEFAULT 0,
    can_hold_misplaced BOOLEAN DEFAULT TRUE,
    operating_hours TEXT,                   -- e.g., "06:00-22:00"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table: `routes`
```sql
CREATE TABLE routes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,                     -- e.g., "DEL-MUM Express"
    hub_sequence TEXT NOT NULL,             -- JSON array of hub IDs
    distance_km REAL NOT NULL,
    estimated_time_hours REAL NOT NULL,
    cost_per_km REAL NOT NULL,
    active BOOLEAN DEFAULT TRUE
);
```

### Table: `recovery_actions`
```sql
CREATE TABLE recovery_actions (
    id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,              -- FK to shipments
    action_type TEXT NOT NULL,              -- 'piggyback', 'reroute', 'dedicated', 'hold'
    matched_vehicle_id TEXT,               -- FK to vehicles (for piggyback)
    original_route TEXT,                   -- JSON: what route it was on
    recovery_route TEXT,                   -- JSON: the recovery path
    detour_km REAL,
    additional_cost REAL,
    time_impact_hours REAL,
    capacity_fit_score REAL,               -- 0-1 how well it fits capacity
    deadline_risk_score REAL,              -- 0-1 risk of missing deadline
    overall_score REAL NOT NULL,           -- 0-100 composite recovery score
    status TEXT DEFAULT 'proposed',
    -- status ENUM: 'proposed', 'approved', 'in_progress', 'completed', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
```

---

## ⚙️ MODULE 1: ANOMALY DETECTION ENGINE

**File:** `backend/engines/anomaly_detector.py`

### Logic
```
INPUT: All shipments with status 'in_transit'
OUTPUT: List of shipments flagged as 'misplaced' with classification

FOR each shipment in active_shipments:
    1. ROUTE DEVIATION CHECK:
       - Compare shipment.current_hub_id against shipment.expected_route
       - If current hub is NOT the next expected hub → flag as 'wrong_hub'
    
    2. GEOFENCE CHECK:
       - Calculate distance between shipment.current_lat/lng and the expected hub location
       - If distance > GEOFENCE_THRESHOLD_KM (e.g., 50km from expected path) → flag as 'wrong_vehicle'
    
    3. TIME ANOMALY CHECK:
       - Calculate expected transit time to next hub based on distance and avg speed
       - If actual_time > expected_time * TIME_TOLERANCE (e.g., 1.5x) → flag as 'stuck'
    
    4. SCAN GAP CHECK:
       - If no scan event received for > MAX_SCAN_GAP_HOURS (e.g., 6 hours) → flag as potential misplacement
    
    5. CLASSIFY AND SCORE:
       severity = calculate_severity(priority, deadline_proximity, misplacement_type)
       -- severity: 'critical' (>80), 'high' (60-80), 'medium' (40-60), 'low' (<40)
```

### Key Functions to Implement
```python
def detect_anomalies(shipments: List[Shipment]) -> List[AnomalyResult]:
    """Scan all in-transit shipments and return flagged anomalies"""

def check_route_deviation(shipment) -> Optional[str]:
    """Returns misplacement_type if shipment is off-route, None otherwise"""

def check_geofence(shipment, expected_hub) -> bool:
    """Returns True if shipment is outside geofence radius of expected hub"""

def check_time_anomaly(shipment, expected_hub) -> bool:
    """Returns True if transit time exceeds expected duration by tolerance factor"""

def calculate_severity(priority, hours_to_deadline, misplacement_type) -> float:
    """Returns severity score 0-100 based on urgency factors"""
```

---

## ⚙️ MODULE 2: PIGGYBACK MATCHING ALGORITHM

**File:** `backend/engines/piggyback_matcher.py`

**Architecture change:** Piggyback matching is no longer a standalone scan over all vehicles — it is now a **constrained shortest-path search over the time-expanded graph built by Module 4**. A valid piggyback candidate is simply a path through the graph, starting from the shipment's current `(hub, time)` node, that includes at least one edge (vehicle leg) with spare capacity for S. This means Module 2 and Module 4 share the same graph structure; Module 2 supplies the search objective and the hard filters, Module 4 supplies the nodes/edges/pathfinding.

### Hard filters (applied before any scoring — not part of the weighted score)
```
1. HANDLING ELIGIBILITY:
   - IF S.handling_flags includes 'oversized' → not eligible for standard piggyback matching at all;
     route directly to Module 3's dedicated/specialized-vehicle strategy.
   - IF S.handling_flags includes a hazmat class → only candidate edges whose vehicle is certified
     for that class, and not co-loaded with an incompatible class, are included in the graph search.

2. TRANSFER-TIMING FEASIBILITY (replaces the old standalone proximity check):
   - This is now structural, not a manual check: because nodes are (hub, time) pairs, a candidate
     edge (vehicle leg) simply does not exist in the graph if the vehicle already departed before
     S can reach that hub. No separate "is the vehicle still there" function is needed — the graph
     can't route through a leg that has already left.

3. CAPACITY:
   - available_weight = edge.vehicle.total_capacity_kg - edge.vehicle.used_capacity_kg
   - available_volume = edge.vehicle.total_capacity_cbm - edge.vehicle.used_capacity_cbm
   - IF S.weight_kg > available_weight OR S.volume_cbm > available_volume → edge is not traversable
     for S (excluded from the search, not merely penalized)
```

### Logic — The Core Innovation
```
INPUT: A misplaced shipment S (with current (hub, time) position), the time-expanded graph G
OUTPUT: Ranked list of piggyback candidate PATHS with compatibility scores

1. Apply hard filters above to prune G down to S's traversable subgraph.

2. SEARCH:
   - Run constrained shortest-path search (Dijkstra/A* variant) from S's current (hub, time) node
     toward any node at S.destination_hub.
   - Search objective depends on S.priority (see Priority Tiers):
       🔴 Critical → minimize arrival time only (cost ignored)
       🟠 High     → minimize arrival time, cost as tiebreaker
       🟡 Medium   → weighted cost/time objective (baseline)
       🟢 Low      → minimize cost, time as tiebreaker
   - Each returned path may cross multiple vehicle legs (multi-hop recovery via transfer hubs).

3. FOR each candidate path P:
   ROUTE ALIGNMENT SCORE:
       - overlap_ratio = (hubs shared with S's original expected_route / S.remaining_hubs)
   COST:
       - path_cost = sum of detour_cost across all edges in P
       - savings_ratio = 1 - (path_cost / dedicated_vehicle_cost)
   DEADLINE SAFETY:
       - safety_score = normalized buffer between P's arrival time and S.deadline

4. COMPOSITE SCORING (tiers 🟡/🟠 — 🔴 bypasses this and takes the fastest feasible path directly):
   score = (
       0.25 * proximity_score +       -- inherited from path's first-hop wait time (normalized 0-1)
       0.20 * capacity_fit_score +    -- better fit is better
       0.20 * deadline_safety_score + -- more time buffer is better
       0.20 * route_overlap_score +   -- more overlap is better
       0.15 * cost_savings_score      -- more savings is better
   ) * 100

5. ADD to candidates list with score

RETURN candidates (paths) sorted by score DESC
```

### Key Functions to Implement
```python
def find_piggyback_matches(shipment, graph: TimeExpandedGraph) -> List[PiggybackCandidate]:
    """Prune graph by hard filters, then search for ranked candidate paths"""

def apply_hard_filters(shipment, graph: TimeExpandedGraph) -> TimeExpandedGraph:
    """Returns the subgraph of edges S is eligible to use (handling + capacity)"""

def search_candidate_paths(shipment, graph: TimeExpandedGraph, objective: str) -> List[Path]:
    """Constrained shortest-path search; objective set by priority tier"""

def check_capacity_fit(shipment, edge) -> Tuple[bool, float]:
    """Returns (fits: bool, fit_score: 0-1) for a single graph edge"""

def calculate_route_overlap(shipment_route, path) -> float:
    """Returns overlap ratio 0-1 between S's original route and the candidate path"""

def calculate_path_cost(path) -> float:
    """Returns total additional cost for the candidate path"""

def composite_score(proximity, capacity, deadline, overlap, cost) -> float:
    """Weighted composite score 0-100"""
```

---

## ⚙️ MODULE 3: RECOVERY STRATEGY ENGINE

**File:** `backend/engines/recovery_engine.py`

### Logic
```
INPUT: A misplaced shipment S, piggyback candidates from Module 2
OUTPUT: Ranked recovery strategies with recommendation

GENERATE 4 strategy options:

STRATEGY 1 - PIGGYBACK (if candidates exist):
    - Use top piggyback candidate from Module 2
    - cost = detour_cost_only
    - time = current_time + pickup_time + remaining_transit
    - score = piggyback_match_score

STRATEGY 2 - REROUTE:
    - Use Module 4 (Graph Network) to find alternative path from current location to destination
    - cost = new_route_cost (may use different carrier)
    - time = new_route_estimated_time
    - score based on cost and time vs. original route

STRATEGY 3 - DEDICATED RECOVERY VEHICLE:
    - Dispatch a new vehicle just for this shipment
    - cost = full_trip_cost (highest cost option)
    - time = fastest (direct route)
    - score penalized for cost but rewarded for speed

STRATEGY 4 - HOLD AT HUB:
    - Keep shipment at current hub until next scheduled vehicle passes through
    - cost = minimal (just holding cost)
    - time = next_vehicle_eta (could be hours to days)
    - score based on how soon next vehicle arrives vs. deadline

FOR each strategy:
    weighted_score = (
        0.30 * cost_score +           -- lower cost = higher score (normalized)
        0.30 * time_score +           -- faster = higher score (normalized)
        0.20 * priority_multiplier +  -- critical shipments boost time weight
        0.10 * capacity_efficiency +  -- how well it uses existing resources
        0.10 * reliability_score      -- historical success rate of strategy type
    ) * 100

RETURN strategies sorted by weighted_score DESC
RECOMMEND strategy[0] as the optimal action
```

### Confidence-threshold autonomy (auto-execute vs. human approval)

This is what makes the engine "autonomous" rather than just a recommender — the system acts on its own for clear-cut cases, and defers to a human for everything else. This is a threshold rule on top of the scoring above, not a separate module.

```
AFTER strategies are ranked, determine shipment.recovery_mode:

IF shipment.priority == 'critical' AND strategy[0].score > AUTO_EXECUTE_THRESHOLD (e.g., 85):
    recovery_mode = 'auto_executed'
    → execute_recovery() fires immediately, no human wait
    → emit 'recovery_started' WebSocket event (system-initiated)

ELIF strategy[0].score is between LOW_CONFIDENCE_THRESHOLD and AUTO_EXECUTE_THRESHOLD (e.g., 50-85):
    recovery_mode = 'pending_approval'
    → surface top 2-3 strategies with full scoring breakdown in Recovery Modal
    → wait for 'approve_recovery' / 'reject_recovery' client event

ELSE (no strategy clears LOW_CONFIDENCE_THRESHOLD, or no piggyback/reroute candidates exist):
    recovery_mode = 'escalated'
    → flagged for manual review; no strategy pre-selected
```

Only 🔴 Critical shipments are eligible for auto-execution — everything else always goes through human approval, even at a high score. This is a deliberate scope limit, not a technical constraint: it keeps a visible decision point in the demo (the scoring breakdown modal) for the majority of cases, while still giving you a legitimate "autonomous" claim for the genuinely time-critical ones.

### Key Functions to Implement
```python
def generate_recovery_strategies(shipment, piggyback_candidates, graph) -> List[Strategy]:
    """Generate and score all 4 recovery strategies"""

def score_strategy(strategy, shipment) -> float:
    """Calculate weighted composite score for a strategy"""

def compare_strategies(strategies: List[Strategy]) -> Strategy:
    """Return the best strategy with comparison metrics"""

def determine_recovery_mode(shipment, ranked_strategies) -> str:
    """Apply confidence-threshold rule: 'auto_executed' | 'pending_approval' | 'escalated'"""

def execute_recovery(shipment_id, strategy_id) -> RecoveryAction:
    """Execute the chosen recovery strategy (update DB, notify)"""
```

---

## ⚙️ MODULE 4: GRAPH BUILDER — TIME-EXPANDED NETWORK MODEL

**File:** `backend/engines/graph_network.py`

**Why time-expanded, not plain hub graph:** A plain hub-to-hub graph (distance-weighted, as in v1 of this plan) can answer "what's the shortest physical path between two hubs" but not "is this specific vehicle actually going to be at this hub before my shipment needs it." Modeling time explicitly makes that constraint structural — you cannot route through a leg that already departed, because the node it would depart from doesn't exist at that time. This is also what lets Module 2's piggyback matching become a graph search instead of a separate scan-and-check algorithm (see Module 2).

### Logic
```
NODES = (hub_id, timestamp) pairs — NOT just physical hub locations.
    - Every scheduled arrival/departure at a hub is a distinct node.
    - This is what makes the search respect real schedules: you can't board
      a vehicle that already left, because there is no edge back in time.

EDGES = Scheduled vehicle legs, each annotated with:
    - remaining_capacity_kg / remaining_capacity_cbm
    - departure_time, arrival_time
    - cost_per_unit
    - vehicle_id, route_id

SPECIAL CASE — the misplaced shipment's own entry point:
    - When a shipment is flagged by Module 1, create a synthetic
      (current_hub_or_location, detection_time) node for it.
    - Edges out of this node = any vehicle leg the shipment can still
      physically catch (departure_time > detection_time + handling_buffer).
    - Decide explicitly whether this node is created the instant detection
      fires, or after a short lag representing "ops confirms shipment location" —
      this affects how tight your recovery windows look in the demo.

REBUILD STRATEGY (hackathon scope):
    - Rebuild the full graph on each simulation tick rather than maintaining
      incremental updates. At demo scale (~8-12 hubs, ~15-20 vehicles), a full
      rebuild is milliseconds — incremental graph maintenance is a real
      optimization for production but not worth the build time here.

Functions:
    1. build_time_expanded_graph() → Creates (hub,time) nodes + scheduled-leg edges from DB
    2. add_shipment_entry_node(shipment) → Inserts the synthetic current-position node
    3. find_fastest_path(entry_node, dest_hub) → minimize arrival time (🔴/🟠 objective)
    4. find_cheapest_path(entry_node, dest_hub) → minimize cost (🟢 objective, time as tiebreak)
    5. find_weighted_path(entry_node, dest_hub, weights) → baseline cost/time blend (🟡 objective)
    6. filter_by_capacity(graph, shipment) → prune edges that can't fit S (weight/volume)
    7. filter_by_handling(graph, shipment) → prune edges ineligible for S's handling_flags
    8. rebuild_on_tick() → called each simulation tick with latest schedule/capacity data
```

### Key Functions to Implement
```python
import networkx as nx

def build_time_expanded_graph(hubs, vehicles, routes, current_time) -> nx.DiGraph:
    """Build the (hub, time) node graph with scheduled-leg edges"""

def add_shipment_entry_node(graph, shipment, detection_time) -> nx.DiGraph:
    """Insert synthetic (location, time) node for a misplaced shipment + its outbound edges"""

def find_recovery_path(graph, entry_node, dest_hub_id, objective: str) -> dict:
    """Returns path, arrival_time, cost using the objective set by shipment.priority tier"""

def filter_by_capacity(graph, shipment) -> nx.DiGraph:
    """Returns subgraph of edges with enough remaining capacity for shipment"""

def filter_by_handling(graph, shipment) -> nx.DiGraph:
    """Returns subgraph of edges eligible under shipment.handling_flags (hazmat, oversized, etc.)"""

def get_hub_connectivity(hub_id, graph) -> dict:
    """Returns connected (hub,time) nodes and available scheduled legs"""
```

---

## ⚙️ MODULE 5: SIMULATION ENGINE

**File:** `backend/engines/simulation.py`

### Purpose
Since this is a hackathon demo, we need a simulation engine to generate realistic scenarios without real IoT data.

### Logic
```
SIMULATION LOOP (runs every 2 seconds in demo mode):

1. MOVE VEHICLES:
   - Update each vehicle's lat/lng based on speed and route
   - Progress vehicles along their planned route
   - When vehicle reaches a hub, mark it as 'at_hub' briefly, then continue

2. GENERATE EVENTS:
   - Every N ticks, randomly misplace a shipment:
     - Move it to a wrong hub (30% chance)
     - Put it on wrong vehicle (40% chance)
     - Make it stuck/delayed (30% chance)

3. TRIGGER DETECTION:
   - Run anomaly detection on all shipments
   - For each detected anomaly, run piggyback matching
   - Generate recovery strategies automatically

4. SIMULATE RECOVERY:
   - If auto-recovery is ON, execute best strategy automatically
   - Update shipment location as recovery progresses
   - Mark as 'recovered' when it reaches destination

5. EMIT EVENTS via WebSocket:
   - 'vehicle_moved' → update map markers
   - 'shipment_misplaced' → trigger alert
   - 'recovery_started' → show recovery route on map
   - 'shipment_recovered' → success notification
```

---

## ⚙️ MODULE 6: LLM RECOVERY DECISION AGENT

**File:** `backend/engines/decision_agent.py`

### Purpose
Modules 2–3 already compute the ranked strategies and scores. This module is a **thin reasoning layer on top of that output** — it does not re-decide anything. It takes the graph results, DB state, and scoring breakdown that already exist, and turns them into a natural-language explanation, a risk summary, and answers to ad-hoc operator questions. This is what makes the scoring transparent to a non-technical judge instead of just a number.

### Logic
```
INPUT: A shipment S, its ranked strategies (from Module 3), the graph path data (from Module 4)
OUTPUT: Explanation text, risk flags, and a recommended next action — grounded ONLY in
        the actual numbers already computed (no invented facts)

1. SITUATION ANALYSIS:
   - Summarize S's status, priority tier, deadline proximity, and why it was flagged (Module 1 output)

2. EXPLAINABLE RECOMMENDATION:
   - Take strategy[0]'s score breakdown (cost_score, time_score, capacity_fit, etc.)
   - Generate a plain-language explanation referencing the actual numbers,
     e.g. "Truck TS-09-XX was chosen because it passes within 23km with 40% spare
     capacity, arriving 3 hours before deadline — ₹1,150 cheaper than dedicated recovery."
   - The agent must not state a reason not backed by an actual field in the strategy object.

3. RISK ANALYSIS:
   - Flag deadline risk (buffer < some threshold), capacity risk (fit_score close to 1.0,
     little slack), route risk (single point of failure / no backup candidate), and
     extra cost vs. baseline

4. NATURAL-LANGUAGE QUERY HANDLING:
   - Accept operator questions in free text (e.g. "why was this truck selected?",
     "what's the cheapest safe recovery?", "which shipments may miss their deadline?")
   - Route the question to the relevant existing data (strategy scores, graph paths,
     shipment table) rather than letting the LLM answer from general knowledge
   - For aggregate questions ("which shipments may miss deadline?"), query the DB/graph
     directly and hand the LLM only the retrieved rows to summarize

5. WHAT-IF ANALYSIS:
   - Given an operator's hypothetical ("what if we hold this instead?"), re-run the
     relevant strategy's scoring (Module 3) for that option and compare against the
     current top recommendation — this reuses existing scoring functions, it does not
     ask the LLM to estimate a score itself

6. DECISION AUDIT TRAIL:
   - Every explanation + recommendation is logged with a timestamp, the strategy score
     it was based on, and (once available) the operator's actual approve/reject decision
```

### Key Functions to Implement
```python
def explain_recommendation(shipment, ranked_strategies) -> str:
    """Generate grounded natural-language explanation for strategy[0], citing actual scores"""

def summarize_risk(shipment, strategy) -> dict:
    """Returns {deadline_risk, capacity_risk, route_risk, cost_delta} flags"""

def answer_query(question: str, shipment_id: str = None) -> str:
    """Route a free-text operator question to the relevant DB/graph data, then summarize"""

def run_what_if(shipment, hypothetical_strategy_type: str) -> dict:
    """Re-score a hypothetical strategy via Module 3 and compare to the current top pick"""

def log_decision(shipment_id, explanation, risk_summary, operator_decision=None) -> AuditRecord:
    """Persist the agent's output + eventual human decision to the audit trail"""
```

### Table: `decision_audit_log`
```sql
CREATE TABLE decision_audit_log (
    id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,             -- FK to shipments
    recovery_action_id TEXT,               -- FK to recovery_actions (if one was generated)
    explanation TEXT NOT NULL,             -- natural-language reasoning, grounded in scores
    risk_summary TEXT,                     -- JSON: {deadline_risk, capacity_risk, route_risk, cost_delta}
    confidence_score REAL,                 -- copied from the strategy's overall_score
    operator_query TEXT,                   -- the free-text question, if this row is a Q&A response
    operator_decision TEXT,                -- 'approved', 'rejected', NULL if not yet actioned
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### New API Endpoints
```
GET    /api/agent/explain/:shipment_id     → Natural-language explanation for current top recommendation
GET    /api/agent/risk/:shipment_id        → Risk flags for current top recommendation
POST   /api/agent/query                    → {question, shipment_id?} → free-text answer
POST   /api/agent/what-if                  → {shipment_id, hypothetical_strategy} → comparison result
GET    /api/agent/audit-trail/:shipment_id → Full decision history for a shipment
```

### Demo-scope note
Ground every LLM call in the actual scored data — pass the strategy object's real fields into the prompt rather than asking the LLM to reconstruct or guess at numbers. This keeps the "explainability" feature honest (it explains real scoring, it doesn't hallucinate a plausible-sounding one) and avoids a bad live-demo moment where the explanation contradicts the number shown on screen.

---

## ⚙️ MODULE 7: REAL-TIME TRACKING LAYER

**Files:** `backend/realtime/socket_server.py`, `backend/realtime/location_service.py`, `backend/realtime/recommendation_loop.py`, `backend/realtime/gps_simulator.py`, `backend/realtime/auth.py`

### Purpose
Moves vehicle positions from the driver (or simulator) to the dashboard in real time, and keeps piggyback recommendations up to date as vehicles move. Modules 2–4 compute recommendations; this module decides when to recompute them and pushes the results to the right screens.

### End-to-end flow
```
Driver device / GPS simulator
    ↓  'vehicle:location' (every 1–2 s)
Socket.IO server (FastAPI + python-socketio)
    ↓  validate (auth, coordinate range, timestamp order)
Redis           ← latest state per vehicle (fast reads)
PostgreSQL      ← location history (batched writes)
    ↓
Socket.IO rooms → 'vehicle:location:update'
    ↓
React dashboard → smooth marker animation on MapLibre map
    ↓ (in parallel, throttled)
Recommendation loop → refresh graph ETAs → re-run Modules 2–3 → 'piggyback:recommendation'
```

### 1. Vehicle state (Redis)
```
Key:    vehicle:{vehicle_id}
Value:  {lat, lng, speed, heading, timestamp, used_capacity_kg, max_capacity_kg,
         status, current_route_id, destination_hub_id}
Key:    vehicle:{vehicle_id}:last_seen   → timestamp, used for stale/offline detection
```
Dashboards read the current state from Redis on initial load. PostgreSQL is never queried for live positions.

### 2. Location history (PostgreSQL)
```sql
CREATE TABLE vehicle_locations (
    id BIGSERIAL PRIMARY KEY,
    vehicle_id TEXT NOT NULL,              -- FK to vehicles
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    speed_kmh REAL,
    heading REAL,                          -- degrees, 0–360
    recorded_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_vehicle_locations_vehicle_time ON vehicle_locations (vehicle_id, recorded_at);
```
Write in small batches (e.g., buffer and insert every 5–10 seconds) rather than one INSERT per GPS ping. With four demo trucks this hardly matters, but it keeps the database off the hot path.

### 3. Socket rooms
```
vehicle:{vehicle_id}    → operators watching one vehicle
shipment:{shipment_id}  → operators watching one shipment (receives updates for its
                          candidate/assigned vehicles only)
fleet:{fleet_id}        → the control-tower map (all vehicles in a fleet)
```
When a location arrives, emit to `vehicle:{id}` and `fleet:{fleet_id}`, plus `shipment:{id}` for any shipment currently linked to that vehicle as a candidate or assignment.

### 4. Status indicators
```
🟢 live     → update received within STALE_AFTER_SECONDS (e.g., 10 s)
🟡 delayed  → vehicle is moving but its ETA has slipped past the planned schedule
🔴 offline  → no update for OFFLINE_AFTER_SECONDS (e.g., 30 s)
```
A background task checks `last_seen` every few seconds and emits `vehicle:status` when a status changes. An offline vehicle is excluded from new piggyback recommendations until it reports again. A vehicle that goes offline while carrying cargo can feed Module 1 as a possible `vehicle_failure` case.

### 5. Validation and reconnection
- Reject coordinates outside valid ranges (and outside India for the demo), timestamps older than the last accepted one, and implausible jumps (e.g., implied speed above 150 km/h). Log rejected updates; do not broadcast them.
- Client: socket.io-client auto-reconnect with backoff. On reconnect, re-join rooms and fetch current state from Redis once, so markers snap to the right positions.
- Driver: if GPS is unavailable, keep the last known position and let the status move to delayed/offline rather than sending fake coordinates.
- Backend restart: Redis keeps latest state, and clients re-join rooms on reconnect.

### 6. Authentication and roles
- JWT issued at login and required in the Socket.IO handshake (`auth: { token }`).
- DRIVER: may only emit `vehicle:location` for the vehicle assigned to them; the server checks the vehicle_id against the token.
- LOGISTICS_OPERATOR: may join rooms, view data, approve or reject recoveries.
- ADMIN: everything, plus managing vehicles and users.
- The GPS simulator authenticates as a service account with DRIVER permissions for its demo vehicles.

### 7. Dynamic recommendations (with stability rules)
Recommendations update as vehicles move, but recomputing on every 1–2 second ping would make the recommended truck flicker between near-equal candidates. Rules:

```
ON 'vehicle:location' for vehicle V:
    1. Update Redis, broadcast position (always, immediately)
    2. Update V's upcoming edge times in the time-expanded graph (Module 4) using the new ETA
    3. Mark misplaced shipments within RELEVANCE_RADIUS_KM of V's remaining route as "dirty"

EVERY RECOMPUTE_INTERVAL (e.g., 5 s), for each dirty shipment S:
    - Re-run Module 2 → Module 3 for S
    - IF S has no current recommendation → publish the top candidate
    - ELIF new top candidate's score > current recommendation's score + SWITCH_MARGIN (e.g., 5 points)
          → switch recommendation, emit 'piggyback:recommendation' with reason
    - ELIF current recommended vehicle is no longer feasible (went offline, lost capacity,
          missed the pickup window) → switch immediately to next best, or escalate
    - ELSE → keep current recommendation, update its ETA/score numbers only

ONCE a recovery is approved or auto-executed:
    - Lock the assignment. Stop switching vehicles for S.
    - Continue tracking; only if the locked vehicle becomes infeasible, raise a new alert.
```
This keeps the "recommendation updates automatically" behaviour for the demo without changing the answer every few seconds.

### 8. GPS simulator and demo toggle
- Vehicles TRUCK-101 to TRUCK-104 follow predefined routes over real Telangana/Andhra Pradesh road coordinates (e.g., Hyderabad → Warangal → Vijayawada corridor).
- Emits `vehicle:location` every 1–2 s per vehicle through the same socket path as a real driver, so the whole pipeline is exercised.
- Speed and route can be changed at runtime (e.g., reroute TRUCK-103) to demonstrate the recommendation switching.
- Dashboard toggle: **LIVE GPS | DEMO SIMULATION**. LIVE GPS accepts updates from a phone using the browser Geolocation API; DEMO SIMULATION runs the simulator. This is the same toggle as Module 5's simulation controls.

### 9. Frontend map behaviour
- Keep one MapLibre marker per vehicle; on each update, animate from the previous to the new position over the update interval (linear interpolation with requestAnimationFrame) and rotate by heading.
- Show vehicle markers 🚚, misplaced shipment markers 📦 (colored by priority tier), planned route lines, pickup point, and destination.
- Updates arrive over sockets into client state; the page never reloads.

### Demo scenario
```
1. SHP-501 (🟠 High, 120 kg, deadline 4:00 PM) is flagged misplaced at Warangal;
   destination Vijayawada.
2. Dashboard shows the 📦 marker and an alert immediately.
3. TRUCK-101 to TRUCK-104 move on the map in real time.
4. As TRUCK-102 approaches Warangal heading toward Vijayawada with 35% free capacity,
   the engine shows "PIGGYBACK OPPORTUNITY DETECTED" with score, pickup ETA,
   delivery ETA, free capacity, recovery cost, and saving vs dedicated vehicle.
5. Presenter reroutes TRUCK-102 (or slows it down); the recommendation switches to
   TRUCK-104 with the reason shown.
6. Operator approves; assignment locks; SHP-501 is tracked to delivery.
```

---

## 🎨 FRONTEND DESIGN SPECIFICATION

### Design System

```css
/* Color Palette - Dark Theme */
--bg-primary:      #0a0e1a;          /* Deep navy background */
--bg-secondary:    #111827;          /* Card backgrounds */
--bg-surface:      #1e2538;          /* Elevated surfaces */
--bg-glass:        rgba(30, 37, 56, 0.7);  /* Glassmorphism panels */

--text-primary:    #f0f4ff;          /* Main text */
--text-secondary:  #8892b0;          /* Muted text */
--text-accent:     #64ffda;          /* Highlighted text */

--accent-primary:  #6366f1;          /* Indigo - primary actions */
--accent-success:  #10b981;          /* Green - recovered/success */
--accent-warning:  #f59e0b;          /* Amber - alerts/delays */
--accent-danger:   #ef4444;          /* Red - critical/misplaced */
--accent-info:     #3b82f6;          /* Blue - information */
--accent-piggyback:#a855f7;          /* Purple - piggyback actions */

--border-subtle:   rgba(99, 102, 241, 0.2);
--shadow-glow:     0 0 20px rgba(99, 102, 241, 0.15);

--font-primary:    'Inter', sans-serif;
--font-mono:       'JetBrains Mono', monospace;

--radius-sm:       8px;
--radius-md:       12px;
--radius-lg:       16px;
--radius-xl:       24px;

--transition:      all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
```

### Page Layouts

#### 1. Dashboard Page (Main Control Tower)
```
┌─────────────────────────────────────────────────────────────────┐
│  🚚 PiggyShip  │  Dashboard  │ Shipments │ Recovery │ Analytics │
├────────┬────────────────────────────────────────────────────────┤
│        │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│  F     │  │Active│ │Mispl-│ │Piggy-│ │Recov-│ │Cost  │        │
│  I     │  │Ship- │ │aced  │ │backed│ │ery   │ │Saved │        │
│  L     │  │ments │ │Today │ │Now   │ │Rate  │ │Today │        │
│  T     │  │ 247  │ │  12  │ │  8   │ │ 94%  │ │$4.2K │        │
│  E     │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘        │
│  R     │                                                        │
│  S     │  ┌─────────────────────────────────────────────┐      │
│        │  │                                             │      │
│  ──    │  │            INTERACTIVE MAP                  │      │
│  Hub   │  │     (Leaflet with vehicle markers,          │      │
│  Type  │  │      shipment dots, route lines,            │      │
│  ──    │  │      recovery paths highlighted)            │      │
│  Prio  │  │                                             │      │
│  rity  │  │  🟢 = normal  🔴 = misplaced  🟣 = piggyback│      │
│  ──    │  │  --- = planned route                        │      │
│  Stat  │  │  === = recovery route (animated)            │      │
│  us    │  └─────────────────────────────────────────────┘      │
│        │                                                        │
│        │  ┌─────────────────────┐ ┌──────────────────────┐     │
│        │  │   ALERT PANEL       │ │  ACTIVE RECOVERIES   │     │
│        │  │ ⚠ SHP-042 misplaced │ │  SHP-031 → VEH-012  │     │
│        │  │ ⚠ SHP-087 delayed   │ │  Score: 87/100       │     │
│        │  │ 🔴 SHP-103 critical │ │  ETA: 2h 15m         │     │
│        │  └─────────────────────┘ └──────────────────────┘     │
└────────┴────────────────────────────────────────────────────────┘
```

#### 2. Recovery Modal (when clicking a misplaced shipment)
```
┌──────────────────────────────────────────────────────┐
│  RECOVERY OPTIONS for SHP-20260918-0042              │
│  Priority: HIGH  │  Deadline: 6h 30m remaining       │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ★ RECOMMENDED: PIGGYBACK onto VEH-TRK-0012         │
│  ┌────────────────────────────────────────────────┐  │
│  │  Score: 87/100  ████████████████░░░░           │  │
│  │  Detour: +23km  │  Extra Time: +35min          │  │
│  │  Cost: ₹450     │  Savings vs Dedicated: 72%   │  │
│  │  Capacity Fit: 89%  │  Deadline Safe: ✅        │  │
│  │  [VIEW ON MAP]  [APPROVE RECOVERY]              │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Option 2: REROUTE via HUB-BLR-02                    │
│  ┌────────────────────────────────────────────────┐  │
│  │  Score: 64/100  ████████████░░░░░░░░           │  │
│  │  Distance: 180km │ Time: 3h 20min              │  │
│  │  Cost: ₹1,200   │  Deadline: ⚠️ Tight          │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Option 3: DEDICATED VEHICLE                         │
│  ┌────────────────────────────────────────────────┐  │
│  │  Score: 52/100  ██████████░░░░░░░░░░           │  │
│  │  Direct: 95km   │  Time: 1h 45min (fastest)    │  │
│  │  Cost: ₹1,600   │  Deadline: ✅ Safe            │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Option 4: HOLD AT HUB (wait for next vehicle)       │
│  ┌────────────────────────────────────────────────┐  │
│  │  Score: 38/100  ████████░░░░░░░░░░░░           │  │
│  │  Wait: ~8 hours │  Cost: ₹120 (holding)        │  │
│  │  Next Vehicle: VEH-VAN-0044 at 18:30           │  │
│  │  Deadline: 🔴 WILL MISS                         │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
└──────────────────────────────────────────────────────┘
```

#### 3. Analytics Page
```
┌─────────────────────────────────────────────────────┐
│  ANALYTICS & PERFORMANCE                            │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────┐  ┌──────────────────────────┐│
│  │ Recovery Rate     │  │ Cost Savings Over Time   ││
│  │ (Donut Chart)     │  │ (Line Chart)             ││
│  │                   │  │                          ││
│  │  94% Success      │  │  ₹4.2K today             ││
│  │   4% Partial      │  │  ₹28K this week          ││
│  │   2% Failed       │  │  ₹112K this month        ││
│  └──────────────────┘  └──────────────────────────┘│
│                                                     │
│  ┌──────────────────┐  ┌──────────────────────────┐│
│  │ Strategy Usage    │  │ Avg Recovery Time        ││
│  │ (Bar Chart)       │  │ (Bar Chart by strategy)  ││
│  │                   │  │                          ││
│  │ Piggyback: 65%    │  │ Piggyback:  1.2 hrs     ││
│  │ Reroute:   20%    │  │ Reroute:    3.5 hrs     ││
│  │ Dedicated:  10%   │  │ Dedicated:  2.1 hrs     ││
│  │ Hold:       5%    │  │ Hold:       8.4 hrs     ││
│  └──────────────────┘  └──────────────────────────┘│
│                                                     │
│  ┌─────────────────────────────────────────────────┐│
│  │ Misplacement Heatmap (on map)                   ││
│  │ Shows which hubs/routes have most misplacements ││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## 🗺️ DEMO SEED DATA — Indian Logistics Network

### Hubs (15 hubs across India)
```json
[
    {"id": "HUB-DEL-01", "name": "Delhi Central Hub", "city": "Delhi", "lat": 28.6139, "lng": 77.2090, "type": "distribution", "capacity": 5000},
    {"id": "HUB-DEL-02", "name": "Delhi South Sorting", "city": "Delhi", "lat": 28.5245, "lng": 77.1855, "type": "transfer", "capacity": 2000},
    {"id": "HUB-MUM-01", "name": "Mumbai Main Hub", "city": "Mumbai", "lat": 19.0760, "lng": 72.8777, "type": "distribution", "capacity": 6000},
    {"id": "HUB-BLR-01", "name": "Bangalore Tech Hub", "city": "Bangalore", "lat": 12.9716, "lng": 77.5946, "type": "distribution", "capacity": 4000},
    {"id": "HUB-HYD-01", "name": "Hyderabad Central", "city": "Hyderabad", "lat": 17.3850, "lng": 78.4867, "type": "distribution", "capacity": 3500},
    {"id": "HUB-CHN-01", "name": "Chennai Port Hub", "city": "Chennai", "lat": 13.0827, "lng": 80.2707, "type": "distribution", "capacity": 4500},
    {"id": "HUB-KOL-01", "name": "Kolkata East Hub", "city": "Kolkata", "lat": 22.5726, "lng": 88.3639, "type": "distribution", "capacity": 3000},
    {"id": "HUB-JAI-01", "name": "Jaipur Transfer", "city": "Jaipur", "lat": 26.9124, "lng": 75.7873, "type": "transfer", "capacity": 1500},
    {"id": "HUB-LKO-01", "name": "Lucknow Sorting", "city": "Lucknow", "lat": 26.8467, "lng": 80.9462, "type": "transfer", "capacity": 1800},
    {"id": "HUB-AHM-01", "name": "Ahmedabad West", "city": "Ahmedabad", "lat": 23.0225, "lng": 72.5714, "type": "transfer", "capacity": 2200},
    {"id": "HUB-PUN-01", "name": "Pune Distribution", "city": "Pune", "lat": 18.5204, "lng": 73.8567, "type": "distribution", "capacity": 2500},
    {"id": "HUB-NAG-01", "name": "Nagpur Central India", "city": "Nagpur", "lat": 21.1458, "lng": 79.0882, "type": "transfer", "capacity": 2000},
    {"id": "HUB-BHO-01", "name": "Bhopal Relay", "city": "Bhopal", "lat": 23.2599, "lng": 77.4126, "type": "transfer", "capacity": 1200},
    {"id": "HUB-PAT-01", "name": "Patna East Hub", "city": "Patna", "lat": 25.6093, "lng": 85.1376, "type": "transfer", "capacity": 1000},
    {"id": "HUB-VIZ-01", "name": "Vizag Port Hub", "city": "Visakhapatnam", "lat": 17.6868, "lng": 83.2185, "type": "destination", "capacity": 1500}
]
```

### Sample Routes (major corridors)
```json
[
    {"id": "RT-01", "name": "Delhi-Mumbai Express", "hubs": ["HUB-DEL-01", "HUB-JAI-01", "HUB-AHM-01", "HUB-MUM-01"], "distance_km": 1400, "time_hours": 24, "cost_per_km": 18},
    {"id": "RT-02", "name": "Delhi-Bangalore Golden", "hubs": ["HUB-DEL-01", "HUB-BHO-01", "HUB-NAG-01", "HUB-HYD-01", "HUB-BLR-01"], "distance_km": 2150, "time_hours": 36, "cost_per_km": 16},
    {"id": "RT-03", "name": "Mumbai-Chennai Coastal", "hubs": ["HUB-MUM-01", "HUB-PUN-01", "HUB-BLR-01", "HUB-CHN-01"], "distance_km": 1350, "time_hours": 22, "cost_per_km": 17},
    {"id": "RT-04", "name": "Delhi-Kolkata Eastern", "hubs": ["HUB-DEL-01", "HUB-LKO-01", "HUB-PAT-01", "HUB-KOL-01"], "distance_km": 1500, "time_hours": 26, "cost_per_km": 15},
    {"id": "RT-05", "name": "Hyderabad-Vizag Coastal", "hubs": ["HUB-HYD-01", "HUB-VIZ-01"], "distance_km": 620, "time_hours": 10, "cost_per_km": 14},
    {"id": "RT-06", "name": "Delhi-Hyderabad Direct", "hubs": ["HUB-DEL-01", "HUB-BHO-01", "HUB-NAG-01", "HUB-HYD-01"], "distance_km": 1600, "time_hours": 27, "cost_per_km": 16},
    {"id": "RT-07", "name": "Mumbai-Pune Shuttle", "hubs": ["HUB-MUM-01", "HUB-PUN-01"], "distance_km": 150, "time_hours": 3, "cost_per_km": 20},
    {"id": "RT-08", "name": "Central India Cross", "hubs": ["HUB-NAG-01", "HUB-BHO-01", "HUB-AHM-01", "HUB-MUM-01"], "distance_km": 1100, "time_hours": 18, "cost_per_km": 15}
]
```

### Demo Scenario Script
```
TIME 0:00  → System starts with 30 shipments in transit, 12 vehicles moving
TIME 0:10  → SHP-042 gets misplaced at HUB-NAG-01 (was supposed to go to HUB-HYD-01, ended up at HUB-BHO-01)
TIME 0:12  → Anomaly detector flags SHP-042 as "wrong_hub" severity: HIGH
TIME 0:15  → Piggyback matcher finds VEH-TRK-0012 on RT-08 passing near HUB-BHO-01
             Score: 87/100 — 23km detour, fits in capacity, deadline safe
TIME 0:18  → Recovery approved (auto or manual)
TIME 0:20  → VEH-TRK-0012 detours to HUB-BHO-01, picks up SHP-042
TIME 0:35  → SHP-042 continues on VEH-TRK-0012's route toward Mumbai
TIME 0:50  → SHP-042 reaches HUB-MUM-01, transferred to local delivery
TIME 0:52  → SHP-042 marked as RECOVERED. Cost saved: ₹1,150 vs dedicated vehicle

SIMULTANEOUSLY:
TIME 0:25  → SHP-087 gets stuck at HUB-LKO-01 (scan gap detected)
TIME 0:28  → No piggybacking options nearby — HOLD AT HUB recommended
TIME 0:30  → SHP-103 critical shipment misplaced on wrong vehicle
TIME 0:32  → DEDICATED recovery approved due to critical priority
```

---

## 🔌 API ENDPOINTS

### Shipments
```
GET    /api/shipments                    → List all shipments (with filters)
GET    /api/shipments/:id                → Get shipment details
GET    /api/shipments/misplaced          → List all currently misplaced shipments
POST   /api/shipments                    → Create new shipment (for simulation)
PATCH  /api/shipments/:id/status         → Update shipment status
```

### Vehicles
```
GET    /api/vehicles                     → List all vehicles (with filters)
GET    /api/vehicles/:id                 → Get vehicle details + cargo
GET    /api/vehicles/nearby/:hub_id      → Find vehicles near a hub
PATCH  /api/vehicles/:id/position        → Update vehicle position (simulation)
```

### Recovery
```
GET    /api/recovery/options/:shipment_id  → Get all recovery strategies for a shipment
POST   /api/recovery/execute               → Execute a recovery strategy
GET    /api/recovery/active                → List all active recovery operations
GET    /api/recovery/history               → List completed recoveries
```

### Analytics
```
GET    /api/analytics/dashboard            → KPI summary (counts, rates, costs)
GET    /api/analytics/recovery-rate        → Recovery success rate over time
GET    /api/analytics/cost-savings         → Cost savings breakdown
GET    /api/analytics/strategy-usage       → Strategy type distribution
GET    /api/analytics/heatmap              → Misplacement frequency by hub
```

### Simulation
```
POST   /api/simulation/start              → Start the simulation engine
POST   /api/simulation/stop               → Stop simulation
POST   /api/simulation/trigger-misplacement → Manually trigger a misplacement event
POST   /api/simulation/speed              → Set simulation speed (1x, 2x, 5x, 10x)
GET    /api/simulation/status             → Get current simulation state
```

### WebSocket Events (Socket.IO)
```
DRIVER / SIMULATOR → SERVER:
    'vehicle:location'          → {vehicle_id, lat, lng, speed, heading, timestamp}

SERVER → CLIENT (sent to rooms, not broadcast to everyone — see Module 7):
    'vehicle:location:update'   → {vehicle_id, lat, lng, speed, heading, timestamp}
    'vehicle:status'            → {vehicle_id, status: 'live' | 'delayed' | 'offline'}
    'shipment:alert'            → {shipment_id, type, severity, message}
    'piggyback:recommendation'  → {shipment_id, vehicle_id, score, pickup_eta, delivery_eta,
                                   available_capacity, recovery_cost, cost_saving}
    'recovery:started'          → {shipment_id, strategy, vehicle_id, route}
    'recovery:progress'         → {shipment_id, percent_complete, eta}
    'recovery:completed'        → {shipment_id, cost_saved, time_taken}
    'simulation:tick'           → {tick_number, timestamp, events_count}

OPERATOR CLIENT → SERVER:
    'room:join' / 'room:leave'  → {room: 'vehicle:{id}' | 'shipment:{id}' | 'fleet:{id}'}
    'recovery:approve'          → {shipment_id, strategy_id}
    'recovery:reject'           → {shipment_id, reason}
```

Live tracking uses these socket events only. No page refresh, no frontend `setInterval` polling, and no repeated REST GETs for location. REST endpoints are used for initial page load and history, not for live updates.

### Additional REST Endpoints (Module 7)
```
GET    /api/vehicles/:id/location-history → Stored GPS trail from PostgreSQL
GET    /api/piggyback/opportunities       → Current live recommendations (initial page load only)
POST   /api/auth/login                    → Returns JWT with role
```

---

## 🔧 UTILITY FUNCTIONS

### Haversine Distance (geo.py)
```python
import math

def haversine(lat1, lng1, lat2, lng2) -> float:
    """Calculate great-circle distance in km between two points"""
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlng/2)**2)
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def is_within_geofence(point_lat, point_lng, center_lat, center_lng, radius_km) -> bool:
    """Check if a point is within a circular geofence"""
    return haversine(point_lat, point_lng, center_lat, center_lng) <= radius_km

def point_to_line_distance(point, line_start, line_end) -> float:
    """Calculate minimum distance from a point to a line segment (for route proximity)"""
    # Implementation using vector projection
```

### Scoring Utilities (scoring.py)
```python
def normalize(value, min_val, max_val) -> float:
    """Normalize a value to 0-1 range"""
    if max_val == min_val:
        return 0.5
    return max(0, min(1, (value - min_val) / (max_val - min_val)))

def inverse_normalize(value, min_val, max_val) -> float:
    """Inverse normalize (lower is better, e.g., cost)"""
    return 1 - normalize(value, min_val, max_val)

def weighted_score(scores: dict, weights: dict) -> float:
    """Calculate weighted composite score"""
    total = sum(scores[k] * weights[k] for k in scores)
    return round(total * 100, 2)
```

---

## 🚦 IMPLEMENTATION ORDER

Follow this exact sequence to build the application:

```
PHASE 1: Foundation (Backend Core)
  1. Set up FastAPI project with folder structure
  2. Create database models and SQLite setup
  3. Write seed_data.py with Indian logistics network
  4. Implement utility functions (geo.py, scoring.py)
  5. Build graph_network.py (Module 4) — this is a dependency for everything

PHASE 2: Core Engines (Backend Intelligence)
  6. Build anomaly_detector.py (Module 1)
  7. Build piggyback_matcher.py (Module 2)
  8. Build recovery_engine.py (Module 3)
  9. Create all API routes

PHASE 3: Simulation
  10. Build simulation.py engine
  11. Add WebSocket support (Socket.IO)
  12. Test simulation loop with console output

PHASE 4: Frontend
  13. Set up Vite + React project
  14. Implement design system (index.css)
  15. Build Dashboard page with KPI cards
  16. Integrate Leaflet map with live markers
  17. Build Alert Panel and Recovery Modal
  18. Build Analytics page with charts
  19. Add WebSocket client for real-time updates

PHASE 5: Polish
  20. Add animations (marker movements, route drawing)
  21. Add sound/notification effects for alerts
  22. Full end-to-end demo test
  23. Create README with setup instructions
```

---

## 📌 CRITICAL REQUIREMENTS FOR HACKATHON JUDGES

1. **Working Demo** — The simulation must run end-to-end: shipment gets misplaced → detected → matched → recovered
2. **Visual Impact** — The map must show animated vehicle movements and recovery route drawing in real-time
3. **Algorithm Transparency** — Show the scoring breakdown for each recovery strategy (judges love math)
4. **Cost Savings** — Display clear metrics showing how piggybacking saves money vs. traditional recovery
5. **Novelty** — Emphasize that NO competitor offers this exact combination of detection + piggybacking
6. **Indian Context** — Use Indian cities, Indian pricing (₹), and Indian logistics corridors for relatability

---

## 🏷️ NAMING

- **App Name:** PiggyShip
- **Tagline:** "Don't lose shipments. Rescue them."
- **Logo Concept:** A package icon with a small truck "carrying" it piggyback-style
- **Color Theme:** Dark navy (#0a0e1a) with indigo (#6366f1) and green (#10b981) accents

---

*This plan is self-contained. Any LLM with coding capability can use this document to build the complete application from scratch.*
