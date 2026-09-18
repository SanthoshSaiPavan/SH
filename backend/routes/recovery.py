"""Recovery options, execution, and history; live piggyback opportunities."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.db import SessionLocal, get_db
from database.models import RecoveryAction, Shipment
from realtime import auth
from realtime.recommendation_loop import recommendation_loop
from routes.serializers import action_dict

router = APIRouter(prefix="/api", tags=["recovery"])


class ExecuteRequest(BaseModel):
    shipment_id: str = Field(min_length=1, max_length=64)
    strategy_id: str | None = Field(default=None, max_length=32)


class RejectRequest(BaseModel):
    shipment_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=500)


@router.get("/recovery/options/{shipment_id}")
async def options(shipment_id: str, _=Depends(auth.require_any)):
    with SessionLocal() as db:
        shipment = db.get(Shipment, shipment_id)
        if shipment is None:
            raise HTTPException(404, "Shipment not found")
        if shipment.status != "misplaced":
            raise HTTPException(409, f"Shipment is {shipment.status}, not misplaced")
        await recommendation_loop.ensure_evaluation(db, shipment_id)
    view = recommendation_loop.view(shipment_id)
    if view is None:
        raise HTTPException(503, "Recovery graph not ready yet")
    return view


@router.post("/recovery/execute")
async def execute(body: ExecuteRequest, user: dict = Depends(auth.require_operator)):
    result = await recommendation_loop.approve(body.shipment_id, body.strategy_id, user["sub"])
    if not result.get("ok"):
        raise HTTPException(409, result.get("error"))
    return result


@router.post("/recovery/reject")
async def reject(body: RejectRequest, user: dict = Depends(auth.require_operator)):
    result = await recommendation_loop.reject(body.shipment_id, body.reason, user["sub"])
    if not result.get("ok"):
        raise HTTPException(404, result.get("error"))
    return result


@router.get("/recovery/active")
def active(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    rows = db.query(RecoveryAction).filter(RecoveryAction.status.in_(
        ("approved", "in_progress"))).order_by(RecoveryAction.created_at.desc())
    return [action_dict(a) for a in rows]


@router.get("/recovery/history")
def history(limit: int = 200, db: Session = Depends(get_db), _=Depends(auth.require_any)):
    rows = (db.query(RecoveryAction).filter(RecoveryAction.status.in_(("completed", "failed")))
            .order_by(RecoveryAction.completed_at.desc().nullslast()).limit(min(limit, 1000)))
    return [action_dict(a) for a in rows]


@router.get("/piggyback/opportunities")
def opportunities(_=Depends(auth.require_any)):
    """Current live recommendations (initial page load only; updates come over sockets)."""
    out = []
    for sid, rec in recommendation_loop.current.items():
        ev = recommendation_loop.evaluations.get(sid)
        if ev is not None:
            out.append(recommendation_loop.recommendation_payload(
                sid, rec, ev, recommendation_loop.reasons.get(sid)))
    return out
