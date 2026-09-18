"""Vehicle progress along planned routes, shared by DEMO SIMULATION and LIVE GPS.

Called for every accepted location update. Detects hub arrival/departure,
scans shipments aboard, delivers them, and moves recovery shipments between
hub and vehicle following the legs saved on their RecoveryAction. Every
physical load/unload/hub scan writes a ScanEvent (Module 1's evidence), and a
vehicle reaching a hub without a parcel manifested to arrive there raises a 'short'.
Returns socket events as (event, payload, shipment_id, vehicle_id) tuples.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import Hub, RecoveryAction, ScanEvent, Shipment, Vehicle
from engines.anomaly_detector import ACTIVE_STATUSES, expected_segment
from utils import clock, roads
from utils.geo import haversine

ARRIVAL_RADIUS_KM = 2.0  # ASSUMPTION: within this distance of the next stop = arrived
VEHICLE_RECOVERIES = ("piggyback", "hold")


def record_scan(shipment: Shipment, event_type: str, now: datetime, hub_id: str | None = None,
                vehicle_id: str | None = None, expected: bool = True,
                note: str | None = None) -> ScanEvent:
    """Append a scan event to the shipment (saved with it by the caller's session)."""
    event = ScanEvent(id=f"SCN-{uuid.uuid4().hex[:10]}", shipment_id=shipment.id,
                      event_type=event_type, hub_id=hub_id, vehicle_id=vehicle_id,
                      expected=expected, note=note, scanned_at=now)
    shipment.scans.append(event)
    return event


def short_targets(vehicle_id: str, hub_id: str, manifested) -> list:
    """Shipments manifested on the vehicle, due at this hub, but not aboard: each gets a 'short'.

    At most one short per shipment per hub; shipments in recovery or already flagged are skipped.
    """
    targets = []
    for s in manifested:
        if (s.manifest_vehicle_id != vehicle_id or s.current_vehicle_id == vehicle_id
                or s.status not in ACTIVE_STATUSES or s.recovery_strategy):
            continue
        if expected_segment(s)[1] != hub_id:
            continue
        if any(e.event_type == "short" and e.hub_id == hub_id for e in s.scans):
            continue
        targets.append(s)
    return targets


def active_action(db: Session, shipment_id: str) -> RecoveryAction | None:
    return (db.query(RecoveryAction)
            .filter_by(shipment_id=shipment_id, status="in_progress")
            .order_by(RecoveryAction.created_at.desc()).first())


def _release(vehicle: Vehicle, shipment: Shipment) -> None:
    vehicle.used_capacity_kg = max(0.0, vehicle.used_capacity_kg - shipment.weight_kg)
    vehicle.used_capacity_cbm = max(0.0, vehicle.used_capacity_cbm - shipment.volume_cbm)
    if shipment.id in (vehicle.piggybacked_shipments or []):
        vehicle.piggybacked_shipments = [s for s in vehicle.piggybacked_shipments
                                         if s != shipment.id]


def _place_at_hub(shipment: Shipment, hub: Hub) -> None:
    shipment.current_vehicle_id = None
    shipment.current_hub_id = hub.id
    shipment.current_lat, shipment.current_lng = hub.lat, hub.lng


def complete_recovery(db: Session, shipment: Shipment, action: RecoveryAction, now: datetime):
    hub = db.get(Hub, shipment.destination_hub_id)
    record_scan(shipment, "unload", now, hub.id, shipment.current_vehicle_id,
                note="recovery delivered")
    _place_at_hub(shipment, hub)
    shipment.status = "recovered"
    shipment.manifest_vehicle_id = None
    shipment.actual_route = list(shipment.actual_route or []) + [hub.id]
    shipment.last_scan_at = now
    action.status = "completed"
    action.completed_at = now
    plan = action.recovery_route or {}
    start = datetime.fromisoformat(plan["start_time"]) if plan.get("start_time") else now
    cost_saved = round((plan.get("dedicated_cost") or 0) - (action.additional_cost or 0), 2)
    return ("recovery:completed",
            {"shipment_id": shipment.id, "strategy": action.action_type,
             "cost_saved": cost_saved,
             "time_taken": round((now - start).total_seconds() / 3600, 2)},
            shipment.id, action.matched_vehicle_id)


def _recovery_arrival(db, vehicle, hub, shipment, action, now) -> list:
    legs = (action.recovery_route or {}).get("legs") or []
    idx = next((i for i, leg in enumerate(legs)
                if leg["vehicle_id"] == vehicle.id and leg["to_hub"] == hub.id), None)
    if idx is None:
        return []
    percent = round(100 * (idx + 1) / len(legs), 1)
    if idx == len(legs) - 1 or hub.id == shipment.destination_hub_id:
        _release(vehicle, shipment)
        return [complete_recovery(db, shipment, action, now)]
    shipment.actual_route = list(shipment.actual_route or []) + [hub.id]
    shipment.last_scan_at = now
    if legs[idx + 1]["vehicle_id"] != vehicle.id:
        record_scan(shipment, "unload", now, hub.id, vehicle.id, note="recovery transfer")
        _release(vehicle, shipment)
        _place_at_hub(shipment, hub)
    else:
        record_scan(shipment, "hub_scan", now, hub.id, vehicle.id)
    return [("recovery:progress", {"shipment_id": shipment.id, "percent_complete": percent,
                                   "eta": legs[-1]["arrival_time"], "at_hub": hub.id},
             shipment.id, vehicle.id)]


def _recovery_pickup(db, vehicle, hub, now) -> list:
    events = []
    waiting = db.query(Shipment).filter(Shipment.current_hub_id == hub.id,
                                        Shipment.recovery_strategy.in_(VEHICLE_RECOVERIES),
                                        Shipment.status.in_(("piggybacked", "in_transit")))
    for shipment in waiting:
        action = active_action(db, shipment.id)
        legs = (action.recovery_route or {}).get("legs") if action else None
        if not legs:
            continue
        idx = next((i for i, leg in enumerate(legs)
                    if leg["vehicle_id"] == vehicle.id and leg["from_hub"] == hub.id), None)
        if idx is None:
            continue
        if idx > 0:  # first vehicle's capacity was reserved at execution
            vehicle.used_capacity_kg += shipment.weight_kg
            vehicle.used_capacity_cbm += shipment.volume_cbm
        shipment.current_vehicle_id = vehicle.id
        shipment.current_hub_id = None
        shipment.manifest_vehicle_id = vehicle.id  # the recovery legs are the new manifest
        record_scan(shipment, "load", now, hub.id, vehicle.id, note=f"recovery {action.action_type}")
        shipment.status = "piggybacked" if action.action_type == "piggyback" else "in_transit"
        events.append(("recovery:progress",
                       {"shipment_id": shipment.id, "percent_complete": round(100 * idx / len(legs), 1),
                        "eta": legs[-1]["arrival_time"], "loaded_on": vehicle.id},
                       shipment.id, vehicle.id))
    return events


def _raise_shorts(db: Session, vehicle: Vehicle, hub: Hub, now: datetime) -> None:
    manifested = db.query(Shipment).filter(Shipment.manifest_vehicle_id == vehicle.id,
                                           Shipment.status.in_(ACTIVE_STATUSES),
                                           Shipment.recovery_strategy.is_(None)).all()
    for shipment in short_targets(vehicle.id, hub.id, manifested):
        record_scan(shipment, "short", now, hub.id, vehicle.id, expected=False,
                    note=f"manifested on {vehicle.id} for {hub.id} but not aboard at unload")


def arrive(db: Session, vehicle: Vehicle, hub: Hub, now: datetime) -> list:
    events = []
    vehicle.status = "at_hub"
    vehicle.current_lat, vehicle.current_lng = hub.lat, hub.lng
    for shipment in db.query(Shipment).filter_by(current_vehicle_id=vehicle.id).all():
        action = active_action(db, shipment.id) if shipment.recovery_strategy else None
        if action is not None and action.action_type in VEHICLE_RECOVERIES:
            events += _recovery_arrival(db, vehicle, hub, shipment, action, now)
            continue
        shipment.current_lat, shipment.current_lng = hub.lat, hub.lng
        if shipment.status == "misplaced":
            continue  # stays aboard the wrong vehicle until a recovery is executed
        if hub.id not in (shipment.expected_route or []):
            continue  # a stop off its route (e.g. a detour): the parcel stays aboard, unscanned
        shipment.actual_route = list(shipment.actual_route or []) + [hub.id]
        shipment.last_scan_at = now
        if hub.id == shipment.destination_hub_id:
            record_scan(shipment, "unload", now, hub.id, vehicle.id)
            _release(vehicle, shipment)
            _place_at_hub(shipment, hub)
            shipment.status = "delivered"
            shipment.manifest_vehicle_id = None
        else:
            record_scan(shipment, "hub_scan", now, hub.id, vehicle.id)
    _raise_shorts(db, vehicle, hub, now)
    events += _recovery_pickup(db, vehicle, hub, now)
    return events


def depart(vehicle: Vehicle) -> None:
    vehicle.current_stop_index += 1
    vehicle.status = ("completed" if vehicle.current_stop_index >= len(vehicle.planned_route)
                      else "in_transit")


def on_position(db: Session, vehicle: Vehicle, lat: float, lng: float, now: datetime) -> list:
    """Advance route state for an accepted position. Caller commits."""
    vehicle.current_lat, vehicle.current_lng = lat, lng
    route = vehicle.planned_route or []
    idx = vehicle.current_stop_index or 0
    if vehicle.status == "completed" or idx >= len(route):
        return []
    hub = db.get(Hub, route[idx])
    near = haversine(lat, lng, hub.lat, hub.lng) <= ARRIVAL_RADIUS_KM
    if vehicle.status == "at_hub":
        if near:  # recoveries executed while the vehicle is already dwelling here
            return _recovery_pickup(db, vehicle, hub, now)
        depart(vehicle)
        return []
    return arrive(db, vehicle, hub, now) if near else []


def sync_carried_shipments(db: Session, positions: dict) -> None:
    """Shipments aboard a vehicle take the vehicle's live position."""
    for shipment in db.query(Shipment).filter(Shipment.current_vehicle_id.isnot(None)):
        pos = positions.get(shipment.current_vehicle_id)
        if pos:
            shipment.current_lat, shipment.current_lng = pos


def progress_virtual_recoveries(db: Session, now: datetime) -> list:
    """Reroute/dedicated recoveries move along their hub path by elapsed time."""
    events = []
    actions = (db.query(RecoveryAction)
               .filter(RecoveryAction.status == "in_progress",
                       RecoveryAction.action_type.in_(("reroute", "dedicated"))).all())
    hubs = {h.id: h for h in db.query(Hub).all()}
    for action in actions:
        shipment = db.get(Shipment, action.shipment_id)
        plan = action.recovery_route or {}
        start = datetime.fromisoformat(plan["start_time"])
        end = datetime.fromisoformat(plan["arrival_time"])
        span = max((end - start).total_seconds(), 1.0)
        fraction = max(0.0, min(1.0, (now - start).total_seconds() / span))
        if fraction >= 1.0:
            events.append(complete_recovery(db, shipment, action, now))
            continue
        hub_ids = [h for h in plan.get("hubs", []) if h in hubs]
        if len(hub_ids) >= 2:
            line = roads.hub_polyline(hubs, hub_ids)
            shipment.current_lat, shipment.current_lng = roads.point_along_path(line, fraction)
            shipment.current_hub_id = None
        events.append(("recovery:progress",
                       {"shipment_id": shipment.id, "percent_complete": round(fraction * 100, 1),
                        "eta": plan["arrival_time"]}, shipment.id, None))
    return events


def detach_for_recovery(db: Session, shipment: Shipment, start_hub_id: str) -> None:
    """Bring an off-hub (e.g. wrong-vehicle) shipment to its recovery start hub."""
    carrier = shipment.current_vehicle_id
    if carrier:
        vehicle = db.get(Vehicle, carrier)
        if vehicle is not None:
            _release(vehicle, shipment)
    hub = db.get(Hub, start_hub_id)
    if hub is not None:
        _place_at_hub(shipment, hub)
        record_scan(shipment, "unload" if carrier else "hub_scan", clock.now(), hub.id, carrier,
                    note="brought to recovery start hub")


def _reserved_vehicle_id(shipment: Shipment, action: RecoveryAction | None) -> str | None:
    """Vehicle holding capacity for this shipment: the one carrying it, or the first recovery
    vehicle (reserved at execution) while the shipment waits at that leg's pickup hub."""
    if shipment.current_vehicle_id:
        return shipment.current_vehicle_id
    legs = (action.recovery_route or {}).get("legs") if action else None
    if legs and shipment.current_hub_id == legs[0]["from_hub"]:
        return legs[0]["vehicle_id"]
    return None


def cancel_recovery(db: Session, shipment: Shipment, now: datetime) -> bool:
    """Fail the in-progress recovery (if any) and clear the shipment's recovery fields.

    Frees capacity reserved for a shipment still waiting at its pickup hub; a shipment
    already aboard keeps its space until `end_carriage`. Returns True if one was cancelled.
    """
    action = active_action(db, shipment.id)
    if action is None:
        return False
    if not shipment.current_vehicle_id:
        vid = _reserved_vehicle_id(shipment, action)
        vehicle = db.get(Vehicle, vid) if vid else None
        if vehicle is not None:
            _release(vehicle, shipment)
    action.status = "failed"
    action.completed_at = now
    shipment.recovery_strategy = None
    shipment.recovery_vehicle_id = None
    shipment.recovery_mode = None
    shipment.recovery_score = None
    return True


def end_carriage(db: Session, shipment: Shipment, hub_id: str) -> None:
    """Take the shipment off whatever vehicle carries it and put it at `hub_id`."""
    if shipment.current_vehicle_id:
        vehicle = db.get(Vehicle, shipment.current_vehicle_id)
        if vehicle is not None:
            _release(vehicle, shipment)
    shipment.manifest_vehicle_id = None
    hub = db.get(Hub, hub_id)
    if hub is not None:
        _place_at_hub(shipment, hub)
    else:
        shipment.current_vehicle_id = None
