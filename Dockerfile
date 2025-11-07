FROM python:3.11-slim

# Opcional, hace logs sin buffer y evita .pyc
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# ADB (paquete correcto en Debian/Ubuntu)
RUN apt-get update && apt-get install -y --no-install-recommends \
      android-tools-adb curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia el código (asegúrate de que aquí está tu main.py con FastAPI(app))
COPY . .

# Instala dependencias (versionadas es mejor)
# Si tienes requirements.txt, usa esa línea; si no, la de abajo.
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7"

# Expone el puerto que realmente usas
EXPOSE 5001

# (Opcional) Healthcheck simple
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD curl -fsS http://127.0.0.1:5001/ || exit 1

# Ejecuta el server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]
