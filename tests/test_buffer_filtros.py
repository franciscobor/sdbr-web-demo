from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sdbr_web.dominio.buffer import (
    AMARILLO,
    BLANCO,
    NEGRO,
    ROJO,
    SIN_DATO,
    VERDE,
    calcular_buffer,
    conteo_zonas,
    zona_de_buffer,
)
from sdbr_web.dominio.filtros import aplicar_filtros

HOY = datetime(2026, 11, 23)


def _df(fechas, lead_times):
    return pd.DataFrame({"fin": fechas, "lead": lead_times})


def test_buffer_casos_conocidos():
    df = _df(
        [
            HOY + timedelta(days=10),
            HOY,
            HOY + timedelta(days=30),
            HOY - timedelta(days=5),
            HOY + timedelta(days=10),
        ],
        [20, 20, 20, 20, -20],
    )
    assert calcular_buffer(df, "fin", "lead", HOY).tolist() == [50, 100, -50, 125, 50]


def test_buffer_igual_que_escritorio():
    """La fórmula de los _datos_listos de escritorio, con datos al azar."""
    rng = np.random.default_rng(7)
    df = _df(
        [
            HOY + timedelta(days=int(d), hours=int(h))
            for d, h in zip(rng.integers(-60, 90, 500), rng.integers(0, 24, 500))
        ],
        rng.integers(1, 120, 500),
    )
    dias = (pd.to_datetime(df["fin"]) - HOY).dt.total_seconds() / 86400.0
    escritorio = ((1 - (dias / df["lead"].abs())) * 100).round().astype(int)
    assert (
        calcular_buffer(df, "fin", "lead", HOY).astype(int).tolist()
        == escritorio.tolist()
    )


def test_buffer_no_calculable_queda_vacio():
    df = _df([HOY + timedelta(days=3), None], [0, 10])
    assert calcular_buffer(df, "fin", "lead", HOY).isna().tolist() == [True, True]


def test_zonas_en_los_limites():
    buffer = pd.Series([-1, 0, 33, 34, 66, 67, 100, 101, None], dtype="Int64")
    assert zona_de_buffer(buffer).tolist() == [
        BLANCO,
        VERDE,
        VERDE,
        AMARILLO,
        AMARILLO,
        ROJO,
        ROJO,
        NEGRO,
        SIN_DATO,
    ]


def test_conteo_en_orden_de_las_graficas():
    zonas = pd.Series([NEGRO, NEGRO, ROJO, VERDE, BLANCO, SIN_DATO])
    assert conteo_zonas(zonas) == [
        2,
        1,
        0,
        1,
        1,
    ]  # negro, rojo, amarillo, verde, blanco
    assert conteo_zonas(pd.Series([], dtype=int)) == [0, 0, 0, 0, 0]


def test_filtros_se_combinan_y_no_distinguen_mayusculas():
    df = pd.DataFrame(
        {"cliente": ["Acme", "ACME Norte", "Otro"], "producto": ["X1", "Y2", "X3"]}
    )
    columnas = {"cliente": "cliente", "producto": "producto"}
    assert aplicar_filtros(df, {"cliente": "acme"}, columnas)["producto"].tolist() == [
        "X1",
        "Y2",
    ]
    assert aplicar_filtros(df, {"cliente": "acme", "producto": "x"}, columnas)[
        "producto"
    ].tolist() == ["X1"]


def test_filtros_texto_literal_y_vacios():
    df = pd.DataFrame({"descripcion": ["Eje (largo)", "Eje corto", None]})
    columnas = {"descripcion": "descripcion", "familia": "no_existe"}
    assert (
        len(aplicar_filtros(df, {"descripcion": "(largo"}, columnas)) == 1
    )  # no es regex
    assert (
        len(aplicar_filtros(df, {"descripcion": "  ", "familia": "x"}, columnas)) == 3
    )
