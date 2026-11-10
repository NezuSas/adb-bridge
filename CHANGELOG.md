# Cambios

Formato de [Keep a Changelog](https://keepachangelog.com/es/1.1.0/); versiones según [SemVer](https://semver.org/lang/es/).

## [1.0.0] - 2026-11-09

Primera versión numerada. Hasta aquí el puente era un solo archivo sin pruebas.

### Corregido

- Un comando que el dispositivo ejecuta y devuelve con error (una app que no existe, una ruta inválida) ya no se reintenta hasta 24 veces durante 30 segundos: se devuelve de inmediato con `exit_code` y el mensaje real. Solo los fallos de conexión con el dispositivo se reintentan.

### Añadido

- Autenticación opcional con `ADB_BRIDGE_TOKEN` (cabecera `Authorization: Bearer`). Sin token, el puente funciona como antes y lo avisa en el registro al arrancar.
- Lista opcional de dispositivos permitidos con `ADB_BRIDGE_ALLOWED_DEVICES`.
- Validación del identificador: solo `IP:PUERTO` o `host:PUERTO`; cualquier otra cosa responde `422` sin tocar `adb`.
- `GET /health` con versión, versión de `adb` y si la autenticación está activa. `GET /adb/devices` con los dispositivos que el servidor ADB conoce.
- Campo `attempts` en las respuestas de `/adb/execute`.
- Documentación OpenAPI en `/docs` con título, versión y modelos de respuesta.
- Suite de pruebas con `pytest` sobre un `adb` simulado, y `ruff` para estilo.

### Cambiado

- El código pasa de `main.py` a un paquete `adb_bridge` (configuración, transporte, servicio y API). `uvicorn main:app` sigue funcionando.
- El `command` de `/adb/state` ya es opcional.
- Los comandos se recortan en los registros para no guardar entero lo que se teclea en las pantallas.
- El keepalive arranca y se detiene con la aplicación, en lugar de al importar el módulo.
- `Dockerfile` instala desde `requirements.txt`, parte de `python:3.12-slim` y comprueba `/health`; `docker-compose.yml` expone las dos variables de seguridad.

[1.0.0]: https://github.com/NezuSas/adb-bridge/releases/tag/v1.0.0
