"""python-socketio server: JWT handshake, rooms, and client event handlers.

Server→client events always go to rooms (never a global broadcast):
    vehicle:{id}   fleet:{fleet_id}   shipment:{id}
"""
from __future__ import annotations

import logging
import re

import jwt
import socketio

import config
from realtime import auth

log = logging.getLogger(__name__)

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=config.CORS_ORIGINS)
FLEET_ROOM = f"fleet:{config.DEFAULT_FLEET_ID}"
ROOM_PATTERN = re.compile(r"^(vehicle|shipment|fleet):[A-Za-z0-9_\-]{1,64}$")


async def emit_to_rooms(event: str, data: dict, rooms) -> None:
    for room in dict.fromkeys(rooms):
        await sio.emit(event, data, room=room)


async def emit_fleet(event: str, data: dict, shipment_id: str | None = None,
                     vehicle_id: str | None = None) -> None:
    rooms = [FLEET_ROOM]
    if shipment_id:
        rooms.append(f"shipment:{shipment_id}")
    if vehicle_id:
        rooms.append(f"vehicle:{vehicle_id}")
    await emit_to_rooms(event, data, rooms)


@sio.event
async def connect(sid, environ, auth_data):
    token = (auth_data or {}).get("token")
    if not token:
        raise socketio.exceptions.ConnectionRefusedError("missing token")
    try:
        claims = auth.decode_token(token)
    except jwt.PyJWTError as exc:
        raise socketio.exceptions.ConnectionRefusedError("invalid token") from exc
    await sio.save_session(sid, {"claims": claims})
    if claims.get("role") in auth.OPERATOR_ROLES:
        await sio.enter_room(sid, FLEET_ROOM)


async def _claims(sid) -> dict:
    return (await sio.get_session(sid)).get("claims", {})


@sio.on("room:join")
async def room_join(sid, data):
    claims = await _claims(sid)
    room = (data or {}).get("room", "")
    if not ROOM_PATTERN.match(room):
        return {"ok": False, "error": "invalid room"}
    is_own_vehicle = room.startswith("vehicle:") and auth.can_report_vehicle(claims, room[8:])
    if claims.get("role") not in auth.OPERATOR_ROLES and not is_own_vehicle:
        return {"ok": False, "error": "forbidden"}
    await sio.enter_room(sid, room)
    return {"ok": True}


@sio.on("room:leave")
async def room_leave(sid, data):
    room = (data or {}).get("room", "")
    if ROOM_PATTERN.match(room):
        await sio.leave_room(sid, room)
    return {"ok": True}


@sio.on("vehicle:location")
async def vehicle_location(sid, data):
    from realtime.location_service import location_service

    ok, reason = await location_service.ingest(await _claims(sid), data or {})
    return {"ok": ok, "error": reason}


@sio.on("recovery:approve")
async def recovery_approve(sid, data):
    from realtime.recommendation_loop import recommendation_loop

    claims = await _claims(sid)
    if claims.get("role") not in auth.OPERATOR_ROLES:
        return {"ok": False, "error": "forbidden"}
    data = data or {}
    return await recommendation_loop.approve(data.get("shipment_id"), data.get("strategy_id"),
                                             claims.get("sub"))


@sio.on("recovery:reject")
async def recovery_reject(sid, data):
    from realtime.recommendation_loop import recommendation_loop

    claims = await _claims(sid)
    if claims.get("role") not in auth.OPERATOR_ROLES:
        return {"ok": False, "error": "forbidden"}
    data = data or {}
    return await recommendation_loop.reject(data.get("shipment_id"), data.get("reason", ""),
                                            claims.get("sub"))
