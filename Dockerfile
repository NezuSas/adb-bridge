FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# El binario adb que habla con las pantallas; curl solo para la comprobación de salud.
RUN apt-get update && apt-get install -y --no-install-recommends \
      android-tools-adb curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Las dependencias se instalan antes que el código: cambiar el código no vuelve a instalarlas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY adb_bridge ./adb_bridge

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD curl -fsS http://127.0.0.1:5001/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]
