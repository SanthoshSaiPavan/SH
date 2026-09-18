"""MODULE 1: Misplaced shipment detection.

Checks run in the plan's order; the first failing check determines the
misplacement type:
    route deviation -> 'wrong_hub'
    geofence        -> 'wrong_vehicle'
    time anomaly    -> 'stuck'
    scan gap        -> 'stuck'
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import config
from utils import clock
from utils.geo import haversine, point_to_line_distance
from utils.scoring import clamp01

ACTIVE_STATUSES = ("in_transit", "delayed")
PRIORITY_SEVERITY = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
TYPE_SEVERITY = {"wrong_vehicle": 1.0, "wrong_hub": 0.8, "stuck": 0.6}


@dataclass
class AnomalyResult:
    shipment_id: str
    misplacement_type: str
    reason: str
    severity_score: float
    severity: str
    detected_at: datetime

    def to_dict(self) -> dict:
        data = asdict(self)
        data["detected_at"] = self.detected_at.isoformat()
        return data


def _expected_segment(shipment):
    """(previous expected hub id, next expected hub id) given scans so far."""
    expected = shipment.expected_route or []
    scanned = [h for h in (shipment.actual_route or []) if h in expected]
    if not expected:
        return None, None
    if not scanned:
        return None, expected[0]
    pos = expected.index(scanned[-1])
    nxt = expected[pos + 1] if pos + 1 < len(expected) else expected[pos]
    return expected[pos], nxt


def check_route_deviation(shipment) -> str | None:
    """'wrong_hub' if the shipment is at (or was last scanned at) a hub off its expected route."""
    expected = set(shipment.expected_route or [])
    if shipment.current_hub_id and shipment.current_hub_id not in expected:
        return "wrong_hub"
    scans = shipment.actual_route or []
    if scans and scans[-1] not in expected:
        return "wrong_hub"
    return None


def check_geofence(shipment, expected_hub, previous_hub=None) -> bool:
    """True if the shipment is further than GEOFENCE_THRESHOLD_KM from its expected path."""
    if shipment.current_lat is None or shipment.current_lng is None or expected_hub is None:
        return False
    point = (shipment.current_lat, shipment.current_lng)
    if previous_hub is not None:
        distance = point_to_line_distance(point, (previous_hub.lat, previous_hub.lng),
                                          (expected_hub.lat, expected_hub.lng))
    else:
        distance = haversine(*point, expected_hub.lat, expected_hub.lng)
    return distance > config.GEOFENCE_THRESHOLD_KM


def check_time_anomaly(shipment, expected_hub, previous_hub=None, now=None) -> bool:
    """True if time since the last scan exceeds expected leg time × TIME_TOLERANCE."""
    now = now or clock.now()
    if shipment.last_scan_at is None or expected_hub is None or previous_hub is None:
        return False
    if previous_hub.id == expected_hub.id:
        return False
    km = haversine(previous_hub.lat, previous_hub.lng, expected_hub.lat, expected_hub.lng) \
        * config.ROAD_DISTANCE_FACTOR
    expected_hours = km / config.AVG_TRANSIT_SPEED_KMH
    actual_hours = (now - shipment.last_scan_at).total_seconds() / 3600
    return actual_hours > expected_hours * config.TIME_TOLERANCE


def check_scan_gap(shipment, now=None) -> bool:
    """True if a shipment that is NOT aboard a tracked vehicle has had no scan for too long.

    Shipments riding a vehicle are only scanned at hubs, and national legs can
    exceed MAX_SCAN_GAP_HOURS; for them the time-anomaly check applies instead.
    """
    now = now or clock.now()
    if shipment.last_scan_at is None or shipment.current_vehicle_id is not None:
        return False
    return (now - shipment.last_scan_at).total_seconds() / 3600 > config.MAX_SCAN_GAP_HOURS


def severity_label(score: float) -> str:
    if score > 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def calculate_severity(priority: str, hours_to_deadline: float, misplacement_type: str) -> float:
    """Severity 0-100: 45% priority, 35% deadline proximity, 20% misplacement type.

    Deadline proximity is 1.0 at/after the deadline and 0 at 48 h or more out.
    ASSUMPTION: the plan names the three factors but not their weights.
    """
    deadline_factor = 1.0 - clamp01(hours_to_deadline / 48.0)
    score = (0.45 * PRIORITY_SEVERITY.get(priority, 0.5)
             + 0.35 * deadline_factor
             + 0.20 * TYPE_SEVERITY.get(misplacement_type, 0.6))
    return round(score * 100, 1)


def detect_shipment(shipment, hubs: dict, now=None) -> AnomalyResult | None:
    now = now or clock.now()
    prev_id, next_id = _expected_segment(shipment)
    prev_hub, next_hub = hubs.get(prev_id), hubs.get(next_id)
    kind, reason = None, ""
    if (kind := check_route_deviation(shipment)) is not None:
        where = shipment.current_hub_id or (shipment.actual_route or ["?"])[-1]
        reason = f"At {where}, which is not on expected route {shipment.expected_route}"
    elif shipment.current_hub_id is None and check_geofence(shipment, next_hub, prev_hub):
        kind = "wrong_vehicle"
        reason = (f"Position is more than {config.GEOFENCE_THRESHOLD_KM:.0f} km off the "
                  f"expected path {prev_id} → {next_id}")
    elif check_time_anomaly(shipment, next_hub, prev_hub, now):
        kind = "stuck"
        reason = f"Leg {prev_id} → {next_id} is taking over {config.TIME_TOLERANCE}× expected time"
    elif check_scan_gap(shipment, now):
        kind = "stuck"
        reason = f"No scan for more than {config.MAX_SCAN_GAP_HOURS:.0f} h"
    if kind is None:
        return None
    hours_left = (shipment.deadline - now).total_seconds() / 3600
    score = calculate_severity(shipment.priority, hours_left, kind)
    return AnomalyResult(shipment.id, kind, reason, score, severity_label(score), now)


def detect_anomalies(shipments, hubs: dict, now=None) -> list[AnomalyResult]:
    """Scan active shipments and return flagged anomalies, most severe first."""
    results = [r for s in shipments if s.status in ACTIVE_STATUSES
               if (r := detect_shipment(s, hubs, now)) is not None]
    return sorted(results, key=lambda r: r.severity_score, reverse=True)
