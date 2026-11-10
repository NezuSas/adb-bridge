"""`POST /adb/execute`: reintentos solo ante fallos de conexión, nunca ante errores del comando."""

from __future__ import annotations

from conftest import DEVICE, FAST, Completed, make_client, timeout_expired


def test_command_ok_first_attempt(client, fake_adb):
    fake_adb.shell_script[DEVICE] = [Completed(0, "Awake\n")]

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "dumpsys power"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["output"] == "Awake\n"
    assert body["attempts"] == 1
    assert "exit_code" not in body
    assert body["instance"]
    assert fake_adb.shell_calls(DEVICE) == [["adb", "-s", DEVICE, "shell", "dumpsys power"]]


def test_command_failure_is_returned_without_retrying(client, fake_adb):
    fake_adb.shell_script[DEVICE] = [Completed(1, "", "Error: Activity class {x/y} does not exist.\n")]

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "am start -n x/y"})

    body = r.json()
    assert body["status"] == "error"
    assert body["exit_code"] == 1
    assert body["attempts"] == 1
    assert "does not exist" in body["output"]
    assert len(fake_adb.shell_calls(DEVICE)) == 1
    assert fake_adb.count("kill-server") == 0


def test_transport_error_reconnects_and_retries_same_command(client, fake_adb):
    fake_adb.shell_script[DEVICE] = [
        Completed(1, "", f"error: device '{DEVICE}' not found\n"),
        Completed(0, "done\n"),
    ]

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "input keyevent 26"})

    body = r.json()
    assert body["status"] == "ok"
    assert body["output"] == "done\n"
    assert body["attempts"] == 1
    assert len(fake_adb.shell_calls(DEVICE)) == 2
    assert fake_adb.count("connect") >= 1


def test_timeout_counts_as_transport_and_is_retried(client, fake_adb):
    fake_adb.shell_script[DEVICE] = [timeout_expired(), timeout_expired(), Completed(0, "late\n")]

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "sleep 5"})

    body = r.json()
    assert body["status"] == "ok"
    assert body["output"] == "late\n"
    assert body["attempts"] == 3


def test_unreachable_device_gives_up_after_max_attempts_with_resets(fake_adb, clock):
    fake_adb.reachable.clear()
    fake_adb.connected.clear()
    client = make_client(fake_adb, clock)

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "true"})

    body = r.json()
    assert body["status"] == "error"
    assert body["output"] == f"failed after {FAST.max_attempts} attempts"
    assert body["attempts"] == FAST.max_attempts
    assert fake_adb.count("disconnect") >= 1  # reinicio suave cada 2 fallos
    assert fake_adb.count("kill-server") >= 1  # reinicio duro cada 3 fallos


def test_total_time_cap_stops_the_loop(fake_adb, clock):
    fake_adb.reachable.clear()
    fake_adb.connected.clear()
    slow = FAST.__class__(
        **{**FAST.__dict__, "max_attempts": 100, "max_total_exec": 2.0, "connect_wait": 1.5}
    )
    client = make_client(fake_adb, clock, slow)

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "true"})

    body = r.json()
    assert body["status"] == "error"
    assert body["output"] == "failed by total time cap at bridge"
    assert body["attempts"] < 100


def test_exec_out_prefix_uses_binary_mode(client, fake_adb):
    fake_adb.shell_script[DEVICE] = [Completed(0, "PNG")]

    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": "exec-out screencap -p"})

    assert r.json()["status"] == "ok"
    assert ["adb", "-s", DEVICE, "exec-out", "screencap", "-p"] in fake_adb.calls


def test_empty_command_is_rejected(client):
    r = client.post("/adb/execute", json={"adb_identifier": DEVICE, "command": ""})
    assert r.status_code == 422
