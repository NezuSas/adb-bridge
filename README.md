<div align="center">
  <img src=".github/banner.svg" alt="NEZU · ADB Bridge, servicio FastAPI para dispositivos Android en la red local" width="100%">
</div>

# ADB Bridge

> **In English.** A small FastAPI service that runs ADB commands on Android displays over the local network and handles the flaky parts of ADB over Wi-Fi: on-demand connection, keepalive, retries on transport errors only, and per-device locking. Optional bearer token and device allowlist, OpenAPI docs, a test suite with a simulated `adb`, Docker Compose, a Home Assistant example and a command cheat sheet. Apache 2.0.

Servicio HTTP mínimo, en Python y FastAPI, que ejecuta comandos ADB sobre dispositivos Android conectados por red (`IP:PUERTO`) y devuelve el resultado. Permite que un sistema de automatización controle pantallas y dispositivos Android desde la red local sin tener ADB instalado en cada cliente.

## Qué resuelve

ADB por Wi‑Fi es frágil: el dispositivo se duerme, el demonio pierde la conexión y los comandos fallan de forma intermitente. El puente se encarga de eso:

- Conecta al dispositivo bajo demanda y mantiene un **keepalive** con los usados recientemente.
- Si la conexión falla, reintenta con reconexión progresiva y reinicio del servidor ADB cada cierto número de intentos. Si el comando llega al dispositivo y es este el que devuelve un error, lo entrega tal cual y al momento: reintentarlo no lo arreglaría.
- Serializa los comandos por dispositivo con un bloqueo, para no pisar una conexión con otra.
- Acota el tiempo total de cada petición: el cliente nunca queda colgado.

## Endpoints

| Método | Ruta | Cuerpo | Respuesta |
|---|---|---|---|
| `GET` | `/health` | — | `{"status": "ok", "version": "1.0.0", "adb": "<versión de adb>", "auth": true/false}`. No pide token. |
| `GET` | `/adb/devices` | — | `{"devices": [{"adb_identifier": "IP:PUERTO", "state": "device", "description": "..."}]}`: lo que el servidor ADB conoce. |
| `POST` | `/adb/state` | `{"adb_identifier": "IP:PUERTO"}` | `{"status": "ok", "state": "device", "attempt": n}` cuando el dispositivo responde; `state: "unknown"` si no se asienta tras varios intentos. |
| `POST` | `/adb/execute` | `{"adb_identifier": "IP:PUERTO", "command": "<comando adb shell>"}` | `{"status": "ok", "output": "...", "attempts": n}`, o `{"status": "error", "output": "<motivo>", "attempts": n}` con `exit_code` cuando el error lo devolvió el propio comando. |
| `GET` | `/` | — | `OK (<host>)`, por compatibilidad con comprobaciones antiguas. |

Toda respuesta incluye `instance` con el host que atendió. El identificador debe ser `IP:PUERTO` (o `host:PUERTO`); cualquier otra cosa responde `422` sin tocar `adb`. La documentación interactiva está en `/docs`.

```bash
curl -s -X POST http://127.0.0.1:5001/adb/execute \
  -H 'Content-Type: application/json' \
  -d '{"adb_identifier": "192.168.1.50:5555", "command": "input keyevent KEYCODE_WAKEUP"}'
```

Con token configurado, añade `-H 'Authorization: Bearer <token>'`.

## Ejecutar

Con Docker Compose, que ya incluye `android-tools-adb` y conserva la clave ADB entre reinicios:

```bash
ADB_BRIDGE_TOKEN=cambia-este-valor docker compose up -d --build
```

O con Docker a secas:

```bash
docker build -t adb-bridge .
docker run -d --name adb-bridge --network host -v adb_keys:/root/.android \
  -e ADB_BRIDGE_TOKEN=cambia-este-valor adb-bridge
```

Sin Docker, con ADB instalado en el sistema:

```bash
pip install -r requirements.txt
ADB_BRIDGE_TOKEN=cambia-este-valor uvicorn main:app --host 0.0.0.0 --port 5001
```

El servicio escucha en el puerto `5001`. Los dispositivos deben tener la depuración por red habilitada y haber autorizado la clave ADB del equipo donde corre el puente; cómo prepararlos, en [`examples/commands.md`](examples/commands.md).

## Ejemplos

| Archivo | Para qué |
|---|---|
| [`examples/home-assistant.yaml`](examples/home-assistant.yaml) | Controlar la pantalla desde Home Assistant: `rest_command` para despertar, dormir, abrir una URL y subir el volumen, con automatizaciones de ejemplo (encender con movimiento, apagar de noche, abrir el tablero por la mañana). |
| [`examples/commands.md`](examples/commands.md) | Chuleta de comandos para pantalla, navegación, apps, sonido e información del equipo; cómo preparar la pantalla una sola vez; y qué significan `unauthorized`, `offline` y `unknown`. |
| [`docker-compose.yml`](docker-compose.yml) | Despliegue con reinicio automático, comprobación de salud, clave ADB persistente y las variables de seguridad. |

Cualquier cliente HTTP sirve: Node-RED, n8n, un cron con `curl`, o la API de tu propio sistema.

## Ajustes

Los límites son constantes en `adb_bridge/config.py`: tiempo de espera por comando, intentos máximos, cota total por petición y ventana del keepalive. No se leen de variables de entorno a propósito: el comportamiento es el mismo en todas las instalaciones. Solo la seguridad depende del entorno:

| Variable | Efecto |
|---|---|
| `ADB_BRIDGE_TOKEN` | Si está definida, `/adb/*` exige `Authorization: Bearer <token>`; sin ella, el puente lo avisa en el registro al arrancar. |
| `ADB_BRIDGE_ALLOWED_DEVICES` | Lista separada por comas de identificadores admitidos; los demás reciben `403`. |

## Seguridad

Quien alcance el puerto puede ejecutar comandos en los dispositivos, por eso el puente debe correr **solo en la red local** y nunca exponerse a internet. El token y la lista de dispositivos reducen el daño si alguien llega al puerto, pero no sustituyen el aislamiento de red: el tráfico va en claro, así que un token que viaja por una red ajena es un token perdido. Los comandos se recortan en los registros para no guardar entero lo que se teclea en las pantallas.

## Código y pruebas

```
adb_bridge/
  config.py   ajustes y variables de entorno
  adb.py      lo que habla con el binario adb
  service.py  conexión bajo demanda, reintentos, bloqueo por dispositivo, keepalive
  api.py      validación, token, rutas
main.py       expone `app` para uvicorn
tests/        suite con un adb simulado: no hace falta ningún dispositivo
```

```bash
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
pytest
```

## ¿Lo necesitas en tu instalación?

Esta herramienta es gratuita: la publicamos porque la usamos en nuestros propios proyectos. Si quieres controlar pantallas Android en tu local, oficina o casa y prefieres que lo instalemos, lo adaptemos a tu caso o lo integremos con el resto de tu sistema, [cuéntanos qué necesitas](https://nezuecuador.com/es/contacto) y te respondemos con una propuesta concreta. Aquí está [lo que hacemos](https://nezuecuador.com/es/servicios).

## Versiones

Los cambios de cada versión están en [CHANGELOG.md](CHANGELOG.md).

## Licencia

Apache 2.0: puedes usar, modificar y redistribuir este código, también en proyectos comerciales, conservando el aviso de copyright. La licencia no concede derechos sobre la marca NEZU. Texto completo en [LICENSE](LICENSE).

---

<div align="center">
  <sub>Parte del ecosistema <a href="https://github.com/NezuSas">NEZU</a> · <a href="https://nezuecuador.com">nezuecuador.com</a> · © NEZU S.A.S. · Licencia Apache 2.0.</sub>
</div>
