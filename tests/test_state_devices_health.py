"""`/adb/state`, `/adb/devices`, `/health` y `/`."""

from __future__ import annotations

from conftest import DEVICE, FAST, make_client


def test_state_ok_when_device_answers(client):
    r = client.post("/adb/state", json={"adb_identifier": DEVICE})

    body = r.json()
    assert body == {"status": "ok", "state": "device", "attempt": 1, "instance": body["instance"]}


def test_state_accepts_legacy_empty_command_field(client):
    r = client.post("/adb/state", json={"adb_identifier": DEVICE, "command": ""})
    assert r.json()["state"] == "device"


def test_state_unknown_when_device_never_settles(fake_adb, clock):
    fake_adb.reachable.clear()
    fake_adb.connected.clear()
    client = make_client(fake_adb, clock)

    r = client.post("/adb/state", json={"adb_identifier": DEVICE})

    body = r.json()
    assert body["status"] == "error"
    assert body["state"] == "unknown"
    assert body["output"] == f"state unsettled after {FAST.state_retries} retries"
    assert fake_adb.count("disconnect") == FAST.state_retries - 1


def test_devices_lists_what_adb_knows(client, fake_adb):
    fake_adb.devices_output = (
        "List of devices attached\n"
        f"{DEVICE}\tdevice product:tv model:Pantalla device:p1 transport_id:3\n"
        "192.168.1.51:5555\toffline transport_id:4\n"
        "\n"
    )

    r = client.get("/adb/devices")

    assert r.status_code == 200
    devices = r.json()["devices"]
    assert devices[0]["adb_identifier"] == DEVICE
    assert devices[0]["state"] == "device"
    assert "model:Pantalla" in devices[0]["description"]
    assert devices[1] == {
        "adb_identifier": "192.168.1.51:5555",
        "state": "offline",
        "description": "transport_id:4",
    }


def test_health_reports_version_adb_and_auth_mode(client):
    r = client.get("/health")

    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["adb"] == "Android Debug Bridge version 1.0.41"
    assert body["auth"] is False
    assert body["instance"]


def test_root_keeps_plain_text_ok(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.text.startswith("OK (")
