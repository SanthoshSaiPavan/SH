"""ORM → JSON-ready dicts shared by the route modules."""


def _iso(value):
    return value.isoformat() if value is not None else None


def hub_dict(h) -> dict:
    return {"id": h.id, "name": h.name, "city": h.city, "state": h.state, "lat": h.lat,
            "lng": h.lng, "hub_type": h.hub_type, "capacity_packages": h.capacity_packages,
            "current_load": h.current_load, "can_hold_misplaced": h.can_hold_misplaced,
            "operating_hours": h.operating_hours}


def shipment_dict(s) -> dict:
    return {
        "id": s.id, "tracking_number": s.tracking_number, "origin_hub_id": s.origin_hub_id,
        "destination_hub_id": s.destination_hub_id, "current_hub_id": s.current_hub_id,
        "expected_route": s.expected_route, "actual_route": s.actual_route, "status": s.status,
        "priority": s.priority, "handling_flags": s.handling_flags or [],
        "weight_kg": s.weight_kg, "volume_cbm": s.volume_cbm, "deadline": _iso(s.deadline),
        "current_lat": s.current_lat, "current_lng": s.current_lng,
        "current_vehicle_id": s.current_vehicle_id, "last_scan_at": _iso(s.last_scan_at),
        "misplacement_type": s.misplacement_type,
        "misplacement_detected_at": _iso(s.misplacement_detected_at),
        "recovery_strategy": s.recovery_strategy, "recovery_vehicle_id": s.recovery_vehicle_id,
        "recovery_score": s.recovery_score, "recovery_mode": s.recovery_mode,
        "created_at": _iso(s.created_at), "updated_at": _iso(s.updated_at),
    }


def vehicle_dict(v, live: dict | None = None) -> dict:
    return {
        "id": v.id, "vehicle_type": v.vehicle_type, "carrier_name": v.carrier_name,
        "current_lat": v.current_lat, "current_lng": v.current_lng, "route_id": v.route_id,
        "planned_route": v.planned_route, "current_stop_index": v.current_stop_index,
        "total_capacity_kg": v.total_capacity_kg, "used_capacity_kg": v.used_capacity_kg,
        "total_capacity_cbm": v.total_capacity_cbm, "used_capacity_cbm": v.used_capacity_cbm,
        "speed_kmh": v.speed_kmh, "status": v.status, "eta_destination": _iso(v.eta_destination),
        "piggybacked_shipments": v.piggybacked_shipments or [],
        "hazmat_certifications": v.hazmat_certifications or [], "fleet_id": v.fleet_id,
        "live": live,
    }


def action_dict(a) -> dict:
    return {
        "id": a.id, "shipment_id": a.shipment_id, "action_type": a.action_type,
        "matched_vehicle_id": a.matched_vehicle_id, "original_route": a.original_route,
        "recovery_route": a.recovery_route, "detour_km": a.detour_km,
        "additional_cost": a.additional_cost, "time_impact_hours": a.time_impact_hours,
        "capacity_fit_score": a.capacity_fit_score, "deadline_risk_score": a.deadline_risk_score,
        "overall_score": a.overall_score, "status": a.status, "created_at": _iso(a.created_at),
        "completed_at": _iso(a.completed_at),
    }


def audit_dict(r) -> dict:
    return {"id": r.id, "shipment_id": r.shipment_id, "recovery_action_id": r.recovery_action_id,
            "explanation": r.explanation, "risk_summary": r.risk_summary,
            "confidence_score": r.confidence_score, "operator_query": r.operator_query,
            "operator_decision": r.operator_decision, "created_at": _iso(r.created_at)}
