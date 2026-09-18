"""Vehicle tracking, capacity, and location history endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Hub, Shipment, Vehicle, VehicleLocation
from realtime import auth
from realtime.location_service import location_service
from routes.serializers import shipment_dict, vehicle_dict
from utils.geo import haversine

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


class PositionUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    speed: float = Field(default=0, ge=0, le=300)
    heading: float = Field(default=0, ge=0, le=360)
    timestamp: str | None = None


@router.get("")
async def list_vehicles(status: str | None = None, vehicle_type: str | None = None,
                        db: Session = Depends(get_db), _=Depends(auth.require_any)):
    query = db.query(Vehicle)
    if status:
        query = query.filter(Vehicle.status.in_(status.split(",")))
    if vehicle_type:
        query = query.filter(Vehicle.vehicle_type == vehicle_type)
    live = await location_service.all_states()
    return [vehicle_dict(v, live.get(v.id)) for v in query.order_by(Vehicle.id)]


@router.get("/nearby/{hub_id}")
async def nearby(hub_id: str, radius_km: float = 150, db: Session = Depends(get_db),
                 _=Depends(auth.require_any)):
    hub = db.get(Hub, hub_id)
    if hub is None:
        raise HTTPException(404, "Hub not found")
    live = await location_service.all_states()
    out = []
    for v in db.query(Vehicle).all():
        lat, lng = (live[v.id]["lat"], live[v.id]["lng"]) if v.id in live else (
            v.current_lat, v.current_lng)
        km = haversine(hub.lat, hub.lng, lat, lng)
        if km <= radius_km:
            out.append({**vehicle_dict(v, live.get(v.id)), "distance_km": round(km, 1)})
    return sorted(out, key=lambda x: x["distance_km"])


@router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: str, db: Session = Depends(get_db),
                      _=Depends(auth.require_any)):
    v = db.get(Vehicle, vehicle_id)
    if v is None:
        raise HTTPException(404, "Vehicle not found")
    live = await location_service.all_states()
    cargo = db.query(Shipment).filter_by(current_vehicle_id=vehicle_id).all()
    return {**vehicle_dict(v, live.get(v.id)), "cargo": [shipment_dict(s) for s in cargo]}


@router.get("/{vehicle_id}/location-history")
def history(vehicle_id: str, limit: int = 500, db: Session = Depends(get_db),
            _=Depends(auth.require_any)):
    rows = (db.query(VehicleLocation).filter_by(vehicle_id=vehicle_id)
            .order_by(VehicleLocation.recorded_at.desc()).limit(min(limit, 5000)).all())
    return [{"lat": r.lat, "lng": r.lng, "speed_kmh": r.speed_kmh, "heading": r.heading,
             "recorded_at": r.recorded_at.isoformat()} for r in reversed(rows)]


@router.patch("/{vehicle_id}/position")
async def update_position(vehicle_id: str, body: PositionUpdate,
                          user: dict = Depends(auth.require_roles("ADMIN", "DRIVER"))):
    ok, error = await location_service.ingest(user, {"vehicle_id": vehicle_id,
                                                     **body.model_dump()})
    if not ok:
        raise HTTPException(422, error)
    return {"ok": True}
