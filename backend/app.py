"""PiggyShip backend: FastAPI REST + python-socketio, one process.

Run from backend/:  uvicorn app:socket_app --reload --port 8000
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from database.db import init_db
from database.seed_data import seed_if_empty
from engines.simulation import engine_loop
from realtime.location_service import location_service
from realtime.recommendation_loop import recommendation_loop
from realtime.socket_server import sio
from routes import agent, analytics, auth, graph, recovery, shipments, simulation, vehicles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    if seed_if_empty():
        await location_service.reset()
    await location_service.prime_from_db()
    tasks = [asyncio.create_task(coro) for coro in (
        engine_loop(), recommendation_loop.run(), location_service.flush_loop(),
        location_service.status_loop())]
    yield
    for t in tasks:
        t.cancel()
    location_service.flush()


app = FastAPI(title="PiggyShip API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for module in (auth, shipments, vehicles, recovery, analytics, simulation, agent, graph):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"ok": True}


socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
