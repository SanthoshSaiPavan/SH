# PiggyShip Engines Overview (In-Depth Architecture)

The intelligence of PiggyShip is split across 7 dedicated backend engines. Together, they create a real-time, self-healing logistics network. Here is a technical deep-dive into the architecture, algorithms, and data models of each engine.

## 1. Simulation Engine (`simulation.py`, `fleet_progress.py`)
**Role:** The continuous event loop and geospatial state manager.
**How it works:**
- **State Mutation:** It maintains the active state of all `Vehicle` and `Shipment` entities in memory and syncs them to the SQLite database.
- **Geospatial Ticking:** During every "tick", the engine uses the **Haversine formula** (`road_km = haversine(lat, lng) * FACTOR`) to calculate exact coordinate progression along a vehicle's scheduled route based on its `speed_kmh`. 
- **Event Injection:** It programmatically injects variance into the system, such as forced delays or moving a shipment onto a misaligned truck, to test the recovery subsystems.

## 2. Anomaly Detector (`anomaly_detector.py`)
**Role:** The autonomous rule-engine and watchdog.
**How it works:**
- It listens to the stream of simulated GPS coordinates and compares them against a shipment's `expected_route`.
- If a shipment's tracking ping reports it at a hub or on a truck that is not in its `expected_route`, it immediately mutates the shipment state to `misplaced`.
- It tracks time-to-delivery against the strict `deadline` datetime. If the projected arrival time (based on remaining distance and speed) exceeds the SLA, it generates a `delayed` alert.

## 3. Time-Expanded Graph Network (`graph_network.py`)
**Role:** The core routing brain using Spatial-Temporal Networks.
**How it works:**
- Standard routing (like Google Maps) uses static graphs. PiggyShip builds a **NetworkX Directed Graph (`nx.DiGraph`)** where nodes are separated by both location *and* time. 
- **Nodes:** A node is not just "Hub A". A node is a tuple: `("hub", hub_id, time)` or `("dep", vehicle_id, stop_idx)`. 
- **Edges:** Edges represent actions: `leg` (driving), `board` (loading onto a truck), `unload`, and `wait` (holding at a hub).
- **Dynamic Weights:** Edge costs are calculated dynamically at query time using a `_weight_fn`. Depending on the shipment's priority (`fastest`, `cheapest`, or `weighted`), the weight merges literal `₹ cost` with `hours * VALUE_OF_TIME_PER_HOUR`.

## 4. Piggyback Matcher (`piggyback_matcher.py`)
**Role:** The constrained path-finding and scoring algorithm.
**How it works:**
- **Hard Constraints:** It first creates a Subgraph by applying strict filters: dropping edges where the truck lacks `available_capacity_kg/cbm` or where Hazmat handling flags conflict (`edge_allowed_by_handling`). Oversized shipments are instantly rejected.
- **Path Search:** It runs **Dijkstra's Algorithm** (`nx.single_source_dijkstra`) from a synthetic "entry node" to the destination hub, evaluating every possible truck boarding combination.
- **Composite Scoring:** Candidates are scored mathematically (0.0 to 1.0) using a weighted function (`composite_score`) of 5 dimensions:
  1. `proximity`: How fast the package can board.
  2. `capacity`: Utilization efficiency of the truck's free space.
  3. `deadline`: How close it cuts to the SLA.
  4. `overlap`: How much of the recovery path matches the original plan.
  5. `cost_savings`: Cost reduction versus dispatching a dedicated vehicle (`DEDICATED_COST_PER_KM`).

## 5. Recovery Engine (`recovery_engine.py`)
**Role:** The strategy evaluator and comparative optimizer.
**How it works:**
- Piggybacking isn't always the mathematical optimum. The Recovery Engine runs an evaluation array pitting the top Piggyback candidates against classical strategies:
  - **Holding:** Wait at the hub for the next natively scheduled truck.
  - **Dedicated Dispatch:** A strict `distance * DEDICATED_COST` calculation.
  - **Hub Transfer (Reroute):** Calculates off-route hub detours using point-to-line distance geometry (`point_to_line_distance(hub, A, B) <= MAX_DETOUR_KM`).
- It ranks the strategies, applying buffer penalties and handling costs (`HANDLING_COST_PER_TRANSFER`) to ensure the chosen strategy is strictly dominant in overall utility.

## 6. LLM Decision Agent (`decision_agent.py`)
**Role:** The semantic reasoning layer.
**How it works:**
- It bridges deterministic algorithms with non-deterministic "soft constraints".
- It serializes the top-ranked strategies from the Recovery Engine into a strict JSON payload and constructs a prompt including dynamic context (e.g., weather conditions, road types, driver HOS limits, and client VIP status).
- The Large Language Model evaluates the trade-offs that algorithms miss (e.g., "Strategy A is 100 Rs cheaper, but it routes through a hub experiencing a thunderstorm; routing via Strategy B is safer for this fragile VIP package").
- It outputs a structured JSON decision which is intercepted by the backend and broadcasted to the UI.

## 7. Real-Time Layer (`realtime/`)
**Role:** The asynchronous communication bus.
**How it works:**
- Built on `FastAPI` and `python-socketio`, it maintains an active WebSocket pool.
- It bypasses REST polling overhead by emitting `diff` updates (e.g., `truck_moved`, `alert_generated`, `recovery_found`) directly into the React frontend's Redux/State store (`useLiveData` hook).
- This guarantees a sub-100ms latency between an anomaly occurring in the Python simulation and the red banner rendering on the operations dashboard.
