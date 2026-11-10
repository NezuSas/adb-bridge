"""Un `adb` simulado y una aplicación con tiempos a cero, para probar el puente sin dispositivos."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from adb_bridge.adb import Adb
from adb_bridge.api import create_app
from adb_bridge.config import Settings
from adb_bridge.service import Bridge


@dataclass
class Completed:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class FakeAdb:
    """Simula el binario `adb`.

    - `reachable`: dispositivos a los que `adb connect` consigue llegar.
    - `connected`: dispositivos que ya responden `device`.
    - `shell_script`: respuestas en orden para `adb shell` de cada dispositivo; agotadas, responde ok.
    - `calls`: todas las líneas de comandos ejecutadas, para afirmar sobre ellas.
    """

    reachable: set[str] = field(default_factory=set)
    connected: set[str] = field(default_factory=set)
    shell_script: dict[str, list[Completed | Exception]] = field(default_factory=dict)
    devices_output: str = "List of devices attached\n"
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, args: Sequence[str], timeout: float) -> Completed:
        args = list(args)
        self.calls.append(args)
        op = args[1] if args[1] != "-s" else args[3]
        if op == "connect":
            target = args[2]
            if target in self.reachable:
                self.connected.add(target)
                return Completed(0, f"connected to {target}\n")
            return Completed(1, "", f"failed to connect to '{target}'\n")
        if op == "disconnect":
            self.connected.discard(args[2])
            return Completed(0, f"disconnected {args[2]}\n")
        if op in ("kill-server", "start-server"):
            return Completed(0)
        if op == "version":
            return Completed(0, "Android Debug Bridge version 1.0.41\nVersion 34.0.4\n")
        if op == "devices":
            return Completed(0, self.devices_output)
        target = args[2]
        if op == "get-state":
            if target in self.connected:
                return Completed(0, "device\n")
            return Completed(1, "", "error: device offline\n")
        if op in ("shell", "exec-out"):
            if target not in self.connected:
                return Completed(1, "", f"error: device '{target}' not found\n")
            if args[4:] == ["true"]:
                return Completed(0)
            script = self.shell_script.get(target) or []
            if script:
                nxt = script.pop(0)
                if isinstance(nxt, Exception):
                    raise nxt
                return nxt
            return Completed(0, "ok\n")
        raise AssertionError(f"comando no simulado: {args}")

    def shell_calls(self, target: str) -> list[list[str]]:
        return [c for c in self.calls if c[:4] == ["adb", "-s", target, "shell"] and c[4:] != ["true"]]

    def count(self, op: str) -> int:
        return sum(1 for c in self.calls if op in c[1:3])


FAST = Settings(
    exec_timeout=1.0,
    connect_wait=0.3,
    connect_poll=0.1,
    max_attempts=4,
    hard_reset_every=3,
    disconnect_every=2,
    sleep_between_attempts=0.0,
    max_total_exec=30.0,
    state_retries=2,
    keepalive_interval=0.0,
)

DEVICE = "192.168.1.50:5555"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_adb() -> FakeAdb:
    return FakeAdb(reachable={DEVICE}, connected={DEVICE})


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_client(fake_adb: FakeAdb, clock: FakeClock, settings: Settings = FAST) -> TestClient:
    bridge = Bridge(settings, Adb(fake_adb), clock=clock, sleep=clock.sleep)
    return TestClient(create_app(settings=settings, bridge=bridge))


@pytest.fixture
def client(fake_adb: FakeAdb, clock: FakeClock) -> TestClient:
    return make_client(fake_adb, clock)


def timeout_expired() -> subprocess.TimeoutExpired:
    return subprocess.TimeoutExpired(cmd="adb", timeout=1.0)
