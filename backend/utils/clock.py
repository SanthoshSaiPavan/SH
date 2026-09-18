"""Single source of "now" for engines.

In DEMO SIMULATION mode the simulation engine advances a compressed clock;
in LIVE GPS mode (or before the simulation starts) this is wall-clock time.
All timestamps are naive UTC.
"""
from datetime import datetime, timedelta, timezone

_sim_now: datetime | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now() -> datetime:
    return _sim_now if _sim_now is not None else utcnow()


def set_sim_time(value: datetime | None) -> None:
    global _sim_now
    _sim_now = value


def advance(delta: timedelta) -> datetime:
    global _sim_now
    _sim_now = (_sim_now or utcnow()) + delta
    return _sim_now
