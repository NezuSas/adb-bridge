"""Punto de entrada: `uvicorn main:app --host 0.0.0.0 --port 5001`.

La aplicación vive en el paquete `adb_bridge`; este archivo solo la expone con el nombre de siempre.
"""

from adb_bridge.api import app

__all__ = ["app"]
