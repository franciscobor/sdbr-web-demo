"""Configuración común de las pruebas. Ninguna prueba toca SQL Server."""

import os
from datetime import timedelta

import pandas as pd
import pytest
from sdbr_web.dominio.buffer import hoy_a_medianoche

# Antes de importar la aplicación: clave fija y una base que no existe, para que un acceso
# accidental a SQL Server falle en vez de leer datos reales. Usuario y contraseña ficticios porque
# cargar_configuracion() los exige: así la suite corre sin .env, y como el entorno manda sobre el
# .env, una prueba nunca usa las credenciales reales.
os.environ.setdefault("SDBR_SECRET_KEY", "clave-de-pruebas")
os.environ["SDBR_SQL_SERVIDOR"] = "servidor-inexistente-de-pruebas"
os.environ["SDBR_SQL_USUARIO"] = "nadie"
os.environ["SDBR_SQL_PASSWORD"] = "nada"
# La marca y el modo demo tampoco salen del .env local: las pruebas que los necesitan los cambian
# en la configuración de Flask (ver tests/test_app.py).
os.environ["SDBR_EMPRESA"] = ""
os.environ["SDBR_LOGO"] = "logo_sdbr.svg"
os.environ["SDBR_MODO_DEMO"] = "no"

# Las pantallas calculan el buffer contra la fecha real de hoy: los datos se construyen igual.
HOY = hoy_a_medianoche()


def fila_v3(
    pedido,
    producto,
    estado="Ingenieria",
    dias_al_fin=10,
    lead_time=20,
    buffer_global=40,
    familia="FAMILIA A",
    cliente="CLIENTE S.A.",
):
    """Una fila con las columnas de Pedidos_Fechas_Fin2_V3 que usa la pantalla de Ingeniería."""
    return {
        "pedconsecutivo": pedido,
        "NombCliente": cliente,
        "Producto": producto,
        "Descripcion": f"Pieza {producto}",
        "Final_Inge": HOY + timedelta(days=dias_al_fin),
        "Buffer_Ing": lead_time,
        "Cantidad": 5,
        "Estado_SDBR": estado,
        "NombreFamilia": familia,
        "Buffer": buffer_global,
        "Fecha_Venci_Espejo": HOY + timedelta(days=30),
        "Estado_Final": "En_planta",
    }


@pytest.fixture
def crudo():
    """Pedidos en planta sintéticos: dos líneas del pedido 1001 en Ingeniería, una en Ops..."""
    return pd.DataFrame(
        [
            fila_v3("1001", "PROD-A", dias_al_fin=10),  # buffer 50 → amarillo
            fila_v3("1001", "PROD-B", dias_al_fin=-5),  # buffer 125 → negro
            fila_v3("1001", "PROD-C", estado="Planeacion"),
            fila_v3(
                "1002", "PROD-D", dias_al_fin=30, familia=""
            ),  # buffer -50 → blanco
            fila_v3(
                "1003", "PROD-E", dias_al_fin=18, cliente="OTRO CLIENTE"
            ),  # buffer 10 → verde
        ]
    )
