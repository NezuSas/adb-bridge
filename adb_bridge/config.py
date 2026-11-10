"""Ajustes del puente.

Los tiempos y los límites son fijos a propósito: el comportamiento es el mismo en todas las
instalaciones. Solo la seguridad (token y lista de dispositivos) se lee del entorno, porque
depende de cada red.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # Ejecución de comandos
    exec_timeout: float = 8.0  # segundos por intento de `adb shell`
    connect_wait: float = 3.0  # cuánto se espera a que el dispositivo responda tras `adb connect`
    connect_poll: float = 0.2  # cada cuánto se consulta el estado mientras se espera
    max_attempts: int = 24  # intentos por petición cuando el fallo es de transporte
    hard_reset_every: int = 6  # cada cuántos fallos se reinicia el servidor ADB
    disconnect_every: int = 3  # cada cuántos fallos se desconecta y reconecta
    sleep_between_attempts: float = 0.35
    max_total_exec: float = 30.0  # cota dura por petición, en segundos
    state_retries: int = 4  # intentos de `/adb/state`

    # Keepalive de los dispositivos usados recientemente
    keepalive_interval: float = 15.0  # 0 desactiva el hilo
    recent_window: float = 600.0

    # Seguridad (opcional, desde el entorno)
    token: str | None = None
    allowed_devices: frozenset[str] = field(default_factory=frozenset)

    # Registros
    log_command_chars: int = 80


ENV_TOKEN = "ADB_BRIDGE_TOKEN"
ENV_ALLOWED_DEVICES = "ADB_BRIDGE_ALLOWED_DEVICES"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Construye los ajustes a partir del entorno (solo token y lista de dispositivos)."""
    source = os.environ if env is None else env
    token = (source.get(ENV_TOKEN) or "").strip() or None
    allowed = frozenset(
        item.strip() for item in (source.get(ENV_ALLOWED_DEVICES) or "").split(",") if item.strip()
    )
    return Settings(token=token, allowed_devices=allowed)
