from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import subprocess
import shlex
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Dict
import time
import random
import logging
import socket

# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("adb-bridge")

app = FastAPI()

class ADBCommandRequest(BaseModel):
    adb_identifier: str  # "IP:PUERTO"
    command: str

# -------- Config fija (sin ENV) --------
POOL_WORKERS = 8
EXEC_TIMEOUT_DEFAULT = 8.0      # antes 6.0 -> más aire a comandos “largos”
CONNECT_WAIT_SEC = 3.0          # antes 1.8 -> redes más lentas / wake-up del daemon
CONNECT_POLL_SEC = 0.20
KEEPALIVE_SEC = 15.0
RECENT_WINDOW_SEC = 600

# Reintentos agresivos hasta lograr OK (con salvaguardas)
UNTIL_OK_MAX_ATTEMPTS = 24
HARD_RESET_EVERY = 6
DISCONNECT_EVERY = 3
SLEEP_BETWEEN_ATTEMPTS = 0.35   # antes 0.25 -> menos martilleo y más tiempo a reconectar
MAX_TOTAL_EXEC_SEC = 30.0       # antes 25.0 -> cota dura un poco mayor

# Reintentos cortos para /adb/state (para evitar ventanas “frías”)
STATE_RETRIES = 4

# -------- Infra --------
pool = ThreadPoolExecutor(max_workers=POOL_WORKERS)
_device_locks: Dict[str, threading.Lock] = {}
_global_lock = threading.Lock()
_last_used_ts: Dict[str, float] = {}

def _get_lock(adb_id: str) -> threading.Lock:
    with _global_lock:
        if adb_id not in _device_locks:
            _device_locks[adb_id] = threading.Lock()
        return _device_locks[adb_id]

def _run(args: list[str], timeout: float = 3.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

def _is_device(adb_id: str) -> bool:
    try:
        p = _run(["adb", "-s", adb_id, "get-state"], timeout=1.8)  # antes 1.6 -> 1.8
        return p.returncode == 0 and p.stdout.strip() == "device"
    except subprocess.TimeoutExpired:
        return False

def _connect_once(adb_id: str) -> None:
    try:
        _run(["adb", "connect", adb_id], timeout=3.5)  # antes 2.5 -> 3.5
    except subprocess.TimeoutExpired:
        pass

def _disconnect_once(adb_id: str) -> None:
    try:
        _run(["adb", "disconnect", adb_id], timeout=2.5)  # antes 2.0 -> 2.5
    except subprocess.TimeoutExpired:
        pass

def _kill_server() -> None:
    try:
        _run(["adb", "kill-server"], timeout=3.0)   # antes 2.0 -> 3.0
        _run(["adb", "start-server"], timeout=4.0)  # antes 3.0 -> 4.0
    except subprocess.TimeoutExpired:
        pass

def _connect_and_wait(adb_id: str, wait_s: float) -> bool:
    _connect_once(adb_id)
    deadline = time.time() + max(0.3, wait_s)
    while time.time() < deadline:
        if _is_device(adb_id):
            return True
        time.sleep(CONNECT_POLL_SEC)
    return _is_device(adb_id)

def _ensure_connected(adb_id: str) -> bool:
    return _is_device(adb_id) or _connect_and_wait(adb_id, CONNECT_WAIT_SEC)

def _looks_transport_error(stderr_out: str, retcode: int) -> bool:
    s = (stderr_out or "").lower()
    needles = (
        "device not found", "device '", "no devices/emulators found",
        "offline", "connection reset", "closed", "failed to connect",
        "cannot connect", "daemon not running", "more than one device/emulator",
        "timeout"
    )
    return any(n in s for n in needles) or retcode in (1, 255)

def _exec_shell(adb_id: str, raw_cmd: str, timeout: float) -> tuple[int, str, str]:
    if raw_cmd.startswith("exec-out "):
        real = raw_cmd[len("exec-out "):]
        args = ["adb", "-s", adb_id, "exec-out", *shlex.split(real)]
    else:
        args = ["adb", "-s", adb_id, "shell", raw_cmd]
    p = _run(args, timeout=timeout)
    return p.returncode, p.stdout, p.stderr

def _warmup(adb_id: str) -> None:
    try:
        _run(["adb", "-s", adb_id, "shell", "true"], timeout=1.4)  # antes 1.2 -> 1.4
    except Exception:
        pass

def _jitter_sleep(base: float, spread: float = 0.12) -> None:
    time.sleep(max(0, base + random.uniform(-spread, spread)))

def _exec_one(adb_id: str, raw_cmd: str, timeout: float) -> dict:
    """Ejecuta una sola vez con reconnect suave previo."""
    if not _ensure_connected(adb_id):
        return {"status": "error", "output": f"{adb_id} not connected"}
    _warmup(adb_id)
    _jitter_sleep(0.10)  # antes 0.08 -> 0.10

    try:
        code, out, err = _exec_shell(adb_id, raw_cmd, timeout)
    except subprocess.TimeoutExpired:
        return {"status": "error", "output": "timeout executing command"}

    if code == 0:
        return {"status": "ok", "output": out}

    if _looks_transport_error(err or out, code):
        if _connect_and_wait(adb_id, CONNECT_WAIT_SEC):
            _warmup(adb_id)
            _jitter_sleep(0.12)  # antes 0.10 -> 0.12
            try:
                code2, out2, err2 = _exec_shell(adb_id, raw_cmd, timeout)
            except subprocess.TimeoutExpired:
                return {"status": "error", "output": "timeout executing command (after reconnect#1)"}
            if code2 == 0:
                return {"status": "ok", "output": out2}
            return {"status": "error", "output": (err2 or out2 or "execution failed after reconnect#1")}
        return {"status": "error", "output": "reconnect failed (device still not found)"}

    return {"status": "error", "output": (err or out or "execution failed")}

def _exec_until_ok(adb_id: str, raw_cmd: str, timeout: float = EXEC_TIMEOUT_DEFAULT) -> dict:
    """
    BUCLE HASTA OK (con salvaguarda de intentos y cota de tiempo total).
    Reseteos progresivos: disconnect/reconnect y kill-server/start-server.
    """
    lock = _get_lock(adb_id)
    start = time.monotonic()
    with lock:
        _last_used_ts[adb_id] = time.time()
        failures = 0

        for attempt in range(1, UNTIL_OK_MAX_ATTEMPTS + 1):
            # Cota total antes de cada intento
            if (time.monotonic() - start) > MAX_TOTAL_EXEC_SEC:
                total_ms = (time.monotonic() - start) * 1000.0
                log.error("[FAILURE-TOTALCAP] adb=%s cmd=%s total=%.1fms", adb_id, raw_cmd, total_ms)
                return {"status": "error", "output": "failed by total time cap at bridge"}

            t0 = time.monotonic()
            res = _exec_one(adb_id, raw_cmd, timeout)
            elapsed_one = (time.monotonic() - t0) * 1000.0

            if res.get("status") == "ok":
                total_ms = (time.monotonic() - start) * 1000.0
                log.info("[OK] adb=%s cmd=%s attempt=%d time=%.1fms total=%.1fms",
                         adb_id, raw_cmd, attempt, elapsed_one, total_ms)
                return res

            failures += 1
            out = (res.get("output") or "").strip()
            log.warning("[RETRY] adb=%s cmd=%s attempt=%d reason=%s time=%.1fms",
                        adb_id, raw_cmd, attempt, out, elapsed_one)

            # Refuerzo progresivo
            low = out.lower()
            transportish = any(x in low for x in (
                "device not found", "device '", "no devices/emulators found",
                "offline", "connection reset", "closed", "failed to connect",
                "cannot connect", "daemon not running", "more than one device/emulator", "timeout"
            ))

            if failures % HARD_RESET_EVERY == 0:
                log.warning("[HARD RESET] kill-server -> reconnect (%s)", adb_id)
                _kill_server()
                _jitter_sleep(0.30)  # antes 0.25 -> 0.30
                _connect_and_wait(adb_id, CONNECT_WAIT_SEC)

            elif failures % DISCONNECT_EVERY == 0:
                log.warning("[SOFT RESET] disconnect -> reconnect (%s)", adb_id)
                _disconnect_once(adb_id)
                _jitter_sleep(0.18)  # antes 0.15 -> 0.18
                _connect_and_wait(adb_id, CONNECT_WAIT_SEC)

            elif transportish:
                _connect_and_wait(adb_id, CONNECT_WAIT_SEC)

            _jitter_sleep(SLEEP_BETWEEN_ATTEMPTS)

        total_ms = (time.monotonic() - start) * 1000.0
        log.error("[FAILURE] adb=%s cmd=%s attempts=%d total=%.1fms",
                  adb_id, raw_cmd, UNTIL_OK_MAX_ATTEMPTS, total_ms)
        return {"status": "error", "output": f"failed after {UNTIL_OK_MAX_ATTEMPTS} attempts"}

# -------- Keep-alive opcional --------
def _keepalive_loop():
    while True:
        time.sleep(max(KEEPALIVE_SEC, 1.0))
        if KEEPALIVE_SEC <= 0:
            continue
        now = time.time()
        with _global_lock:
            ids = list(_device_locks.keys())
        for adb_id in ids:
            last = _last_used_ts.get(adb_id, 0)
            if now - last > RECENT_WINDOW_SEC:
                continue
            lock = _get_lock(adb_id)
            with lock:
                try:
                    if not _is_device(adb_id):
                        _connect_and_wait(adb_id, CONNECT_WAIT_SEC)
                    else:
                        _warmup(adb_id)
                except Exception:
                    pass

threading.Thread(target=_keepalive_loop, daemon=True).start()

# -------- Endpoints --------
@app.get("/", response_class=PlainTextResponse)
def root():
    return f"OK ({socket.gethostname()[:12]})"

@app.post("/adb/execute")
def adb_execute(req: ADBCommandRequest):
    # Bucle until_ok (bloquea aquí, pero con salvaguardas)
    fut = pool.submit(_exec_until_ok, req.adb_identifier, req.command, EXEC_TIMEOUT_DEFAULT)
    try:
        res = fut.result()  # sin timeout explícito; el loop tiene cota total
        res.setdefault("instance", socket.gethostname()[:12])
        return res
    except Exception as e:
        log.exception("adb_execute exception")
        return {"status": "error", "output": str(e), "instance": socket.gethostname()[:12]}

@app.post("/adb/state")
def adb_state(req: ADBCommandRequest):
    lock = _get_lock(req.adb_identifier)
    with lock:
        # Pequeño bucle de asentamiento: intenta conectar y validar hasta STATE_RETRIES veces
        for attempt in range(1, STATE_RETRIES + 1):
            try:
                ok = _ensure_connected(req.adb_identifier)
                if ok:
                    _warmup(req.adb_identifier)
                    return {
                        "status": "ok",
                        "state": "device",
                        "instance": socket.gethostname()[:12],
                        "attempt": attempt,
                    }
            except subprocess.TimeoutExpired:
                # seguimos intentando
                pass

            # Soft reconnect progresivo entre intentos
            if attempt < STATE_RETRIES:
                _disconnect_once(req.adb_identifier)
                _jitter_sleep(0.15)
                _connect_and_wait(req.adb_identifier, CONNECT_WAIT_SEC)

        # Si no logró “device” tras los intentos:
        return {
            "status": "error",
            "state": "unknown",
            "output": f"state unsettled after {STATE_RETRIES} retries",
            "instance": socket.gethostname()[:12],
        }
