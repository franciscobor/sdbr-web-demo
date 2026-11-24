# Imagen de SDBR Web: Python 3.12 + ODBC Driver 18 for SQL Server + la aplicación.
# La usan la demo (docker-compose.yml) y el CI. Producción sigue en Windows Server con Waitress.

FROM python:3.12-slim-bookworm

# ODBC Driver 18 de Microsoft desde su repositorio para Debian 12.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL -o /tmp/packages-microsoft-prod.deb \
        https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Bogota \
    SDBR_HOST=0.0.0.0 \
    SDBR_PUERTO=8050

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY servidor.py ./
COPY sdbr_web ./sdbr_web
COPY demo ./demo

# Sin root. logs/ es donde servidor.py escribe su registro.
RUN useradd --create-home --uid 1000 sdbr && mkdir -p /app/logs && chown -R sdbr /app/logs
USER sdbr

EXPOSE 8050
CMD ["python", "servidor.py"]
