"""Additive tables for device management; existing telemetry is preserved."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.main import Base, now


class DeviceDetails(Base):
    __tablename__ = "device_details"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    location: Mapped[str] = mapped_column(String(100), default="")
    hardware: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    report_interval_ms: Mapped[int] = mapped_column(Integer, default=1000)
    offline_timeout_s: Mapped[int] = mapped_column(Integer, default=10)
    broker_provisioned: Mapped[bool] = mapped_column(Boolean, default=False)
    offline_alert: Mapped[bool] = mapped_column(Boolean, default=True)
    full_alert: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_state: Mapped[str] = mapped_column(String(16), default="unknown")
    forced_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    fault: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_boot_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DeviceGrant(Base):
    __tablename__ = "device_grants"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    can_control: Mapped[bool] = mapped_column(Boolean, default=False)
    can_configure: Mapped[bool] = mapped_column(Boolean, default=False)


class DeviceSlot(Base):
    __tablename__ = "device_slots"
    slot_name: Mapped[str] = mapped_column(ForeignKey("slots.name"), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    gpio: Mapped[int] = mapped_column(Integer)


class SeenPacket(Base):
    __tablename__ = "seen_packets"
    device_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    boot_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DeviceBoot(Base):
    __tablename__ = "device_boots"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    boot_id: Mapped[str] = mapped_column(String(32), primary_key=True)


class ParkingEvent(Base):
    __tablename__ = "parking_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    slot_name: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(24))
    occupied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class AlertDetails(Base):
    __tablename__ = "alert_details"
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    active_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeviceCommand(Base):
    __tablename__ = "device_commands"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(32))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_boot_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    uptime_deadline_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
