"""Shipment CRUD and status endpoints."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Hub, Shipment
from realtime import auth
from routes.serializers import shipment_dict
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


@router.patch("/{shipment_id}/status")
def update_status(shipment_id: str, body: StatusUpdate, db: Session = Depends(get_db),
                  _=Depends(auth.require_operator)):
    s = db.get(Shipment, shipment_id)
    if s is None:
        raise HTTPException(404, "Shipment not found")
    s.status = body.status
    db.commit()
    return shipment_dict(s)


