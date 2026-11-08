# adb-bridge

Servicio HTTP mínimo, en Python y FastAPI, que ejecuta comandos ADB sobre dispositivos Android conectados por red (`IP:PUERTO`) y devuelve el resultado. Pensado para que un sistema de automatización controle pantallas y dispositivos Android desde la red local sin tener ADB instalado en cada cliente.

Parte del ecosistema de [NEZU](https://nezuecuador.com).

## Qué resuelve

ADB por Wi‑Fi es frágil: el dispositivo se duerme, el daemon pierde la conexión y los comandos fallan de forma intermitente. El puente se encarga de eso:

- Conecta al dispositivo bajo demanda y mantiene un **keepalive** con los que se usaron recientemente.
- Reintenta hasta obtener respuesta, con reconexión progresiva y reinicio del servidor ADB cada cierto número de intentos.
- Serializa los comandos por dispositivo con un bloqueo, para no pisar una conexión con otra.
- Acota el tiempo total de cada petición, de modo que el cliente nunca queda colgado.

## Endpoints

| Método | Ruta | Cuerpo | Respuesta |
|---|---|---|---|
| `GET` | `/` | — | `OK (<host>)`. Sirve como comprobación de salud. |
| `POST` | `/adb/state` | `{"adb_identifier": "IP:PUERTO", "command": ""}` | `{"status": "ok", "state": "device", "attempt": n}` cuando el dispositivo responde; `state: "unknown"` si no se asienta tras varios intentos. |
| `POST` | `/adb/execute` | `{"adb_identifier": "IP:PUERTO", "command": "<comando adb shell>"}` | `{"status": "ok", "output": "..."}` o `{"status": "error", "output": "<motivo>"}`. Siempre incluye `instance` con el host que atendió. |

Ejemplo:

```bash
curl -s -X POST http://127.0.0.1:5001/adb/execute \
  -H 'Content-Type: application/json' \
  -d '{"adb_identifier": "192.168.1.50:5555", "command": "input keyevent KEYCODE_WAKEUP"}'
```

## Ejecutar

Con Docker, que ya incluye `android-tools-adb`:

```bash
docker build -t adb-bridge .
docker run -d --name adb-bridge --network host adb-bridge
```

Sin Docker, con ADB instalado en el sistema:

```bash
pip install fastapi "uvicorn[standard]" pydantic
uvicorn main:app --host 0.0.0.0 --port 5001
```

El servicio escucha en el puerto `5001`. Los dispositivos deben tener la depuración por red habilitada y haber autorizado previamente la clave ADB del equipo donde corre el puente.

## Ajustes

Los límites están definidos como constantes al inicio de `main.py`: trabajadores concurrentes, tiempo de espera por comando, intentos máximos, cota total por petición y ventana del keepalive. No se leen de variables de entorno a propósito: el comportamiento es el mismo en todas las instalaciones.

## Seguridad

El puente no autentica peticiones. Debe correr **solo en la red local** o detrás de un servicio que sí autorice, y nunca exponerse a internet: cualquiera que alcance el puerto puede ejecutar comandos en los dispositivos.

## Licencia

© NEZU S.A.S. Se publica para uso de clientes e integradores de NEZU.
