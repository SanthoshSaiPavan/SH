"""MODULE 6: LLM recovery decision agent (Ollama).

A thin reasoning layer over Module 3 output. It never decides or scores:
numbers come from the Evaluation object, and the LLM only phrases them.
Every explanation is built from a grounded fact sheet; if Ollama is
unreachable the fact sheet itself is returned so the demo never shows an
explanation that contradicts the on-screen scores.
"""
from __future__ import annotations

import json
import logging
import uuid

import httpx
from sqlalchemy.orm import Session

import config
from database.models import DecisionAuditLog, Shipment
from engines import recovery_engine as re_
from utils import clock

log = logging.getLogger(__name__)

DEADLINE_RISK_BUFFER_HOURS = 2.0  # ASSUMPTION: buffer below this is flagged
CAPACITY_RISK_FIT = 0.9  # ASSUMPTION: fit above this leaves little slack

SYSTEM_PROMPT = (
    "You are the explanation layer of a logistics recovery system. You are given a FACTS "
    "block computed by the scoring engine. Explain using ONLY those facts. Do not invent "
    "numbers, vehicles, hubs, reasons, or events. If the facts do not answer the question, "
    "say that the data does not cover it. Use ₹ for money. Be concise (at most 5 sentences)."
)


def _money(value: float) -> str:
    return f"₹{value:,.0f}"


def fact_sheet(shipment, evaluation: re_.Evaluation, recommended=None) -> dict:
    """Every number the agent may cite, taken directly from engine output.

    `recommended` is the stable recommendation shown to operators (it can lag
    evaluation.best by the switch margin); defaults to evaluation.best.
    """
    best = recommended or evaluation.best
    now = clock.now()
    return {
        "shipment": {
            "id": shipment.id, "priority": shipment.priority, "status": shipment.status,
            "misplacement_type": shipment.misplacement_type,
            "current_hub": shipment.current_hub_id,
            "destination_hub": shipment.destination_hub_id,
            "weight_kg": shipment.weight_kg, "volume_cbm": shipment.volume_cbm,
            "hours_to_deadline": round((shipment.deadline - now).total_seconds() / 3600, 2),
        },
        "recovery_mode": evaluation.recovery_mode,
        "dedicated_vehicle_cost": round(evaluation.dedicated_cost, 2),
        "recommended": best.to_dict() if best else None,
        "alternatives": [
            {"id": s.id, "type": s.type, "score": s.score, "cost": round(s.cost, 2),
             "feasible": s.feasible, "deadline_met": s.deadline_met,
             "buffer_hours": round(s.buffer_hours, 2), "vehicle_id": s.vehicle_id,
             "on_time_probability": round(s.on_time_probability, 3),
             "pareto_label": s.pareto_label}
            for s in evaluation.strategies if s.id != (best.id if best else None)
        ],
        "rejected_options": evaluation.rejected_options,
    }


def template_explanation(facts: dict) -> str:
    """Deterministic explanation built only from the fact sheet."""
    rec = facts["recommended"]
    shp = facts["shipment"]
    if rec is None or not rec["feasible"]:
        return (f"No feasible recovery strategy was found for {shp['id']}; "
                f"it has been escalated for manual review.")
    parts = [f"{rec['type'].upper()} scored {rec['score']:.1f}/100 for {shp['id']} "
             f"({shp['priority']} priority)."]
    if rec["type"] in ("piggyback", "hold") and rec["vehicle_id"]:
        d = rec["details"]
        pickup = d.get("pickup_time") or d.get("next_vehicle_departure")
        parts.append(f"Vehicle {rec['vehicle_id']} departs {rec['hubs'][0]} at {pickup}"
                     + (f" with {d['available_capacity_kg']:.0f} kg free capacity"
                        if "available_capacity_kg" in d else "")
                     + (f", after a {rec['detour_km']:.0f} km detour" if rec["detour_km"] else "")
                     + ".")
    parts.append(f"Estimated arrival {rec['arrival_time']}, "
                 + (f"{rec['buffer_hours']:.1f} h before the deadline."
                    if rec["deadline_met"] else
                    f"{-rec['buffer_hours']:.1f} h after the deadline.")
                 + f" P(on-time) {rec['on_time_probability']:.2f}.")
    for r in facts.get("rejected_options") or []:
        parts.append(f"{r['vehicle_id']} was rejected: {r['reason']}.")
    saving = facts["dedicated_vehicle_cost"] - rec["cost"]
    parts.append(f"Cost {_money(rec['cost'])}"
                 + (f", {_money(saving)} less than a dedicated vehicle "
                    f"({_money(facts['dedicated_vehicle_cost'])})." if saving > 0 else "."))
    s = rec["scores"]
    parts.append("Score components: " + ", ".join(f"{k} {v:.2f}" for k, v in s.items()) + ".")
    return " ".join(parts)


def _ollama(question: str, facts: dict) -> str | None:
    prompt = f"FACTS:\n{json.dumps(facts, indent=1, default=str)}\n\nQUESTION: {question}"
    try:
        resp = httpx.post(
            f"{config.OLLAMA_URL}/api/chat",
            json={"model": config.OLLAMA_MODEL, "stream": False,
                  "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                               {"role": "user", "content": prompt}],
                  "options": {"temperature": 0.1}},
            timeout=config.OLLAMA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        text = resp.json().get("message", {}).get("content", "").strip()
        return text or None
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Ollama unavailable, using template: %s", exc)
        return None


def explain_recommendation(shipment, evaluation: re_.Evaluation, recommended=None) -> dict:
    facts = fact_sheet(shipment, evaluation, recommended)
    grounded = template_explanation(facts)
    llm = _ollama("Explain why the recommended strategy was chosen over the alternatives. "
                  f"Reference text you may rephrase: {grounded}", facts)
    return {"explanation": llm or grounded, "grounded_summary": grounded,
            "source": "llm" if llm else "template", "model": config.OLLAMA_MODEL if llm else None,
            "facts": facts}


def summarize_risk(shipment, strategy: re_.Strategy | None, evaluation=None) -> dict:
    """{deadline_risk, capacity_risk, route_risk, cost_delta} computed from strategy fields."""
    if strategy is None or not strategy.feasible:
        return {"deadline_risk": True, "capacity_risk": False, "route_risk": True,
                "cost_delta": None, "notes": ["No feasible strategy"]}
    notes = []
    deadline_risk = strategy.buffer_hours < DEADLINE_RISK_BUFFER_HOURS
    if deadline_risk:
        notes.append(f"Only {strategy.buffer_hours:.1f} h deadline buffer")
    fit = (strategy.details.get("match_scores") or {}).get("capacity", 0.0)
    capacity_risk = fit > CAPACITY_RISK_FIT
    if capacity_risk:
        notes.append(f"Capacity fit {fit:.2f}: little slack on the vehicle")
    backups = [s for s in (evaluation.strategies if evaluation else [])
               if s is not strategy and s.feasible and s.deadline_met]
    route_risk = not backups
    if route_risk:
        notes.append("No backup strategy that also meets the deadline")
    cost_delta = round(strategy.cost - evaluation.dedicated_cost, 2) if evaluation else None
    return {"deadline_risk": deadline_risk, "capacity_risk": capacity_risk,
            "route_risk": route_risk, "cost_delta": cost_delta, "notes": notes}


def _deadline_risk_rows(db: Session, evaluations: dict) -> list[dict]:
    now = clock.now()
    rows = []
    for s in db.query(Shipment).filter(Shipment.status.notin_(("delivered", "recovered"))):
        ev = evaluations.get(s.id)
        best = ev.best if ev else None
        at_risk = (best is not None and not best.deadline_met) or s.deadline < now
        if at_risk or (best and best.buffer_hours < DEADLINE_RISK_BUFFER_HOURS):
            rows.append({"shipment_id": s.id, "priority": s.priority, "status": s.status,
                         "deadline": s.deadline.isoformat(),
                         "best_strategy": best.type if best else None,
                         "buffer_hours": round(best.buffer_hours, 2) if best else None})
    return rows


def answer_query(db: Session, question: str, evaluations: dict,
                 shipment_id: str | None = None, recommended: dict | None = None) -> dict:
    """Route a free-text question to retrieved data, then let the LLM summarise only that."""
    if shipment_id:
        shipment = db.get(Shipment, shipment_id)
        if shipment is None:
            return {"answer": f"Shipment {shipment_id} not found.", "source": "system"}
        ev = evaluations.get(shipment_id)
        facts = fact_sheet(shipment, ev, (recommended or {}).get(shipment_id)) if ev else {
            "shipment": {"id": shipment.id, "status": shipment.status,
                         "priority": shipment.priority},
            "note": "No recovery evaluation exists for this shipment."}
        fallback = template_explanation(facts) if ev else json.dumps(facts, default=str)
    else:
        rows = _deadline_risk_rows(db, evaluations)
        facts = {"shipments_at_deadline_risk": rows,
                 "misplaced_count": db.query(Shipment).filter_by(status="misplaced").count()}
        fallback = ("Shipments at deadline risk: "
                    + (", ".join(f"{r['shipment_id']} ({r['priority']})" for r in rows) or "none")
                    + ".")
    llm = _ollama(question, facts)
    return {"answer": llm or fallback, "source": "llm" if llm else "template", "facts": facts}


def run_what_if(shipment, evaluation: re_.Evaluation, hypothetical_strategy_type: str,
                recommended=None) -> dict:
    """Compare a hypothetical strategy (already scored by Module 3) with the current pick."""
    current = recommended or evaluation.best
    alt = evaluation.strategy(hypothetical_strategy_type) or next(
        (s for s in evaluation.strategies if s.type == hypothetical_strategy_type), None)
    if alt is None:
        return {"error": f"Unknown strategy type '{hypothetical_strategy_type}'"}
    return {
        "shipment_id": shipment.id,
        "current": current.to_dict() if current else None,
        "hypothetical": alt.to_dict(),
        "delta": {
            "score": round(alt.score - (current.score if current else 0), 2),
            "cost": round(alt.cost - (current.cost if current else 0), 2),
            "buffer_hours": round(alt.buffer_hours - (current.buffer_hours if current else 0), 2),
        },
        "hypothetical_meets_deadline": alt.deadline_met,
    }


def log_decision(db: Session, shipment_id: str, explanation: str, risk_summary: dict | None,
                 confidence: float | None = None, operator_query: str | None = None,
                 operator_decision: str | None = None,
                 recovery_action_id: str | None = None) -> DecisionAuditLog:
    record = DecisionAuditLog(
        id=f"AUD-{uuid.uuid4().hex[:10]}", shipment_id=shipment_id,
        recovery_action_id=recovery_action_id, explanation=explanation,
        risk_summary=risk_summary, confidence_score=confidence, operator_query=operator_query,
        operator_decision=operator_decision,
    )
    db.add(record)
    db.commit()
    return record
