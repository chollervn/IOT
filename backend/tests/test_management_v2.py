from datetime import timedelta
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app import main as M
from app.broker_admin import BrokerUnavailable
from app.domain import DeviceCommand, DeviceDetails, DeviceGrant, ParkingEvent
from app.domain_service import acknowledge_command, persist_reading, runtime_tick
from app.mqtt_receiver import AckMessage, TelemetryMessage


def reading(level1=1, level2=1, **extra):
    return TelemetryMessage(device_id="esp32_01", uptime_s=10, do=level1,
        detected=level1 == 0, do2=level2, detected2=level2 == 0, **extra)


@pytest.fixture
def api(fake_broker):
    with TestClient(M.app) as client:
        published = []
        M.app.state.mqtt_receiver = SimpleNamespace(connected=True, subscribed=True,
            publish_command=lambda code, value: published.append((code, value)), stop=lambda: None)
        M.app.state.broker_admin = fake_broker
        with M.Sessions() as db:
            device = db.scalar(select(M.Device).where(M.Device.code == "esp32_01"))
            did = device.id
            for name, role in (("admin_v2", "admin"), ("operator_v2", "operator"), ("viewer_v2", "viewer"), ("stranger_v2", "viewer")):
                user = M.User(username=name, password_hash=M.hasher.hash("password-for-tests"), role=role)
                db.add(user)
                db.flush()
                if role == "operator" or name == "viewer_v2":
                    db.add(DeviceGrant(device_id=did, user_id=user.id,
                        can_control=role == "operator", can_configure=role == "operator"))
            db.commit()
        headers = {}
        for name in ("admin_v2", "operator_v2", "viewer_v2", "stranger_v2"):
            token = client.post("/auth/login", json={"username": name, "password": "password-for-tests"}).json()["access_token"]
            headers[name] = {"Authorization": "Bearer " + token}
        try:
            yield client, headers, did, published
        finally:
            M.app.state.mqtt_receiver = None


def test_scope_and_grant_revocation(api):
    client, headers, did, _ = api
    stranger = headers["stranger_v2"]
    for path in (f"/devices/{did}", "/telemetry/latest", "/telemetry", "/telemetry/statistics", "/telemetry/export.csv"):
        assert client.get(path, headers=stranger).status_code == 404
    assert client.get("/devices", headers=stranger).json() == []
    assert client.get("/parking/slots", headers=stranger).json() == []
    assert client.get("/dashboard", headers=stranger).json()["capacity"] == 0
    assert client.get("/alerts", headers=stranger).json() == []
    assert client.get("/parking/events", headers=stranger).json() == []
    assert client.get(f"/devices/{did}", headers=headers["viewer_v2"]).status_code == 200
    with M.Sessions() as db:
        viewer = db.scalar(select(M.User).where(M.User.username == "viewer_v2"))
        viewer_id = viewer.id
    assert client.delete(f"/devices/{did}/grants/{viewer_id}", headers=headers["admin_v2"]).status_code == 204
    assert client.get(f"/devices/{did}", headers=headers["viewer_v2"]).status_code == 404


def test_real_provisioning_contract_and_fail_closed(api, fake_broker):
    client, headers, _, _ = api
    admin = headers["admin_v2"]
    response = client.post("/devices", headers=admin, json={"code": "new_node", "name": "New node"})
    did = response.json()["id"]
    assert client.patch(f"/devices/{did}", headers=admin, json={"status": "active"}).status_code == 409
    M.app.state.broker_admin = None
    assert client.post(f"/devices/{did}/provision", headers=admin).status_code == 503
    assert client.get(f"/devices/{did}", headers=admin).json()["status"] == "registered"
    M.app.state.broker_admin = fake_broker
    response = client.post(f"/devices/{did}/provision", headers=admin)
    assert response.status_code == 200
    password = response.json()["mqtt_password"]
    assert fake_broker.clients["new_node"]["password"] == password
    assert "mqtt_password" not in client.get(f"/devices/{did}", headers=admin).json()
    assert password not in str(client.get("/audit-logs", headers=admin).json())
    assert client.patch(f"/devices/{did}", headers=admin, json={"status": "active"}).status_code == 200
    assert client.patch(f"/devices/{did}", headers=admin, json={"status": "revoked"}).status_code == 200
    assert fake_broker.clients["new_node"]["enabled"] is False
    assert client.patch(f"/devices/{did}", headers=admin, json={"status": "decommissioned"}).status_code == 200
    assert client.patch(f"/devices/{did}", headers=admin, json={"status": "provisioned"}).status_code == 409


def test_broker_failure_does_not_claim_revocation_succeeded(api):
    client, headers, did, _ = api
    def fail(*args):
        raise BrokerUnavailable("test outage")
    M.app.state.broker_admin = SimpleNamespace(set_enabled=fail)
    assert client.patch(f"/devices/{did}", headers=headers["admin_v2"], json={"status": "revoked"}).status_code == 503
    assert client.get(f"/devices/{did}", headers=headers["admin_v2"]).json()["status"] == "active"


def test_deduplication_out_of_order_and_old_boot(api):
    _, _, _, _ = api
    assert persist_reading(reading(boot_id="11111111", seq=1), M.now())
    assert not persist_reading(reading(0, 0, boot_id="11111111", seq=1), M.now())
    assert not persist_reading(reading(0, 0, boot_id="11111111", seq=0), M.now())
    assert persist_reading(reading(0, 1, boot_id="11111111", seq=2), M.now())
    assert persist_reading(reading(1, 0, boot_id="22222222", seq=0), M.now())
    assert not persist_reading(reading(0, 0, boot_id="11111111", seq=3), M.now())
    with M.Sessions() as db:
        assert db.scalar(select(func.count()).select_from(M.Telemetry)) == 3


def test_commands_require_scope_and_device_ack(api):
    client, headers, did, published = api
    persist_reading(reading(boot_id="11111111", seq=1), M.now())
    body = {"action": "configure", "report_interval_ms": 2000, "idempotency_key": "configure-1"}
    assert client.post(f"/devices/{did}/commands", headers=headers["viewer_v2"], json=body).status_code == 403
    response = client.post(f"/devices/{did}/commands", headers=headers["operator_v2"], json=body)
    assert response.status_code == 202
    command_id = response.json()["id"]
    assert response.json()["status"] == "queued"
    assert client.post(f"/devices/{did}/commands", headers=headers["operator_v2"], json=body).json()["id"] == command_id
    assert client.post(f"/devices/{did}/commands", headers=headers["operator_v2"], json={**body, "report_interval_ms": 3000}).status_code == 409
    runtime_tick()
    assert len(published) == 1
    assert published[0][1]["boot_id"] == "11111111"
    assert client.get(f"/commands/{command_id}", headers=headers["viewer_v2"]).json()["status"] == "sent"
    acknowledge_command(AckMessage(device_id="other", command_id=command_id, status="succeeded",
                                   result={"report_interval_ms": 2000}), M.now())
    assert client.get(f"/commands/{command_id}", headers=headers["operator_v2"]).json()["status"] == "sent"
    acknowledge_command(AckMessage(device_id="esp32_01", command_id=command_id, status="succeeded",
                                   result={"report_interval_ms": 2000}), M.now())
    assert client.get(f"/commands/{command_id}", headers=headers["operator_v2"]).json()["status"] == "acknowledged"
    assert client.get(f"/devices/{did}/configuration", headers=headers["operator_v2"]).json()["report_interval_ms"] == 2000
    acknowledge_command(AckMessage(device_id="esp32_01", command_id=command_id, status="failed"), M.now())
    assert client.get(f"/commands/{command_id}", headers=headers["operator_v2"]).json()["status"] == "acknowledged"


def test_command_timeout_and_no_late_success(api):
    client, headers, did, _ = api
    persist_reading(reading(boot_id="11111111", seq=1), M.now())
    response = client.post(f"/devices/{did}/commands", headers=headers["admin_v2"], json={"action": "ping"})
    command_id = response.json()["id"]
    with M.Sessions() as db:
        db.get(DeviceCommand, command_id).expires_at = M.now() - timedelta(seconds=1)
        db.commit()
    runtime_tick()
    acknowledge_command(AckMessage(device_id="esp32_01", command_id=command_id, status="succeeded"), M.now())
    assert client.get(f"/commands/{command_id}", headers=headers["admin_v2"]).json()["status"] == "timed_out"
    assert any(alert["kind"] == "command_timeout" for alert in client.get("/alerts", headers=headers["admin_v2"]).json())


def test_full_offline_alerts_latched_and_scoped(api):
    client, headers, did, _ = api
    persist_reading(reading(0, 0), M.now())
    runtime_tick(); runtime_tick()
    alerts = client.get("/alerts?active_only=true", headers=headers["operator_v2"]).json()
    full = [alert for alert in alerts if alert["kind"] == "parking_full"]
    assert len(full) == 1
    aid = full[0]["id"]
    assert client.post(f"/alerts/{aid}/acknowledge", headers=headers["viewer_v2"]).status_code == 403
    assert client.post(f"/alerts/{aid}/acknowledge", headers=headers["operator_v2"]).status_code == 200
    persist_reading(reading(1, 0), M.now())
    runtime_tick()
    resolved = [alert for alert in client.get("/alerts", headers=headers["operator_v2"]).json() if alert["id"] == aid][0]
    assert not resolved["active"] and resolved["resolved_at"] and resolved["acknowledged"]
    with M.Sessions() as db:
        db.get(DeviceDetails, did).last_seen = M.now() - timedelta(seconds=20)
        db.commit()
    runtime_tick(); runtime_tick()
    assert client.get("/dashboard", headers=headers["operator_v2"]).json()["unknown"] == 2
    offline = [alert for alert in client.get("/alerts?active_only=true", headers=headers["operator_v2"]).json() if alert["kind"] == "device_offline"]
    assert len(offline) == 1
    persist_reading(reading(1, 1), M.now())
    runtime_tick()
    assert not [alert for alert in client.get("/alerts?active_only=true", headers=headers["operator_v2"]).json() if alert["kind"] == "device_offline"]
    assert client.get("/alerts", headers=headers["stranger_v2"]).json() == []


def test_time_search_export_statistics_and_events(api):
    client, headers, _, _ = api
    persist_reading(reading(0, 1), M.now() - timedelta(hours=2))
    persist_reading(reading(1, 0), M.now())
    viewer = headers["viewer_v2"]
    from_at = (M.now() - timedelta(hours=1)).isoformat()
    response = client.get("/telemetry", headers=viewer, params={"from_at": from_at})
    assert len(response.json()) == 1
    assert client.get("/telemetry", headers=viewer, params={"from_at": "2026-01-01T00:00:00"}).status_code == 422
    assert client.get("/telemetry", headers=viewer, params={"from_at": M.now().isoformat(), "to_at": from_at}).status_code == 422
    csv = client.get("/telemetry/export.csv", headers=viewer, params={"from_at": from_at})
    assert csv.status_code == 200 and len(csv.text.strip().splitlines()) == 3
    stats = client.get("/telemetry/statistics", headers=viewer).json()
    assert stats["basis"] == "sample_count_not_parking_duration"
    assert sum(bucket["samples"] for bucket in stats["buckets"]) == 4
    assert client.get("/parking/events", headers=viewer).json()
