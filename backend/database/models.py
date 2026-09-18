"""ORM models mirroring the plan's schema.

Additions beyond the plan (approved): vehicles.hazmat_certifications,
vehicles.fleet_id, shipments.last_scan_at, shipments.current_vehicle_id, the users table,
and (level-up, scan-based detection) shipments.manifest_vehicle_id and the scan_events table.
JSON-array columns use the JSON type instead of TEXT.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base

SHIPMENT_STATUSES = (
    "at_origin", "in_transit", "misplaced", "piggybacked", "recovered", "delivered", "delayed",
)
PRIORITIES = ("critical", "high", "medium", "low")
MISPLACEMENT_TYPES = ("wrong_hub", "wrong_vehicle", "stuck")
STRATEGY_TYPES = ("piggyback", "reroute", "dedicated", "hold")
RECOVERY_MODES = ("auto_executed", "pending_approval", "escalated")
VEHICLE_STATUSES = ("idle", "loading", "in_transit", "at_hub", "completed")
ACTION_STATUSES = ("proposed", "approved", "in_progress", "completed", "failed")
SCAN_EVENT_TYPES = ("load", "unload", "hub_scan", "short", "excess")


class Hub(Base):
    __tablename__ = "hubs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    hub_type: Mapped[str] = mapped_column(String, nullable=False)
    capacity_packages: Mapped[int] = mapped_column(Integer, nullable=False)
    current_load: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    can_hold_misplaced: Mapped[bool] = mapped_column(Boolean, default=True)
    operating_hours: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    hub_sequence: Mapped[list] = mapped_column(JSON, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_time_hours: Mapped[float] = mapped_column(Float, nullable=False)
    cost_per_km: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    vehicle_type: Mapped[str] = mapped_column(String, nullable=False)
    carrier_name: Mapped[str] = mapped_column(String, nullable=False)
    current_lat: Mapped[float] = mapped_column(Float, nullable=False)
    current_lng: Mapped[float] = mapped_column(Float, nullable=False)
    route_id: Mapped[str | None] = mapped_column(ForeignKey("routes.id"))
    planned_route: Mapped[list] = mapped_column(JSON, nullable=False)
    # Index into planned_route of the next hub the vehicle will reach
    # (or the hub it is at, when status == 'at_hub').
    current_stop_index: Mapped[int] = mapped_column(Integer, default=0)
    total_capacity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    used_capacity_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    total_capacity_cbm: Mapped[float] = mapped_column(Float, nullable=False)
    used_capacity_cbm: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    speed_kmh: Mapped[float] = mapped_column(Float, default=60)
    status: Mapped[str] = mapped_column(String, nullable=False, default="in_transit")
    eta_destination: Mapped[datetime | None] = mapped_column(DateTime)
    piggybacked_shipments: Mapped[list | None] = mapped_column(JSON, default=list)
    hazmat_certifications: Mapped[list | None] = mapped_column(JSON, default=list)
    fleet_id: Mapped[str] = mapped_column(String, nullable=False, default="FLEET-MAIN")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tracking_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    origin_hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id"), nullable=False)
    destination_hub_id: Mapped[str] = mapped_column(ForeignKey("hubs.id"), nullable=False)
    current_hub_id: Mapped[str | None] = mapped_column(ForeignKey("hubs.id"))
    expected_route: Mapped[list] = mapped_column(JSON, nullable=False)
    actual_route: Mapped[list | None] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, nullable=False, default="in_transit")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    handling_flags: Mapped[list | None] = mapped_column(JSON, default=list)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    volume_cbm: Mapped[float] = mapped_column(Float, nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    current_lat: Mapped[float | None] = mapped_column(Float)
    current_lng: Mapped[float | None] = mapped_column(Float)
    # Vehicle currently carrying the shipment (normal carriage, not recovery).
    current_vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"))
    # Vehicle the shipment is manifested on for its current leg (what the paperwork says).
    manifest_vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"))
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime)
    misplacement_type: Mapped[str | None] = mapped_column(String)
    misplacement_detected_at: Mapped[datetime | None] = mapped_column(DateTime)
    recovery_strategy: Mapped[str | None] = mapped_column(String)
    recovery_vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"))
    recovery_score: Mapped[float | None] = mapped_column(Float)
    recovery_mode: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    scans: Mapped[list["ScanEvent"]] = relationship(order_by="ScanEvent.scanned_at")


class ScanEvent(Base):
    """A barcode scan (or a missing one) at a hub or vehicle: Module 1's only parcel evidence.

    'short' = manifested on a vehicle that reached the parcel's next hub without it;
    'excess' = scanned at a hub that is not on its expected route.
    """
    __tablename__ = "scan_events"
    __table_args__ = (Index("idx_scan_events_shipment_time", "shipment_id", "scanned_at"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    hub_id: Mapped[str | None] = mapped_column(ForeignKey("hubs.id"))
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"))
    expected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str | None] = mapped_column(String)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    matched_vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"))
    original_route: Mapped[list | None] = mapped_column(JSON)
    recovery_route: Mapped[list | dict | None] = mapped_column(JSON)
    detour_km: Mapped[float | None] = mapped_column(Float)
    additional_cost: Mapped[float | None] = mapped_column(Float)
    time_impact_hours: Mapped[float | None] = mapped_column(Float)
    capacity_fit_score: Mapped[float | None] = mapped_column(Float)
    deadline_risk_score: Mapped[float | None] = mapped_column(Float)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class DecisionAuditLog(Base):
    __tablename__ = "decision_audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    shipment_id: Mapped[str] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    recovery_action_id: Mapped[str | None] = mapped_column(ForeignKey("recovery_actions.id"))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    risk_summary: Mapped[dict | None] = mapped_column(JSON)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    operator_query: Mapped[str | None] = mapped_column(Text)
    operator_decision: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VehicleLocation(Base):
    __tablename__ = "vehicle_locations"
    __table_args__ = (Index("idx_vehicle_locations_vehicle_time", "vehicle_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    heading: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    vehicle_id: Mapped[str | None] = mapped_column(ForeignKey("vehicles.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
