"""MODULE 1: Misplaced shipment detection from scan events.

A parcel has no GPS, so the only evidence is its scan trail (`scan_events`,
`actual_route`, `last_scan_at`) and its manifest. The parcel's position and
`current_vehicle_id` are simulator ground truth and are never read here.
Checks run in order; the first failing one sets the misplacement type:
    excess at hub                    -> 'wrong_hub'
    manifest mismatch at loading     -> 'wrong_vehicle'
    short at unload                  -> 'stuck'
    time anomaly / scan gap          -> 'stuck'
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import config
from utils import clock, roads
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


def expected_segment(shipment):
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


def remaining_route(vehicle) -> list:
    if vehicle.status == "completed":
        return []
    return list((vehicle.planned_route or [])[vehicle.current_stop_index or 0:])


def vehicle_serves(vehicle, hub_id: str | None) -> bool:
    """The loading check: does the vehicle's remaining route still reach `hub_id`?"""
    return hub_id is not None and hub_id in remaining_route(vehicle)


def _scans(shipment) -> list:
    return sorted(getattr(shipment, "scans", None) or [], key=lambda e: e.scanned_at)


def last_custody_scan(shipment):
    """Latest scan of the parcel itself (a 'short' records its absence, not its custody)."""
    return next((e for e in reversed(_scans(shipment)) if e.event_type != "short"), None)


def on_vehicle_by_scans(shipment) -> bool:
    """True if the scan trail says the parcel is aboard a vehicle (loaded, not since unloaded)."""
    last = last_custody_scan(shipment)
    return last is not None and last.vehicle_id is not None and last.event_type != "unload"


def check_route_deviation(shipment) -> str | None:
    """Hub id if the parcel was last scanned at a hub off its expected route (excess)."""
    scans = shipment.actual_route or []
    if scans and scans[-1] not in set(shipment.expected_route or []):
        return scans[-1]
    return None


def check_manifest_mismatch(shipment, next_hub_id, vehicles: dict | None = None):
    """The latest custody scan is a load onto a vehicle that no longer reaches the next hub.

    With `vehicles` the loaded vehicle's current remaining route decides; without it (or
    for an unknown vehicle) the loading scanner's own verdict (`expected`) is used.
    Returns the load ScanEvent, or None.
    """
    last = last_custody_scan(shipment)
    if last is None or last.event_type != "load" or last.vehicle_id is None:
        return None
    vehicle = (vehicles or {}).get(last.vehicle_id)
    if vehicle is not None:
        return None if vehicle_serves(vehicle, next_hub_id) else last
    return None if last.expected else last


def check_short(shipment):
    """The 'short' raised since the parcel was last scanned, or None."""
    scans = _scans(shipment)
    return scans[-1] if scans and scans[-1].event_type == "short" else None


def check_time_anomaly(shipment, expected_hub, previous_hub=None, now=None) -> bool:
    """True if time since the last scan exceeds expected leg time × TIME_TOLERANCE."""
    now = now or clock.now()
    if shipment.last_scan_at is None or expected_hub is None or previous_hub is None:
        return False
    if previous_hub.id == expected_hub.id:
        return False
    km = roads.hub_km(previous_hub, expected_hub)
    expected_hours = km / config.AVG_TRANSIT_SPEED_KMH
    actual_hours = (now - shipment.last_scan_at).total_seconds() / 3600
    return actual_hours > expected_hours * config.TIME_TOLERANCE


def check_scan_gap(shipment, now=None) -> bool:
    """True if a parcel that its scans place at a hub (not aboard) has had no scan for too long.

    Parcels riding a vehicle are only scanned at hubs, and national legs can
    exceed MAX_SCAN_GAP_HOURS; for them the time-anomaly check applies instead.
    """
    now = now or clock.now()
    if shipment.last_scan_at is None or on_vehicle_by_scans(shipment):
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


def detect_shipment(shipment, hubs: dict, now=None,
                    vehicles: dict | None = None) -> AnomalyResult | None:
    """`vehicles` (id -> Vehicle) lets the manifest check use each vehicle's live remaining route."""
    now = now or clock.now()
    prev_id, next_id = expected_segment(shipment)
    prev_hub, next_hub = hubs.get(prev_id), hubs.get(next_id)
    last_hub = (shipment.actual_route or ["unknown"])[-1]
    kind, reason = None, ""
    if (hub_id := check_route_deviation(shipment)) is not None:
        kind = "wrong_hub"
        reason = (f"Excess at hub: scanned at {hub_id}, which is not on expected route "
                  f"{shipment.expected_route}")
    elif (load := check_manifest_mismatch(shipment, next_id, vehicles)) is not None:
        kind = "wrong_vehicle"
        where = f" at {load.hub_id}" if load.hub_id else ""
        reason = (f"Manifest mismatch at loading: scanned onto {load.vehicle_id}{where}, "
                  f"which does not go to next hub {next_id} "
                  f"(manifested on {shipment.manifest_vehicle_id or 'no vehicle'})")
    elif (short := check_short(shipment)) is not None:
        kind = "stuck"
        reason = (f"Short at unload: not aboard {short.vehicle_id} when it reached "
                  f"{short.hub_id}; last scanned at {last_hub}")
    elif check_time_anomaly(shipment, next_hub, prev_hub, now):
        kind = "stuck"
        reason = (f"Time anomaly: no scan on leg {prev_id} → {next_id} for over "
                  f"{config.TIME_TOLERANCE}× its expected time")
    elif check_scan_gap(shipment, now):
        kind = "stuck"
        reason = (f"Scan gap: no scan for more than {config.MAX_SCAN_GAP_HOURS:.0f} h "
                  f"(last scanned at {last_hub})")
    if kind is None:
        return None
    hours_left = (shipment.deadline - now).total_seconds() / 3600
    score = calculate_severity(shipment.priority, hours_left, kind)
    return AnomalyResult(shipment.id, kind, reason, score, severity_label(score), now)


def detect_anomalies(shipments, hubs: dict, now=None,
                     vehicles: dict | None = None) -> list[AnomalyResult]:
    """Scan active shipments and return flagged anomalies, most severe first."""
    results = [r for s in shipments if s.status in ACTIVE_STATUSES
               if (r := detect_shipment(s, hubs, now, vehicles)) is not None]
    return sorted(results, key=lambda r: r.severity_score, reverse=True)
