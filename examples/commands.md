# Comandos útiles para pantallas Android

Todos se envían en el campo `command` de `POST /adb/execute`; el puente los ejecuta como `adb shell <command>`. Prueba primero desde la terminal con `adb -s IP:5555 shell <command>` y, cuando funcione, pásalo al puente.

## Pantalla y energía

| Qué hace | Comando |
|---|---|
| Despertar | `input keyevent KEYCODE_WAKEUP` |
| Dormir (apagar la pantalla) | `input keyevent KEYCODE_SLEEP` |
| Alternar encendido/apagado | `input keyevent KEYCODE_POWER` |
| Saber si la pantalla está encendida | `dumpsys power \| grep mWakefulness` → `Awake` o `Asleep` |
| Brillo (0–255) | `settings put system screen_brightness 180` |
| Que no se apague nunca | `settings put system screen_off_timeout 2147483647` |
| Que se apague a los 5 minutos | `settings put system screen_off_timeout 300000` |

## Navegación

| Qué hace | Comando |
|---|---|
| Inicio | `input keyevent KEYCODE_HOME` |
| Atrás | `input keyevent KEYCODE_BACK` |
| Apps recientes | `input keyevent KEYCODE_APP_SWITCH` |
| Tocar en una coordenada | `input tap 540 960` |
| Deslizar (x1 y1 x2 y2 ms) | `input swipe 540 1500 540 500 300` |
| Escribir texto | `input text Hola%sMundo` (`%s` es el espacio) |

## Aplicaciones

| Qué hace | Comando |
|---|---|
| Abrir una URL en el navegador | `am start -a android.intent.action.VIEW -d https://ejemplo.com` |
| Abrir una app por su paquete | `monkey -p com.ejemplo.app -c android.intent.category.LAUNCHER 1` |
| Cerrar una app | `am force-stop com.ejemplo.app` |
| App en primer plano | `dumpsys window \| grep mCurrentFocus` |
| Listar paquetes instalados | `pm list packages` |

## Sonido

| Qué hace | Comando |
|---|---|
| Volumen multimedia (0–15 según el equipo) | `cmd media_session volume --stream 3 --set 8` |
| Silenciar | `input keyevent KEYCODE_VOLUME_MUTE` |
| Reproducir/pausar | `input keyevent KEYCODE_MEDIA_PLAY_PAUSE` |

## Información del dispositivo

| Qué hace | Comando |
|---|---|
| Modelo | `getprop ro.product.model` |
| Versión de Android | `getprop ro.build.version.release` |
| Batería | `dumpsys battery \| grep level` |
| Dirección IP | `ip -4 addr show wlan0 \| grep inet` |

## Preparar la pantalla (una sola vez)

1. Activa las **Opciones de desarrollador** (siete toques sobre «Número de compilación») y dentro **Depuración USB**.
2. Con la pantalla conectada por USB al equipo del puente: `adb tcpip 5555`. Desde ese momento acepta ADB por red; en muchos equipos se conserva tras reiniciar, en otros hay que repetirlo.
3. Dale una **IP fija** en el router: si cambia, el puente dejará de encontrarla.
4. La primera conexión desde el puente mostrará en la pantalla «¿Permitir depuración USB?»: marca «Permitir siempre». Si el puente corre en Docker, monta un volumen para `/root/.android` (ver `docker-compose.yml`) para no repetir esto en cada reinicio.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `unauthorized` | La pantalla no autorizó la clave del puente. Acepta el aviso en la pantalla o borra sus claves en Opciones de desarrollador → «Revocar autorizaciones» y vuelve a conectar. |
| `offline` | El demonio ADB de la pantalla se quedó colgado. El puente reintenta y reinicia su servidor ADB; si persiste, reinicia la pantalla. |
| `state: "unknown"` tras varios intentos | La pantalla está apagada, sin red o cambió de IP. Comprueba `ping` a la IP y que el puerto 5555 responde: `nc -zv IP 5555`. |
| Funciona por USB pero no por red | No se ejecutó `adb tcpip 5555` después del último reinicio. |
| Dos equipos controlan la misma pantalla | Android solo mantiene una sesión ADB por red estable. Deja que solo el puente hable con ella. |
