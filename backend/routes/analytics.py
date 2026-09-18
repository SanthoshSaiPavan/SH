"""Dashboard KPIs and chart data. Periods are measured on the engine clock."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Hub, RecoveryAction, Shipment
from engines.graph_network import nearest_hub
from realtime import auth
from utils import clock

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
ACTIVE = ("at_origin", "in_transit", "misplaced", "piggybacked", "delayed")


def _saving(a: RecoveryAction) -> float:
    baseline = (a.recovery_route or {}).get("dedicated_cost") or 0.0
    return max(0.0, baseline - (a.additional_cost or 0.0))


def _completed(db):
    return db.query(RecoveryAction).filter_by(status="completed").all()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    now = clock.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    actions = db.query(RecoveryAction).all()
    finished = [a for a in actions if a.status in ("completed", "failed")]
    completed = [a for a in finished if a.status == "completed"]
    return {
        "active_shipments": db.query(Shipment).filter(Shipment.status.in_(ACTIVE)).count(),
        "misplaced_now": db.query(Shipment).filter_by(status="misplaced").count(),
        "misplaced_today": db.query(Shipment).filter(
            Shipment.misplacement_detected_at >= day_start).count(),
        "piggybacked_now": db.query(Shipment).filter_by(status="piggybacked").count(),
        "recovery_rate": round(len(completed) / len(finished), 3) if finished else None,
        "recoveries_in_progress": sum(a.status == "in_progress" for a in actions),
        "cost_saved_today": round(sum(_saving(a) for a in completed
                                      if a.completed_at and a.completed_at >= day_start), 2),
        "cost_saved_total": round(sum(_saving(a) for a in completed), 2),
        "as_of": now.isoformat(),
    }


@router.get("/recovery-rate")
def recovery_rate(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    by_day = defaultdict(Counter)
    for a in db.query(RecoveryAction).filter(RecoveryAction.status.in_(("completed", "failed"))):
        day = (a.completed_at or a.created_at).date().isoformat()
        by_day[day][a.status] += 1
    series = [{"date": d, "completed": c["completed"], "failed": c["failed"],
               "rate": round(c["completed"] / (c["completed"] + c["failed"]), 3)}
              for d, c in sorted(by_day.items())]
    totals = Counter(a.status for a in db.query(RecoveryAction))
    return {"series": series, "totals": dict(totals)}


@router.get("/cost-savings")
def cost_savings(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    now = clock.now()
    completed = _completed(db)

    def since(delta):
        return round(sum(_saving(a) for a in completed
                         if a.completed_at and a.completed_at >= now - delta), 2)

    by_day = defaultdict(float)
    for a in completed:
        if a.completed_at:
            by_day[a.completed_at.date().isoformat()] += _saving(a)
    return {"today": since(timedelta(days=1)), "week": since(timedelta(days=7)),
            "month": since(timedelta(days=30)),
            "series": [{"date": d, "saved": round(v, 2)} for d, v in sorted(by_day.items())]}


@router.get("/strategy-usage")
def strategy_usage(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    actions = db.query(RecoveryAction).all()
    counts = Counter(a.action_type for a in actions)
    durations = defaultdict(list)
    for a in actions:
        if a.status == "completed" and a.completed_at and a.recovery_route:
            start = (a.recovery_route or {}).get("start_time")
            if start:
                durations[a.action_type].append(
                    (a.completed_at - datetime.fromisoformat(start)).total_seconds() / 3600)
    total = sum(counts.values())
    return [{"strategy": s, "count": counts.get(s, 0),
             "share": round(counts.get(s, 0) / total, 3) if total else 0,
             "avg_recovery_hours": round(sum(durations[s]) / len(durations[s]), 2)
             if durations[s] else None}
            for s in ("piggyback", "reroute", "dedicated", "hold")]


@router.get("/heatmap")
def heatmap(db: Session = Depends(get_db), _=Depends(auth.require_any)):
    """Misplacements per hub: recovery start hubs plus currently misplaced shipments."""
    hubs = {h.id: h for h in db.query(Hub).all()}
    counts = Counter()
    for a in db.query(RecoveryAction):
        start = ((a.recovery_route or {}).get("hubs") or [None])[0]
        if start in hubs:
            counts[start] += 1
    for s in db.query(Shipment).filter_by(status="misplaced"):
        if s.current_hub_id in hubs:
            counts[s.current_hub_id] += 1
        elif s.current_lat is not None:
            counts[nearest_hub(hubs, s.current_lat, s.current_lng).id] += 1
    return [{"hub_id": hid, "name": hubs[hid].name, "lat": hubs[hid].lat, "lng": hubs[hid].lng,
             "count": n} for hid, n in counts.most_common()]
