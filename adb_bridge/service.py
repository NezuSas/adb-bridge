"""Lógica del puente: conexión bajo demanda, reintentos, bloqueo por dispositivo y keepalive."""

from __future__ import annotations

import logging
import random
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .adb import Adb
from .config import Settings

log = logging.getLogger("adb-bridge")

Kind = Literal["ok", "command", "transport"]


@dataclass(frozen=True)
class Outcome:
    """Resultado de un intento: salió bien, falló el comando en el dispositivo o falló la conexión."""

    kind: Kind
    output: str
    exit_code: int | None = None


class Bridge:
    def __init__(
        self,
        settings: Settings,
        adb: Adb,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.adb = adb
        self._clock = clock
        self._sleep = sleep
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._last_used: dict[str, float] = {}
        self._keepalive_stop = threading.Event()
        self._keepalive_thread: threading.Thread | None = None

    # ----- bloqueo por dispositivo -----

    def _lock_for(self, adb_id: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(adb_id)
            if lock is None:
                lock = self._locks[adb_id] = threading.Lock()
            return lock

    def _known_devices(self) -> list[str]:
        with self._locks_guard:
            return list(self._locks)

    # ----- conexión -----

    def _connect_and_wait(self, adb_id: str) -> bool:
        s = self.settings
        self.adb.connect(adb_id)
        deadline = self._clock() + max(0.3, s.connect_wait)
        while self._clock() < deadline:
            if self.adb.is_device(adb_id):
                return True
            self._sleep(s.connect_poll)
        return self.adb.is_device(adb_id)

    def _ensure_connected(self, adb_id: str) -> bool:
        return self.adb.is_device(adb_id) or self._connect_and_wait(adb_id)

    def _jitter(self, base: float, spread: float = 0.12) -> None:
        self._sleep(max(0.0, base + random.uniform(-spread, spread)))

    def _short(self, raw_cmd: str) -> str:
        """Versión recortada del comando para los registros: lo tecleado no debe quedar entero."""
        limit = self.settings.log_command_chars
        return raw_cmd if len(raw_cmd) <= limit else raw_cmd[:limit] + "..."

    # ----- un intento -----

    def _execute_once(self, adb_id: str, raw_cmd: str) -> Outcome:
        s = self.settings
        if not self._ensure_connected(adb_id):
            return Outcome("transport", f"{adb_id} not connected")
        self.adb.warmup(adb_id)
        self._jitter(0.10)

        try:
            res = self.adb.shell(adb_id, raw_cmd, s.exec_timeout)
        except subprocess.TimeoutExpired:
            return Outcome("transport", "timeout executing command")
        if res.ok:
            return Outcome("ok", res.out, 0)
        if not res.transport_failed:
            return Outcome("command", res.message or "execution failed", res.code)

        # La conexión se cayó: una reconexión inmediata y un segundo intento del mismo comando.
        if not self._connect_and_wait(adb_id):
            return Outcome("transport", "reconnect failed (device still not found)")
        self.adb.warmup(adb_id)
        self._jitter(0.12)
        try:
            again = self.adb.shell(adb_id, raw_cmd, s.exec_timeout)
        except subprocess.TimeoutExpired:
            return Outcome("transport", "timeout executing command (after reconnect)")
        if again.ok:
            return Outcome("ok", again.out, 0)
        if again.transport_failed:
            return Outcome("transport", again.message or "execution failed after reconnect")
        return Outcome("command", again.message or "execution failed", again.code)

    # ----- API del servicio -----

    def execute(self, adb_id: str, raw_cmd: str) -> dict:
        """Ejecuta hasta obtener respuesta del dispositivo.

        Un fallo de transporte se reintenta con reconexiones progresivas, dentro de un número
        máximo de intentos y de una cota de tiempo total. Un comando que el dispositivo ejecuta
        y devuelve con error se entrega tal cual, sin reintentos: reintentarlo no lo arreglaría.
        """
        s = self.settings
        start = self._clock()
        shown = self._short(raw_cmd)
        with self._lock_for(adb_id):
            self._last_used[adb_id] = time.time()
            failures = 0
            for attempt in range(1, s.max_attempts + 1):
                if (self._clock() - start) > s.max_total_exec:
                    log.error("[FAILURE-TOTALCAP] adb=%s cmd=%s attempts=%d", adb_id, shown, attempt - 1)
                    return self._error("failed by total time cap at bridge", attempt - 1)

                t0 = self._clock()
                outcome = self._execute_once(adb_id, raw_cmd)
                elapsed_ms = (self._clock() - t0) * 1000.0

                if outcome.kind == "ok":
                    log.info("[OK] adb=%s cmd=%s attempt=%d time=%.1fms", adb_id, shown, attempt, elapsed_ms)
                    return {"status": "ok", "output": outcome.output, "attempts": attempt}
                if outcome.kind == "command":
                    log.info(
                        "[COMMAND-ERROR] adb=%s cmd=%s exit=%s time=%.1fms",
                        adb_id,
                        shown,
                        outcome.exit_code,
                        elapsed_ms,
                    )
                    return self._error(outcome.output, attempt, outcome.exit_code)

                failures += 1
                log.warning(
                    "[RETRY] adb=%s cmd=%s attempt=%d reason=%s time=%.1fms",
                    adb_id,
                    shown,
                    attempt,
                    outcome.output,
                    elapsed_ms,
                )
                if failures % s.hard_reset_every == 0:
                    log.warning("[HARD RESET] kill-server -> reconnect (%s)", adb_id)
                    self.adb.restart_server()
                    self._jitter(0.30)
                    self._connect_and_wait(adb_id)
                elif failures % s.disconnect_every == 0:
                    log.warning("[SOFT RESET] disconnect -> reconnect (%s)", adb_id)
                    self.adb.disconnect(adb_id)
                    self._jitter(0.18)
                    self._connect_and_wait(adb_id)
                else:
                    self._connect_and_wait(adb_id)
                self._jitter(s.sleep_between_attempts)

            log.error("[FAILURE] adb=%s cmd=%s attempts=%d", adb_id, shown, s.max_attempts)
            return self._error(f"failed after {s.max_attempts} attempts", s.max_attempts)

    @staticmethod
    def _error(output: str, attempts: int, exit_code: int | None = None) -> dict:
        result: dict = {"status": "error", "output": output, "attempts": attempts}
        if exit_code is not None:
            result["exit_code"] = exit_code
        return result

    def state(self, adb_id: str) -> dict:
        """Comprueba que el dispositivo responde como `device`, con unos pocos reintentos suaves."""
        s = self.settings
        with self._lock_for(adb_id):
            self._last_used[adb_id] = time.time()
            for attempt in range(1, s.state_retries + 1):
                try:
                    if self._ensure_connected(adb_id):
                        self.adb.warmup(adb_id)
                        return {"status": "ok", "state": "device", "attempt": attempt}
                except subprocess.TimeoutExpired:
                    pass
                if attempt < s.state_retries:
                    self.adb.disconnect(adb_id)
                    self._jitter(0.15)
                    self._connect_and_wait(adb_id)
            return {
                "status": "error",
                "state": "unknown",
                "output": f"state unsettled after {s.state_retries} retries",
            }

    def devices(self) -> list[dict]:
        return [
            {"adb_identifier": d.identifier, "state": d.state, "description": d.description}
            for d in self.adb.devices()
        ]

    # ----- keepalive -----

    def keepalive_once(self) -> None:
        """Reconecta o despierta los dispositivos usados en la ventana reciente."""
        now = time.time()
        for adb_id in self._known_devices():
            if now - self._last_used.get(adb_id, 0.0) > self.settings.recent_window:
                continue
            with self._lock_for(adb_id):
                try:
                    if not self.adb.is_device(adb_id):
                        self._connect_and_wait(adb_id)
                    else:
                        self.adb.warmup(adb_id)
                except Exception:
                    log.debug("keepalive failed for %s", adb_id, exc_info=True)

    def _keepalive_loop(self) -> None:
        interval = max(self.settings.keepalive_interval, 1.0)
        while not self._keepalive_stop.wait(interval):
            self.keepalive_once()

    def start_keepalive(self) -> None:
        if self.settings.keepalive_interval <= 0 or self._keepalive_thread is not None:
            return
        self._keepalive_stop.clear()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, name="adb-bridge-keepalive", daemon=True
        )
        self._keepalive_thread.start()

    def stop_keepalive(self) -> None:
        if self._keepalive_thread is None:
            return
        self._keepalive_stop.set()
        self._keepalive_thread.join(timeout=2.0)
        self._keepalive_thread = None
