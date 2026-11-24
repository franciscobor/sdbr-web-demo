"""Pruebas de integración contra la base de DEMO (SQL Server de Docker o del CI).

No corren con la suite normal (pytest.ini solo mira tests/). Se activan a propósito:

    docker compose up -d sqlserver
    SDBR_PRUEBAS_INTEGRACION=si ./venv/Scripts/python.exe -m pytest tests_integracion

Leen SOLO demo/docker.env: ni el .env de producción ni las variables del entorno, que en un equipo
de desarrollo pueden ser las de producción.
La primera prueba reinstala la base de demo desde cero, y demo/instalar.py se niega a tocar una
base que no sea de demo.
"""

import os
from contextlib import closing

import pyodbc
import pytest
from demo import instalar
from sdbr_web.app import crear_app
from sdbr_web.datos import conexion

ACTIVAS = os.environ.get("SDBR_PRUEBAS_INTEGRACION", "").strip().lower() in (
    "1",
    "si",
    "sí",
    "true",
    "yes",
)


def pytest_collection_modifyitems(config, items):
    if ACTIVAS:
        return
    saltar = pytest.mark.skip(
        reason="defina SDBR_PRUEBAS_INTEGRACION=si para correrlas"
    )
    for item in items:
        item.add_marker(saltar)


@pytest.fixture(scope="session")
def base_demo():
    """Instala la demo desde cero y deja el pool de la web conectado con el usuario de la app."""
    config, admin = instalar.leer_configuracion(instalar.ENV_DOCKER)
    datos = instalar.instalar(config, admin)
    # La aplicación completa: configura el pool con el usuario de la app y registra las páginas.
    app = crear_app(config)
    yield {"config": config, "admin": admin, "datos": datos, "app": app}
    conexion.configurar(None)


@pytest.fixture
def sql_admin(base_demo):
    """Ejecuta una sentencia con la cuenta de administrador (para preparar casos)."""

    def ejecutar(sentencia, *parametros):
        with closing(pyodbc.connect(base_demo["admin"].cadena_odbc)) as cnx:
            cursor = cnx.cursor()
            cursor.execute(sentencia, *parametros)
            filas = cursor.fetchall() if cursor.description else None
            cnx.commit()
            return filas

    return ejecutar
