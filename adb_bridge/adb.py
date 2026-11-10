"""Transporte: todo lo que habla con el binario `adb`.

Un `Runner` ejecuta una línea de comandos y devuelve código, salida y error. En producción es
`subprocess.run`; en las pruebas, un doble que simula el binario.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol


class Completed(Protocol):
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str], float], Completed]


def run_subprocess(args: Sequence[str], timeout: float) -> Completed:
    return subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)


# Mensajes con los que `adb` avisa de que el problema está en la conexión con el dispositivo,
# no en el comando que se ejecutó. Solo estos justifican reconectar y reintentar.
TRANSPORT_NEEDLES = (
    "device not found",
    "device '",
    "no devices/emulators found",
    "device offline",
    "device still authorizing",
    "device unauthorized",
    "connection reset",
    "error: closed",
    "failed to connect",
    "cannot connect",
    "daemon not running",
    "more than one device/emulator",
    "protocol fault",
)


def is_transport_error(text: str) -> bool:
    low = (text or "").lower()
    return any(needle in low for needle in TRANSPORT_NEEDLES)


@dataclass(frozen=True)
class ShellResult:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def transport_failed(self) -> bool:
        """El comando no llegó al dispositivo (o la conexión se cayó a medias)."""
        return not self.ok and is_transport_error(self.err or self.out)

    @property
    def message(self) -> str:
        return (self.err or self.out or "").strip()


@dataclass(frozen=True)
class Device:
    identifier: str
    state: str
    description: str = ""


class Adb:
    """Operaciones elementales sobre `adb`, cada una con su propio tiempo máximo."""

    STATE_TIMEOUT = 1.8
    CONNECT_TIMEOUT = 3.5
    DISCONNECT_TIMEOUT = 2.5
    KILL_TIMEOUT = 3.0
    START_TIMEOUT = 4.0
    WARMUP_TIMEOUT = 1.4
    INFO_TIMEOUT = 3.0

    def __init__(self, runner: Runner = run_subprocess) -> None:
        self._run = runner

    def is_device(self, adb_id: str) -> bool:
        try:
            p = self._run(["adb", "-s", adb_id, "get-state"], self.STATE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return False
        return p.returncode == 0 and p.stdout.strip() == "device"

    def connect(self, adb_id: str) -> None:
        try:
            self._run(["adb", "connect", adb_id], self.CONNECT_TIMEOUT)
        except subprocess.TimeoutExpired:
            pass

    def disconnect(self, adb_id: str) -> None:
        try:
            self._run(["adb", "disconnect", adb_id], self.DISCONNECT_TIMEOUT)
        except subprocess.TimeoutExpired:
            pass

    def restart_server(self) -> None:
        try:
            self._run(["adb", "kill-server"], self.KILL_TIMEOUT)
            self._run(["adb", "start-server"], self.START_TIMEOUT)
        except subprocess.TimeoutExpired:
            pass

    def warmup(self, adb_id: str) -> None:
        """Un `true` rápido despierta el canal antes del comando real."""
        try:
            self._run(["adb", "-s", adb_id, "shell", "true"], self.WARMUP_TIMEOUT)
        except Exception:
            pass

    def shell(self, adb_id: str, raw_cmd: str, timeout: float) -> ShellResult:
        """Ejecuta `adb shell <raw_cmd>`; con el prefijo `exec-out ` usa ese modo binario."""
        if raw_cmd.startswith("exec-out "):
            args = ["adb", "-s", adb_id, "exec-out", *shlex.split(raw_cmd[len("exec-out ") :])]
        else:
            args = ["adb", "-s", adb_id, "shell", raw_cmd]
        p = self._run(args, timeout)
        return ShellResult(p.returncode, p.stdout, p.stderr)

    def devices(self) -> list[Device]:
        """Dispositivos que el servidor ADB conoce, con su estado."""
        try:
            p = self._run(["adb", "devices", "-l"], self.INFO_TIMEOUT)
        except subprocess.TimeoutExpired:
            return []
        found: list[Device] = []
        for line in p.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            found.append(Device(parts[0], parts[1], " ".join(parts[2:])))
        return found

    def version(self) -> str | None:
        try:
            p = self._run(["adb", "version"], self.INFO_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            return None
        first = p.stdout.strip().splitlines()[:1]
        return first[0] if first else None
