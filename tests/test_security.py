"""Token opcional, lista de dispositivos permitidos y validación del identificador."""

from __future__ import annotations

import pytest
from conftest import DEVICE, FAST, make_client

from adb_bridge.config import Settings, load_settings

WITH_TOKEN = Settings(**{**FAST.__dict__, "token": "s3cret"})
WITH_ALLOWLIST = Settings(**{**FAST.__dict__, "allowed_devices": frozenset({DEVICE})})


def test_without_token_configured_requests_pass(client):
    assert client.post("/adb/state", json={"adb_identifier": DEVICE}).status_code == 200


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic s3cret"}]
)
def test_token_required_when_configured(fake_adb, clock, headers):
    client = make_client(fake_adb, clock, WITH_TOKEN)

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "true"}, headers=headers)

    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert fake_adb.shell_calls(DEVICE) == []


def test_token_accepted(fake_adb, clock):
    client = make_client(fake_adb, clock, WITH_TOKEN)
    headers = {"Authorization": "Bearer s3cret"}

    assert (
        client.post(
            "/adb/execute", json={"adb_identifier": DEVICE, "command": "true"}, headers=headers
        ).status_code
        == 200
    )
    assert client.get("/adb/devices", headers=headers).status_code == 200
    assert client.get("/health").status_code == 200  # la salud nunca pide token
    assert client.get("/health").json()["auth"] is True


def test_allowlist_blocks_other_devices(fake_adb, clock):
    fake_adb.reachable.add("192.168.1.99:5555")
    fake_adb.connected.add("192.168.1.99:5555")
    client = make_client(fake_adb, clock, WITH_ALLOWLIST)

    denied = client.post("/adb/execute", json={"adb_identifier": "192.168.1.99:5555", "command": "true"})
    allowed = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "true"})

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert fake_adb.shell_calls("192.168.1.99:5555") == []


@pytest.mark.parametrize(
    "identifier",
    [
        "pantalla",
        "192.168.1.50",
        "192.168.1.300:5555",
        "192.168.1.50:0",
        "192.168.1.50:70000",
        ":5555",
        "a b:5555",
    ],
)
def test_invalid_identifier_is_rejected_before_calling_adb(client, fake_adb, identifier):
    r = client.post("/adb/execute", json={"adb_identifier": identifier, "command": "true"})

    assert r.status_code == 422
    assert fake_adb.calls == []


@pytest.mark.parametrize("identifier", [DEVICE, "pantalla-sala.lan:5555", " 192.168.1.50:5555 "])
def test_valid_identifiers(fake_adb, clock, identifier):
    fake_adb.reachable.add(identifier.strip())
    fake_adb.connected.add(identifier.strip())
    client = make_client(fake_adb, clock)

    assert client.post("/adb/state", json={"adb_identifier": identifier}).status_code == 200


def test_settings_from_environment():
    s = load_settings(
        {"ADB_BRIDGE_TOKEN": " abc ", "ADB_BRIDGE_ALLOWED_DEVICES": "192.168.1.50:5555, 192.168.1.51:5555 ,"}
    )
    assert s.token == "abc"
    assert s.allowed_devices == frozenset({"192.168.1.50:5555", "192.168.1.51:5555"})
    assert s.max_attempts == 24  # los tiempos no se leen del entorno

    empty = load_settings({})
    assert empty.token is None
    assert empty.allowed_devices == frozenset()


def test_main_module_exposes_the_app():
    import main

    assert main.app.title == "ADB Bridge"
