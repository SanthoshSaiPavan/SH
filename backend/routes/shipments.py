"""Shipment CRUD and status endpoints."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Hub, ScanEvent, Shipment
from engines import fleet_progress
from realtime import auth
from realtime.recommendation_loop import recommendation_loop
from routes.serializers import scan_dict, shipment_dict
from utils import clock

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


class ShipmentCreate(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9\-]{3,40}$")
    tracking_number: str = Field(min_length=3, max_length=40)
    origin_hub_id: str
    destination_hub_id: str
    expected_route: list[str] = Field(min_length=2)
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    handling_flags: list[str] = []
    weight_kg: float = Field(gt=0, le=50000)
    volume_cbm: float = Field(gt=0, le=200)
    deadline: datetime

    @field_validator("expected_route")
    @classmethod
    def route_ends(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("expected_route must not repeat hubs")
        return v


class StatusUpdate(BaseModel):
    status: Literal["at_origin", "in_transit", "misplaced", "piggybacked", "recovered",
                    "delivered", "delayed"]


@router.get("")
def list_shipments(status: str | None = None, priority: str | None = None,
                   hub_id: str | None = None, q: str | None = None,
                   db: Session = Depends(get_db), _=Depends(auth.require_any)):
    query = db.query(Shipment)
    if status:
        query = query.filter(Shipment.status.in_(status.split(",")))
    if priority:
        query = query.filter(Shipment.priority.in_(priority.split(",")))
    if hub_id:
        query = query.filter((Shipment.current_hub_id == hub_id)
                             | (Shipment.origin_hub_id == hub_id)
                             | (Shipment.destination_hub_id == hub_id))
    if q:
        query = query.filter(Shipment.id.ilike(f"%{q}%") | Shipment.tracking_number.ilike(f"%{q}%"))
    return [shipment_dict(s) for s in query.order_by(Shipment.id)]


@router.get("/misplaced")
def misplaced(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    return [shipment_dict(s) for s in db.query(Shipment).filter_by(status="misplaced")]


@router.get("/{shipment_id}")
def get_shipment(shipment_id: str, db: Session = Depends(get_db), _=Depends(auth.require_any)):
    s = db.get(Shipment, shipment_id)
    if s is None:
        raise HTTPException(404, "Shipment not found")
    return shipment_dict(s)


@router.get("/{shipment_id}/scans")
def get_scans(shipment_id: str, db: Session = Depends(get_db), _=Depends(auth.require_any)):
    """The shipment's scan events (Module 1's evidence), newest first."""
    if db.get(Shipment, shipment_id) is None:
        raise HTTPException(404, "Shipment not found")
    events = (db.query(ScanEvent).filter_by(shipment_id=shipment_id)
              .order_by(ScanEvent.scanned_at.desc()))
    return [scan_dict(e) for e in events]


@router.post("", status_code=201)
def create_shipment(body: ShipmentCreate, db: Session = Depends(get_db),
                    _=Depends(auth.require_operator)):
    if db.get(Shipment, body.id) is not None:
        raise HTTPException(409, "Shipment id exists")
    hubs = {h.id: h for h in db.query(Hub).all()}
    unknown = [h for h in body.expected_route if h not in hubs]
    if unknown or body.expected_route[0] != body.origin_hub_id \
            or body.expected_route[-1] != body.destination_hub_id:
        raise HTTPException(422, "expected_route must use known hubs from origin to destination")
    origin = hubs[body.origin_hub_id]
    s = Shipment(**body.model_dump(), current_hub_id=origin.id, actual_route=[origin.id],
                 status="at_origin", current_lat=origin.lat, current_lng=origin.lng,
                 last_scan_at=clock.now())
    db.add(s)
    db.commit()
    return shipment_dict(s)


# Statuses that take the shipment out of carriage, and the hub it is then at.
END_CARRIAGE_HUB = {"delivered": "destination_hub_id", "recovered": "destination_hub_id",
                    "at_origin": "origin_hub_id"}


@router.patch("/{shipment_id}/status")
def update_status(shipment_id: str, body: StatusUpdate, db: Session = Depends(get_db),
                  _=Depends(auth.require_operator)):
    """Operator override of a shipment's status, keeping vehicle and recovery state consistent.

    delivered / recovered / at_origin: any in-progress recovery is failed and its fields
      cleared (capacity reserved at its pickup hub is freed), the shipment is taken off the
      vehicle carrying it (capacity and piggybacked list released) and placed at its
      destination / origin hub.
    misplaced: any in-progress recovery is failed and cleared (reserved capacity freed); a
      shipment already aboard stays aboard, as a detected misplacement does, until a new
      recovery is executed.
    in_transit / delayed / piggybacked: status only; carriage and recovery are untouched.
    """
    s = db.get(Shipment, shipment_id)
    if s is None:
        raise HTTPException(404, "Shipment not found")
    now = clock.now()
    if body.status in END_CARRIAGE_HUB or body.status == "misplaced":
        fleet_progress.cancel_recovery(db, s, now)
    if body.status in END_CARRIAGE_HUB:
        fleet_progress.end_carriage(db, s, getattr(s, END_CARRIAGE_HUB[body.status]))
    if body.status == "misplaced" and s.status != "misplaced":
        s.misplacement_detected_at = now
    s.status = body.status
    db.commit()
    recommendation_loop.mark_dirty(s.id)
    return shipment_dict(s)
