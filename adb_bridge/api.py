"""Capa HTTP: validación de entrada, autenticación opcional y rutas."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .adb import Adb
from .config import Settings, load_settings
from .service import Bridge

log = logging.getLogger("adb-bridge")

_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


def validate_identifier(value: str) -> str:
    """Acepta `IP:PUERTO` (o `host:PUERTO`); rechaza cualquier otra cosa antes de llegar a `adb`."""
    value = value.strip()
    host, sep, port = value.rpartition(":")
    if not sep or not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("adb_identifier must look like IP:PORT, for example 192.168.1.50:5555")
    try:
        ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        looks_numeric = host.replace(".", "").isdigit()
        if looks_numeric or not _HOST_RE.match(host):
            raise ValueError("adb_identifier host must be an IPv4 address or a hostname") from None
    return value


class CommandRequest(BaseModel):
    adb_identifier: str = Field(description="Dispositivo, como IP:PUERTO", examples=["192.168.1.50:5555"])
    command: str = Field(min_length=1, description="Lo que va tras `adb shell`")

    @field_validator("adb_identifier")
    @classmethod
    def _check_identifier(cls, value: str) -> str:
        return validate_identifier(value)


class StateRequest(BaseModel):
    adb_identifier: str = Field(examples=["192.168.1.50:5555"])
    command: str = Field(default="", description="Se ignora; se admite por compatibilidad")

    @field_validator("adb_identifier")
    @classmethod
    def _check_identifier(cls, value: str) -> str:
        return validate_identifier(value)


class CommandResult(BaseModel):
    status: str
    output: str
    attempts: int
    exit_code: int | None = None
    instance: str


class StateResult(BaseModel):
    status: str
    state: str
    attempt: int | None = None
    output: str | None = None
    instance: str


class DeviceInfo(BaseModel):
    adb_identifier: str
    state: str
    description: str = ""


class DevicesResult(BaseModel):
    devices: list[DeviceInfo]
    instance: str


class HealthResult(BaseModel):
    status: str
    version: str
    adb: str | None
    auth: bool
    instance: str


def _instance() -> str:
    return socket.gethostname()[:12]


def create_app(
    settings: Settings | None = None,
    adb: Adb | None = None,
    bridge: Bridge | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    bridge = bridge or Bridge(settings, adb or Adb())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        bridge.start_keepalive()
        if settings.token is None:
            log.warning("ADB_BRIDGE_TOKEN is not set: anyone who reaches this port can run commands")
        try:
            yield
        finally:
            bridge.stop_keepalive()

    app = FastAPI(
        title="ADB Bridge",
        version=__version__,
        description="Ejecuta comandos ADB sobre dispositivos Android de la red local.",
        lifespan=lifespan,
    )
    app.state.bridge = bridge
    app.state.settings = settings

    def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
        if settings.token is None:
            return
        scheme, _, credential = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or credential.strip() != settings.token:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def require_allowed(adb_id: str) -> None:
        if settings.allowed_devices and adb_id not in settings.allowed_devices:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=f"{adb_id} is not in the allowed devices list"
            )

    auth = Depends(require_token)

    @app.get("/", response_class=PlainTextResponse)
    def root() -> str:
        return f"OK ({_instance()})"

    @app.get("/health", response_model=HealthResult)
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "adb": bridge.adb.version(),
            "auth": settings.token is not None,
            "instance": _instance(),
        }

    @app.get("/adb/devices", response_model=DevicesResult, dependencies=[auth])
    def adb_devices() -> dict:
        return {"devices": bridge.devices(), "instance": _instance()}

    @app.post(
        "/adb/execute",
        response_model=CommandResult,
        response_model_exclude_none=True,
        dependencies=[auth],
    )
    def adb_execute(req: CommandRequest) -> dict:
        require_allowed(req.adb_identifier)
        result = bridge.execute(req.adb_identifier, req.command)
        result["instance"] = _instance()
        return result

    @app.post(
        "/adb/state",
        response_model=StateResult,
        response_model_exclude_none=True,
        dependencies=[auth],
    )
    def adb_state(req: StateRequest) -> dict:
        require_allowed(req.adb_identifier)
        result = bridge.state(req.adb_identifier)
        result["instance"] = _instance()
        return result

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
app = create_app()
