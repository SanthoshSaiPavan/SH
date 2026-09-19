"""Time-expanded graph snapshot for the 3D graph view (demo route or live network)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import config
from database.db import get_db
from database.models import Hub, Route, Shipment
from engines import graph_network as gn
from engines import graph_view
from realtime import auth
from realtime.recommendation_loop import recommendation_loop

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
def snapshot(source: Literal["demo", "live"] = "demo",
             hours: float = Query(config.GRAPH_VIEW_DEFAULT_HOURS, gt=0,
                                  le=config.GRAPH_HORIZON_HOURS),
             db: Session = Depends(get_db), _=Depends(auth.require_any)):
    graph = recommendation_loop.graph
    if graph is None:
        raise HTTPException(503, "Graph not built yet")
    hubs = {h.id: h for h in db.query(Hub).all()}
    route = None
    if source == "demo":
        route = db.get(Route, config.GRAPH_VIEW_DEMO_ROUTE)
        if route is None:
            raise HTTPException(404, f"Demo route {config.GRAPH_VIEW_DEMO_ROUTE} not seeded")

    recs = []
    for sid, strategy in list(recommendation_loop.current.items()):
        shipment = db.get(Shipment, sid)
        if shipment is None or not strategy.legs:
            continue
        hub = shipment.current_hub_id
        if hub is None and shipment.current_lat is not None:
            hub = gn.nearest_hub(hubs, shipment.current_lat, shipment.current_lng).id
        recs.append({"shipment_id": sid, "hub": hub, "time": shipment.misplacement_detected_at,
                     "legs": strategy.legs})
    return graph_view.serialize(graph, hubs, hours, route=route, recommendations=recs)
