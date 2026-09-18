# PiggyShip Engines Overview

The intelligence of PiggyShip is split across 7 dedicated backend engines and modules. Together, they create a real-time, self-healing logistics network. Here is a simple explanation of what each engine does.

## 1. Simulation Engine (`simulation.py`, `fleet_progress.py`)
**Role:** The heartbeat of the application.
**How it works:** Because PiggyShip needs to demonstrate real-time tracking and recovery, the Simulation Engine acts as the "clock." It ticks time forward at an accelerated rate, moving vehicles along their geographical routes, simulating GPS coordinate streams, calculating speeds, and even injecting random delays or misplacements to test the system.

## 2. Anomaly Detector (`anomaly_detector.py`)
**Role:** The watchdog.
**How it works:** This engine continuously monitors the state of all shipments and vehicles. It checks if a shipment is physically on the truck it's supposed to be on, or if a truck is running so late that a critical shipment might miss its SLA (Service Level Agreement). When something goes wrong, it immediately flags the shipment as `misplaced` or `delayed` and fires an alert.

## 3. Time-Expanded Graph Network (`graph_network.py`)
**Role:** The spatial-temporal map.
**How it works:** Standard routing algorithms just look at static roads. The Time-Expanded Graph looks at space *and* time. It builds a complex network graph of every hub, every active truck, where they are right now, where they will be in an hour, and exactly how much free cargo space they will have at that exact time. 

## 4. Piggyback Matcher (`piggyback_matcher.py`)
**Role:** The opportunity finder.
**How it works:** When a package is misplaced, this engine searches the Time-Expanded Graph for active vehicles that:
1. Are physically close to the misplaced package.
2. Have enough empty capacity to fit the package.
3. Are already heading toward (or near) the package's destination.
It scores these matches based on how little of a detour the truck would have to make.

## 5. Recovery Engine (`.py`)
**Role:** The strategist.
**How it works:** Piggybacking isn't always the right answer. The Recovery Engine takes the candidates from the Piggyback Matcher and pits them against other traditional strategies, such as:
- **Holding:** Leaving the package at the hub for the next scheduled truck.
- **Dedicated Dispatc
h:** Sending an expensive, brand-new truck just for this package.
- **Hub Transfer:** Rerouting the package through a different sorting facility.
It calculates the absolute cost, SLA adherence, and fuel efficiency of every single option and ranks them.

## 6. LLM Decision Agent (`decision_agent.py`)
**Role:** The final judge.
**How it works:** While algorithms are great at math, they lack human context. The Decision Agent takes the top-ranked mathematical strategies from the Recovery Engine and feeds them into an AI (Large Language Model). The LLM evaluates the options against "soft constraints" (e.g., weather conditions, road types, client priority, VIP status) to make a final, human-like executive decision on how to recover the package.

## 7. Real-Time Layer (`realtime/`)
**Role:** The communicator.
**How it works:** This is the `Socket.IO` websocket server. Instead of the frontend constantly asking the backend "did anything change?", the Real-Time Layer pushes updates instantly. It streams live truck GPS coordinates, simulation clock ticks, new alerts, and the LLM's final recommendations straight to your Dashboard.
