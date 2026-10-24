import logging
from datetime import timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app import main as M
from app.domain import (AlertDetails, DeviceBoot, DeviceCommand, DeviceDetails, DeviceGrant,
                        DeviceSlot, ParkingEvent, SeenPacket)

log = logging.getLogger(__name__)
TERMINAL = {"acknowledged", "failed", "timed_out", "cancelled"}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def details(db, device):
    value = db.get(DeviceDetails, device.id)
    if not value:
        value = DeviceDetails(device_id=device.id)
        db.add(value)
        db.flush()
    return value


def visible_codes(db, user):
    if user.role == "admin":
        return None
    return list(db.scalars(select(M.Device.code).join(DeviceGrant, DeviceGrant.device_id == M.Device.id)
                           .where(DeviceGrant.user_id == user.id)))


def authorize(db, user, device_id=None, code=None, permission="read"):
    device = db.get(M.Device, device_id) if device_id is not None else db.scalar(
        select(M.Device).where(M.Device.code == code))
    if not device:
        raise HTTPException(404, "Device not found")
    if user.role != "admin":
        grant = db.get(DeviceGrant, (device.id, user.id))
        if not grant:
            raise HTTPException(404, "Device not found")
        if permission != "read" and (user.role != "operator" or not getattr(grant, "can_" + permission)):
            raise HTTPException(403, "Insufficient device permission")
    return device


def receiver_ready():
    receiver = getattr(M.app.state, "mqtt_receiver", None)
    return bool(receiver and receiver.connected and receiver.subscribed)


def connectivity(device, info, at=None):
    if device.status in {"revoked", "decommissioned", "registered"}:
        return "disabled" if device.status != "registered" else "unknown"
    if not info or not info.last_seen:
        return "unknown"
    age = ((at or M.now()) - utc(info.last_seen)).total_seconds()
    timeout = max(info.offline_timeout_s, info.report_interval_ms * 3 / 1000)
    return "online" if receiver_ready() and not info.forced_offline and 0 <= age < timeout else "offline"


def seed_physical(db):
    device = db.scalar(select(M.Device).where(M.Device.code == "esp32_01"))
    if not device:
        device = M.Device(code="esp32_01", name="ESP32 bai xe P1/P2", status="active")
        db.add(device)
        db.flush()
        info = details(db, device)
        info.broker_provisioned = True
        info.location = "Bai xe mo hinh"
        info.hardware = "ESP32-D0WD-V3"
    else:
        details(db, device)
    for name, gpio in (("P1", 27), ("P2", 26)):
        if not db.get(DeviceSlot, name):
            db.add(DeviceSlot(slot_name=name, device_id=device.id, gpio=gpio))


def persist_reading(item, received_at):
    with M.Sessions() as db:
        device = db.scalar(select(M.Device).where(M.Device.code == item.device_id))
        simulated = item.device_id == "simulator"
        info = None
        previous_seen = None
        if not simulated:
            if not device or device.status not in {"active", "provisioned", "maintenance"}:
                log.warning("Ignored telemetry from an unregistered or disabled device")
                return False
            info = details(db, device)
            if not info.broker_provisioned:
                return False
            previous_seen = utc(info.last_seen)
        if item.boot_id is not None:
            packet_key = (item.device_id, item.boot_id, item.seq)
            if db.get(SeenPacket, packet_key):
                return False
            if info:
                if info.last_boot_id == item.boot_id and info.last_seq is not None and item.seq <= info.last_seq:
                    return False
                if info.last_boot_id != item.boot_id:
                    if db.get(DeviceBoot, (device.id, item.boot_id)):
                        return False
                    db.add(DeviceBoot(device_id=device.id, boot_id=item.boot_id))
                info.last_boot_id, info.last_seq = item.boot_id, item.seq
            db.add(SeenPacket(device_code=item.device_id, boot_id=item.boot_id, seq=item.seq, received_at=received_at))
        reading = M.Telemetry(device_code=item.device_id, uptime_s=item.uptime_s,
                              do_level=item.do, detected=item.detected, received_at=received_at)
        db.add(reading)
        db.flush()
        levels = [("P1", item.do, item.detected)]
        if item.do2 is not None:
            levels.append(("P2", item.do2, item.detected2))
        for name, level, occupied in levels:
            db.add(M.TelemetrySlot(telemetry_id=reading.id, slot_name=name, do_level=level, occupied=occupied))
            assignment = db.get(DeviceSlot, name)
            if not simulated and assignment and assignment.device_id == device.id and device.status == "active":
                slot = db.scalar(select(M.Slot).where(M.Slot.name == name))
                gap = previous_seen is None or (received_at - previous_seen).total_seconds() >= max(
                    info.offline_timeout_s, info.report_interval_ms * 3 / 1000)
                if slot and (gap or slot.occupied != occupied):
                    db.add(ParkingEvent(device_id=device.id, slot_name=name,
                        kind="initial" if previous_seen is None else ("after_gap" if gap else ("occupied" if occupied else "available")),
                        occupied=occupied, occurred_at=received_at))
                if slot:
                    slot.occupied = occupied
        if info:
            info.last_seen, info.forced_offline = received_at, False
            if item.firmware:
                device.firmware = item.firmware
            if item.hardware:
                info.hardware = item.hardware
            if item.report_interval_ms is not None:
                info.report_interval_ms = item.report_interval_ms
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return False
        return True


def slot_views(db, user=None):
    allowed = visible_codes(db, user) if user else None
    values = []
    for slot in db.scalars(select(M.Slot).order_by(M.Slot.id)):
        assignment = db.get(DeviceSlot, slot.name)
        device = db.get(M.Device, assignment.device_id) if assignment else None
        if user and user.role != "admin" and (not device or device.code not in allowed):
            continue
        sample = None
        fresh = False
        stamp = None
        if device:
            info = db.get(DeviceDetails, device.id)
            sample = db.execute(select(M.TelemetrySlot, M.Telemetry).join(M.Telemetry,
                M.TelemetrySlot.telemetry_id == M.Telemetry.id).where(
                    M.TelemetrySlot.slot_name == slot.name, M.Telemetry.device_code == device.code)
                .order_by(M.Telemetry.id.desc()).limit(1)).first()
            if sample:
                stamp = utc(sample[1].received_at)
                timeout = max(info.offline_timeout_s, info.report_interval_ms * 3 / 1000) if info else 5
                fresh = (device.status == "active" and connectivity(device, info) == "online"
                         and 0 <= (M.now() - stamp).total_seconds() < timeout)
        values.append({"id": slot.id, "name": slot.name, "device_id": device.id if device else None,
            "occupied": sample[0].occupied if sample and fresh else None,
            "gpio": assignment.gpio if assignment else None, "fresh": bool(fresh),
            "updated_at": stamp.isoformat() if stamp else None})
    return values


def set_alert(db, device, kind, active, message):
    key = f"{device.id}:{kind}"
    meta = db.scalar(select(AlertDetails).where(AlertDetails.active_key == key))
    if active and not meta:
        alert = M.Alert(message=message)
        db.add(alert)
        db.flush()
        db.add(AlertDetails(alert_id=alert.id, device_id=device.id, kind=kind, active_key=key))
    elif not active and meta:
        meta.active_key, meta.resolved_at = None, M.now()


def acknowledge_command(item, received_at):
    with M.Sessions() as db:
        device = db.scalar(select(M.Device).where(M.Device.code == item.device_id))
        command = db.get(DeviceCommand, item.command_id)
        if (not device or not command or command.device_id != device.id or command.status in TERMINAL
                or device.status not in {"active", "provisioned"}):
            return
        if utc(command.expires_at) <= received_at:
            command.status, command.completed_at = "timed_out", received_at
            db.commit()
            return
        success = item.status == "succeeded"
        if success and command.action == "configure":
            success = item.result.get("report_interval_ms") == command.arguments.get("report_interval_ms")
            if success:
                info = details(db, device)
                info.report_interval_ms = command.arguments["report_interval_ms"]
        command.status = "acknowledged" if success else "failed"
        command.completed_at, command.result = received_at, item.result
        command.error = item.error if not success else None
        if not success and not command.error:
            command.error = "Device did not confirm the requested configuration"
        db.commit()


def receive_status(item, received_at):
    with M.Sessions() as db:
        device = db.scalar(select(M.Device).where(M.Device.code == item.device_id))
        if not device or device.status not in {"active", "provisioned", "maintenance"}:
            return
        info = details(db, device)
        # A queued will from a previous boot must not take the new boot offline.
        if item.boot_id and info.last_boot_id and item.boot_id != info.last_boot_id:
            return
        if item.state == "offline":
            info.forced_offline = True
        else:
            info.last_seen, info.forced_offline = received_at, False
        db.commit()


def runtime_tick():
    to_publish = []
    with M.Sessions() as db:
        for device in db.scalars(select(M.Device)):
            info = details(db, device)
            state = connectivity(device, info)
            if state != info.connection_state:
                if info.connection_state == "online" and state != "online":
                    for assignment in db.scalars(select(DeviceSlot).where(DeviceSlot.device_id == device.id)):
                        db.add(ParkingEvent(device_id=device.id, slot_name=assignment.slot_name,
                                            kind="unknown", occupied=None))
                info.connection_state = state
            operational = device.status in {"active", "provisioned"}
            set_alert(db, device, "device_offline", operational and state == "offline" and info.offline_alert,
                      f"Thiet bi {device.code} mat ket noi")
            device_slots = [slot for slot in slot_views(db) if slot["device_id"] == device.id]
            full = bool(device_slots) and all(slot["occupied"] is True for slot in device_slots)
            set_alert(db, device, "parking_full", full and info.full_alert,
                      f"Khu vuc cua {device.code} da het cho do")
        for command in db.scalars(select(DeviceCommand).where(DeviceCommand.status.in_(["queued", "sent"]))):
            device = db.get(M.Device, command.device_id)
            if not device or device.status not in {"active", "provisioned"}:
                command.status, command.completed_at = "cancelled", M.now()
                command.error = "Device is not enabled"
            elif utc(command.expires_at) <= M.now():
                command.status, command.completed_at = "timed_out", M.now()
                command.error = "No device acknowledgement before deadline"
                set_alert(db, device, "command_timeout", True, f"Thiet bi {device.code} khong xac nhan lenh")
            elif receiver_ready() and command.attempts < 3 and (
                    command.last_sent_at is None or (M.now() - utc(command.last_sent_at)).total_seconds() >= 2):
                command.status, command.last_sent_at = "sent", M.now()
                command.attempts += 1
                to_publish.append((device.code, {"command_id": command.id, "action": command.action,
                    "arguments": command.arguments, "expires_unix": int(utc(command.expires_at).timestamp()),
                    "boot_id": command.target_boot_id, "uptime_deadline_s": command.uptime_deadline_s}))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return
    receiver = getattr(M.app.state, "mqtt_receiver", None)
    for code, payload in to_publish:
        if receiver:
            receiver.publish_command(code, payload)
