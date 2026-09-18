"""Simulation control: DEMO SIMULATION / LIVE GPS toggle, speed, misplacement, reroutes."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database.db import SessionLocal
from database.models import Hub, Vehicle
from engines.simulation import simulation
from realtime import auth
from realtime.recommendation_loop import recommendation_loop

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


class SpeedRequest(BaseModel):
    speed: int


class ModeRequest(BaseModel):
    mode: Literal["demo", "live"]


class AutoRecoveryRequest(BaseModel):
    enabled: bool


class MisplaceRequest(BaseModel):
    shipment_id: str | None = Field(default=None, max_length=64)
    type: Literal["wrong_hub", "wrong_vehicle", "stuck"] | None = None


class VehicleControl(BaseModel):
    speed_kmh: float | None = Field(default=None, gt=0, le=120)
    remaining_route: list[str] | None = Field(default=None, min_length=1, max_length=20)


@router.get("/status")
def status(_=Depends(auth.require_any)):
    return simulation.status()


@router.post("/start")
def start(_=Depends(auth.require_operator)):
    simulation.start()
    return simulation.status()


@router.post("/stop")
def stop(_=Depends(auth.require_operator)):
    simulation.stop()
    return simulation.status()


@router.post("/speed")
def speed(body: SpeedRequest, _=Depends(auth.require_operator)):
    try:
        simulation.set_speed(body.speed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return simulation.status()


@router.post("/mode")
def mode(body: ModeRequest, _=Depends(auth.require_operator)):
    simulation.set_mode(body.mode)
    return simulation.status()


@router.post("/auto-recovery")
def auto_recovery(body: AutoRecoveryRequest, _=Depends(auth.require_operator)):
    simulation.auto_recovery = body.enabled
    return simulation.status()


@router.post("/trigger-misplacement")
def trigger(body: MisplaceRequest, _=Depends(auth.require_operator)):
    with SessionLocal() as db:
        try:
            result = simulation.misplace(db, body.shipment_id, body.type)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    return result


@router.patch("/vehicles/{vehicle_id}")
def control_vehicle(vehicle_id: str, body: VehicleControl, _=Depends(auth.require_operator)):
    """Change a vehicle's speed and/or replace its remaining stops (demo reroute)."""
    with SessionLocal() as db:
        v = db.get(Vehicle, vehicle_id)
        if v is None:
            raise HTTPException(404, "Vehicle not found")
        if body.speed_kmh is not None:
            v.speed_kmh = body.speed_kmh
        if body.remaining_route is not None:
            if any(db.get(Hub, h) is None for h in body.remaining_route):
                raise HTTPException(422, "Unknown hub in remaining_route")
            keep = v.planned_route[: v.current_stop_index + (1 if v.status == "at_hub" else 0)]
            v.planned_route = keep + body.remaining_route
            if v.status == "completed":
                v.status = "in_transit"
                v.current_stop_index = len(keep)
        db.commit()
        result = {"id": v.id, "speed_kmh": v.speed_kmh, "planned_route": v.planned_route,
                  "current_stop_index": v.current_stop_index}
    recommendation_loop.on_vehicle_moved(vehicle_id)
    return result
