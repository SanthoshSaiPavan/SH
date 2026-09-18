"""Configuration and tunable constants.

Every threshold the plan names (geofence radius, time tolerance, score
thresholds, ...) lives here so engines never hard-code magic numbers.
Values marked ASSUMPTION are not given by the implementation plan and were
chosen as reasonable demo defaults; tune them here.
"""
import os

# --- Infrastructure -------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://piggyship:piggyship@localhost:5432/piggyship"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

# --- Auth -----------------------------------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
ROLES = ("ADMIN", "LOGISTICS_OPERATOR", "DRIVER")

# --- LLM decision agent (Module 6) ----------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

# --- Module 1: anomaly detection ------------------------------------------
GEOFENCE_THRESHOLD_KM = 50.0
TIME_TOLERANCE = 1.5
MAX_SCAN_GAP_HOURS = 6.0
AVG_TRANSIT_SPEED_KMH = 50.0  # ASSUMPTION: used for expected hub-to-hub transit time

# --- Geography / costing ----------------------------------------------------
ROAD_DISTANCE_FACTOR = 1.3  # ASSUMPTION: road km ≈ great-circle km × factor
DEDICATED_COST_PER_KM = 18.0  # ASSUMPTION: ₹/km for a dedicated recovery vehicle
DEDICATED_SPEED_KMH = 60.0  # ASSUMPTION
DEDICATED_DISPATCH_HOURS = 1.0  # ASSUMPTION: time to arrange a dedicated vehicle
REROUTE_RATE_FACTOR = 0.4  # ASSUMPTION: carrier part-load rate as fraction of route ₹/km
REROUTE_BOOKING_HOURS = 2.0  # ASSUMPTION: wait for next carrier service on reroute
HOLDING_COST_PER_HOUR = 15.0  # ASSUMPTION: ₹/hour to hold a shipment at a hub
HANDLING_COST_PER_TRANSFER = 100.0  # ASSUMPTION: ₹ per load/unload transfer
LOCAL_PICKUP_COST_PER_KM = 12.0  # ASSUMPTION: ₹/km to bring an off-hub shipment to nearest hub
LOCAL_PICKUP_SPEED_KMH = 40.0  # ASSUMPTION

# --- Module 4: time-expanded graph ------------------------------------------
HANDLING_BUFFER_MINUTES = 30  # ASSUMPTION: must be at hub this long before a leg departs
HUB_DWELL_MINUTES = 30  # ASSUMPTION: vehicle stop duration at each hub
GRAPH_HORIZON_HOURS = 72  # ASSUMPTION: ignore legs departing further out than this
MAX_DETOUR_KM = 40.0  # ASSUMPTION: vehicles may detour to an off-route hub this close to a leg
# Medium-tier weighted objective converts time to ₹ so cost and time share a unit.
VALUE_OF_TIME_PER_HOUR = 150.0  # ASSUMPTION

# --- Module 2: piggyback matching -------------------------------------------
MAX_FIRST_HOP_WAIT_HOURS = 12.0  # ASSUMPTION: proximity score hits 0 at this wait
CRITICAL_MAX_WAIT_HOURS = 0.5  # ASSUMPTION: "near-instant match" for 🔴 critical
MAX_PIGGYBACK_CANDIDATES = 5
PIGGYBACK_WEIGHTS = {
    "proximity": 0.25,
    "capacity": 0.20,
    "deadline": 0.20,
    "overlap": 0.20,
    "cost": 0.15,
}

# --- Priority tiers ---------------------------------------------------------
PRIORITY_MULTIPLIER = {"critical": 2.0, "high": 1.5, "medium": 1.0, "low": 0.5}
PRIORITY_OBJECTIVE = {
    "critical": "fastest",
    "high": "fastest",  # cost used as tiebreaker
    "medium": "weighted",
    "low": "cheapest",  # time used as tiebreaker
}
# Module 3 strategy weights per tier. The plan's single formula added
# `0.20 * priority_multiplier`, which cannot change ranking; per the user's
# decision the tier instead shifts the weights (Critical: time ~0.6, cost ~0.1).
STRATEGY_WEIGHTS = {
    "critical": {"cost": 0.10, "time": 0.60, "capacity": 0.15, "reliability": 0.15},
    "high": {"cost": 0.20, "time": 0.45, "capacity": 0.20, "reliability": 0.15},
    "medium": {"cost": 0.30, "time": 0.30, "capacity": 0.20, "reliability": 0.20},
    "low": {"cost": 0.45, "time": 0.15, "capacity": 0.20, "reliability": 0.20},
}
# Cost score = 1 - cost / (COST_CEILING_FACTOR × dedicated cost).
COST_CEILING_FACTOR = 2.0  # ASSUMPTION
CAPACITY_EFFICIENCY = {  # ASSUMPTION: how much each strategy reuses existing capacity
    "piggyback": 1.0,
    "hold": 0.9,
    "reroute": 0.6,
    "dedicated": 0.1,
}
DEFAULT_RELIABILITY = {  # ASSUMPTION: prior until recovery_actions history exists
    "piggyback": 0.85,
    "reroute": 0.80,
    "dedicated": 0.95,
    "hold": 0.75,
}
RELIABILITY_PRIOR_WEIGHT = 10  # pseudo-observations blending prior with history

# --- Module 3: autonomy thresholds -------------------------------------------
AUTO_EXECUTE_THRESHOLD = 85.0
LOW_CONFIDENCE_THRESHOLD = 50.0

# --- Module 5: simulation -----------------------------------------------------
SIM_TICK_SECONDS = 2.0
SIM_MINUTES_PER_TICK = 2.0  # ASSUMPTION: at 1x, each 2 s tick advances the sim clock 2 min
SIM_SPEEDS = (1, 2, 5, 10)
SIM_MISPLACE_EVERY_N_TICKS = 30  # ASSUMPTION
SIM_MISPLACE_PROBS = {"wrong_hub": 0.30, "wrong_vehicle": 0.40, "stuck": 0.30}
# Continuous shipment generation (DEMO only): every N ticks, while fewer than the target are
# in transit, load one new shipment onto each vehicle stopped at a hub (up to the shortfall).
SIM_NEW_SHIPMENT_EVERY_N_TICKS = 1  # ASSUMPTION
SIM_TARGET_ACTIVE_SHIPMENTS = 30  # ASSUMPTION: matches the seeded 30 shipments

# --- Module 7: real-time layer -----------------------------------------------
STALE_AFTER_SECONDS = 10
OFFLINE_AFTER_SECONDS = 30
STATUS_CHECK_INTERVAL_SECONDS = 3
MAX_PLAUSIBLE_SPEED_KMH = 150.0
# ASSUMPTION: testing-only exception — the one user (JWT sub) allowed to send out-of-order timestamps
STALE_TIMESTAMP_EXEMPT_USER = "driver101"
INDIA_BOUNDS = {"min_lat": 6.0, "max_lat": 37.5, "min_lng": 68.0, "max_lng": 97.5}
LOCATION_FLUSH_SECONDS = 5
RECOMPUTE_INTERVAL_SECONDS = 5
RELEVANCE_RADIUS_KM = 100.0  # ASSUMPTION
SWITCH_MARGIN = 5.0
DEFAULT_FLEET_ID = "FLEET-MAIN"
