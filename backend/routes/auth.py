"""POST /api/auth/login → JWT with role; GET /api/hubs for the map."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Hub, Route, User
from realtime import auth
from routes.serializers import hub_dict
from utils import roads

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


@router.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()
    if user is None or not auth.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    vehicle_ids = [user.vehicle_id] if user.vehicle_id else []
    return {"token": auth.create_token(user.username, user.role, vehicle_ids),
            "user": {"username": user.username, "role": user.role, "vehicle_ids": vehicle_ids}}


@router.get("/hubs")
def list_hubs(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    return [hub_dict(h) for h in db.query(Hub).order_by(Hub.id)]


@router.get("/routes")
def list_routes(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    return [{"id": r.id, "name": r.name, "hub_sequence": r.hub_sequence,
             "distance_km": r.distance_km, "estimated_time_hours": r.estimated_time_hours,
             "cost_per_km": r.cost_per_km, "active": r.active} for r in db.query(Route)]


@router.get("/road-routes")
def road_routes(pairs: str = Query(..., max_length=4000, description="Comma-separated FROM|TO hub pairs"),
                _=Depends(auth.require_any)):
    """Road geometry for hub pairs, in the requested direction: {"A|B": [[lat, lng], ...]}.

    Pairs with no cached road (or unknown hubs) are omitted; clients draw those straight.
    """
    requested = []
    for item in pairs.split(",")[:200]:
        a_id, sep, b_id = item.partition("|")
        if sep and a_id and b_id:
            requested.append((a_id.strip(), b_id.strip()))
    return roads.paths_for(requested)
