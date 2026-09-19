# PiggyShip System Architecture

If the jury asks about the technical architecture of your platform, you can use this document as your guide. It outlines the end-to-end data flow from live tracking to the final recovery recommendation.

## Architecture Diagram

```mermaid
flowchart TD
    %% Define Styles
    classDef frontend fill:#3b82f6,stroke:#1e3a8a,stroke-width:2px,color:#fff
    classDef backend fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff
    classDef database fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff
    classDef output fill:#8b5cf6,stroke:#4c1d95,stroke-width:2px,color:#fff
    
    subgraph External["External Data Sources"]
        GPS["Live GPS Streams (Trucks)"]
        TMS["Transport Mgmt System (Shipments)"]
    end
    
    subgraph DataLayer["Data Layer"]
        Redis[("Redis\n(Live State & Pub/Sub)")]:::database
        Postgres[("PostgreSQL\n(Hubs, Routes, History)")]:::database
    end
    
    subgraph Engines["Backend Engines (FastAPI / Python)"]
        RT["Real-Time Ingestion (Sockets)"]:::backend
        Anomaly["Anomaly Detector"]:::backend
        Fleet["Fleet Progress"]:::backend
        GraphBuilder["Graph Builder Engine\n(networkx)"]:::backend
        Recovery["Recovery Engine\n(Dijkstra/A*)"]:::backend
        Piggyback["Piggyback Matcher"]:::backend
        Decision["Decision Agent"]:::backend
    end
    
    subgraph Presentation["Frontend (React / Vite)"]
        Map["2D Map View\n(MapLibre)"]:::frontend
        Graph3D["3D Control Tower\n(Three.js)"]:::frontend
        Dash["Analytics Dashboard"]:::frontend
    end
    
    subgraph Output["Final Output"]
        Action["Actionable Recovery Plan\n(Piggyback / Detour)"]:::output
    end

    %% Connections
    GPS --> RT
    TMS --> Postgres
    
    RT --> Redis
    RT --> Anomaly
    RT --> Fleet
    
    Postgres --> GraphBuilder
    Redis --> GraphBuilder
    
    Anomaly --> Recovery
    GraphBuilder -->|"Builds Time-Expanded Graph"| Recovery
    
    Fleet --> Piggyback
    Recovery --> Decision
    Piggyback --> Decision
    
    Decision -->|"Calculates best path"| Action
    
    Decision -.->|"Serializes graph state"| Graph3D
    RT -.->|"Live positions"| Map
    Postgres -.->|"Metrics"| Dash
```

---

## Component Breakdown

### 1. External Data Sources
* **Live GPS Streams:** Continuous telemetry data from active trucks on the road (location, speed, heading).
* **Transport Management System (TMS):** The source of truth for static data like planned shipment routes, hub locations, and truck capacities.

### 2. Data Layer
* **Redis:** Acts as an ultra-fast, in-memory cache for Live GPS positions. It allows the system to process thousands of telemetry pings per second without crashing.
* **PostgreSQL:** Stores persistent relational data like historical shipments, physical hub coordinates, and exact road distance matrices.

### 3. Backend Engines (The Core Intelligence)
The backend is split into **6 specialized engines** working together:
1. **Anomaly Detector (`anomaly_detector.py`):** Continuously monitors the live GPS feed against planned routes to detect misplaced or delayed shipments.
2. **Fleet Progress (`fleet_progress.py`):** Tracks the live progress of all vehicles, calculating their exact locations and ETAs along their routes.
3. **Graph Builder Engine (`graph_network.py`):** Pulls static hubs from Postgres and live truck positions from Redis to dynamically generate the **Time-Expanded (Spatial-Temporal) Graph**.
4. **Recovery Engine (`recovery_engine.py`):** When an anomaly is detected, this engine injects an `entry` node into the graph and runs shortest-path algorithms to find optimal recovery paths.
5. **Piggyback Matcher (`piggyback_matcher.py`):** Evaluates if a misplaced package can be hitched onto an already moving, partially empty truck (Piggybacking).
6. **Decision Agent (`decision_agent.py`):** The final orchestrator that compares standard recovery options vs Piggybacking, weighs the costs/deadlines, and makes the final autonomous decision.

*Note: The real-time ingestion connects via WebSockets/Socket.io to continuously push these decisions to the frontend.*

### 4. Frontend & Final Output
* **2D Map View:** Powered by MapLibre for standard geographic tracking.
* **3D Control Tower:** Powered by Three.js. This takes the massive, complex mathematical graph from the backend and renders it as an interactive 3D visualizer so human operators can explicitly see the "Why" behind the AI's routing decisions.
* **Actionable Output:** The final product is a specific, actionable command (e.g., "Put Shipment 501 on Truck 104 with a 5km detour to Warangal").
