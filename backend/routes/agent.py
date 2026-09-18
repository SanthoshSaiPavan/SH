"""Module 6 endpoints: explain, risk, query, what-if, audit trail."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from database.db import SessionLocal, get_db
from database.models import DecisionAuditLog, Shipment
from engines import decision_agent
from realtime import auth
from realtime.recommendation_loop import recommendation_loop
from routes.serializers import audit_dict

router = APIRouter(prefix="/api/agent", tags=["agent"])


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    shipment_id: str | None = Field(default=None, max_length=64)


class WhatIfRequest(BaseModel):
    shipment_id: str = Field(min_length=1, max_length=64)
    hypothetical_strategy: str = Field(pattern="^(piggyback|reroute|dedicated|hold)$")


async def _evaluated(db, shipment_id: str):
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(404, "Shipment not found")
    ev = await recommendation_loop.ensure_evaluation(db, shipment_id)
    if ev is None:
        raise HTTPException(409, "No recovery evaluation for this shipment (is it misplaced?)")
    return shipment, ev


@router.get("/explain/{shipment_id}")
async def explain(shipment_id: str, _=Depends(auth.require_any)):
    with SessionLocal() as db:
        shipment, ev = await _evaluated(db, shipment_id)
        rec = recommendation_loop.current.get(shipment_id, ev.best)
        result = await run_in_threadpool(decision_agent.explain_recommendation, shipment, ev, rec)
        risk = decision_agent.summarize_risk(shipment, rec, ev)
        decision_agent.log_decision(db, shipment_id, result["explanation"], risk,
                                    confidence=rec.score if rec else None)
    return {**result, "risk": risk}


@router.get("/risk/{shipment_id}")
async def risk(shipment_id: str, _=Depends(auth.require_any)):
    with SessionLocal() as db:
        shipment, ev = await _evaluated(db, shipment_id)
        rec = recommendation_loop.current.get(shipment_id, ev.best)
        return decision_agent.summarize_risk(shipment, rec, ev)


@router.post("/query")
async def query(body: QueryRequest, _=Depends(auth.require_any)):
    with SessionLocal() as db:
        result = await run_in_threadpool(decision_agent.answer_query, db, body.question,
                                         recommendation_loop.evaluations, body.shipment_id,
                                         recommendation_loop.current)
        if body.shipment_id and db.get(Shipment, body.shipment_id) is not None:
            decision_agent.log_decision(db, body.shipment_id, result["answer"], None,
                                        operator_query=body.question)
    return result


@router.post("/what-if")
async def what_if(body: WhatIfRequest, _=Depends(auth.require_any)):
    with SessionLocal() as db:
        shipment, ev = await _evaluated(db, body.shipment_id)
        return decision_agent.run_what_if(shipment, ev, body.hypothetical_strategy,
                                          recommendation_loop.current.get(body.shipment_id))


@router.get("/audit-trail/{shipment_id}")
def audit_trail(shipment_id: str, db: Session = Depends(get_db), _=Depends(auth.require_any)):
    rows = (db.query(DecisionAuditLog).filter_by(shipment_id=shipment_id)
            .order_by(DecisionAuditLog.created_at))
    return [audit_dict(r) for r in rows]
