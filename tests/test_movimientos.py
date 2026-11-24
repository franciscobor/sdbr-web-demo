"""Los movimientos deben escribir lo mismo que escribía sdbr/nucleo/lote.py."""

from datetime import datetime, timedelta

import pandas as pd
import pytest
from sdbr_web.dominio.movimientos import (
    A_TIEMPO,
    NUNCA,
    SIEMPRE,
    SQL_ENTREGA_PI,
    SQL_HISTORIAL,
    SQL_MOVER,
    SQL_RECLASIFICAR,
    SQL_RECLASIFICAR_CONTRA_FLUJO,
    Registro,
    construir_trabajos_contra_flujo,
    construir_trabajos_entrega_pi,
    construir_trabajos_flujo,
    construir_trabajos_solo_estado,
)

from tests.conftest import HOY, fila_v3

AHORA = datetime(2026, 11, 23, 9, 30, 15)


def _filas(crudo):
    return lambda pedido: crudo[crudo["pedconsecutivo"] == pedido]


def _flujo(
    registros, crudo, reclasifica=NUNCA, destino="Planeacion", origen="Ingenieria"
):
    return construir_trabajos_flujo(
        registros,
        origen=origen,
        destino=destino,
        retroceso="No",
        reclasifica=reclasifica,
        filas_de_pedido=_filas(crudo),
        ahora=AHORA,
    )


def _historial(trabajo):
    return next(s for s in trabajo.sentencias if s.sql == SQL_HISTORIAL).parametros


def test_mover_todas_las_lineas_del_area_la_ultima_es_ultimo(crudo):
    trabajos, descartes = _flujo(
        [Registro("1001", "PROD-A", 50), Registro("1001", "PROD-B", 125)], crudo
    )
    assert descartes == []
    assert [_historial(t)["calificacion"] for t in trabajos] == ["Parcial", "Ultimo"]


def test_mover_una_de_dos_lineas_es_parcial_y_una_sola_es_ultimo(crudo):
    trabajos, _ = _flujo([Registro("1001", "PROD-B", 125)], crudo)
    assert _historial(trabajos[0])["calificacion"] == "Parcial"
    trabajos, _ = _flujo([Registro("1003", "PROD-E", 10)], crudo)
    assert _historial(trabajos[0])["calificacion"] == "Ultimo"


def test_like_del_producto_descuenta_las_lineas_que_lo_contienen():
    """Igual que lote.py: mover 'ABC' (LIKE '%ABC%') también se lleva 'ABC-1'."""
    crudo = pd.DataFrame(
        [fila_v3("2001", "ABC"), fila_v3("2001", "ABC-1"), fila_v3("2001", "XYZ")]
    )
    trabajos, _ = _flujo(
        [Registro("2001", "ABC", 10), Registro("2001", "XYZ", 10)], crudo
    )
    assert [_historial(t)["calificacion"] for t in trabajos] == ["Parcial", "Ultimo"]


def test_parametros_identicos_a_escritorio(crudo):
    trabajos, _ = _flujo([Registro("1001", "PROD-A", 50)], crudo)
    mover, insertar = trabajos[0].sentencias
    assert mover.sql == SQL_MOVER and mover.exige_filas
    assert mover.parametros == {
        "destino": "Planeacion",
        "pedido": "1001",
        "patron": "%PROD-A%",
        "origen": "Ingenieria",
    }
    assert insertar.parametros == {
        "fecha": "2026-11-23 09:30:15",
        "pedido": "1001",
        "producto": "PROD-A",
        "origen": "Ingenieria",
        "destino": "Planeacion",
        "fecha_psl": (HOY + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
        "buffer_global": "40",
        "on_time": "1",
        "buffer_zona": "50",
        "retroceso": "No",
        "calificacion": "Parcial",
    }


@pytest.mark.parametrize(
    "reclasifica, buffer, espera_reclasificar, on_time",
    [
        (NUNCA, 50, False, "1"),
        (NUNCA, 125, False, "0"),
        (SIEMPRE, 50, True, "1"),
        (SIEMPRE, 125, True, "0"),
        (A_TIEMPO, 50, True, "1"),
        (A_TIEMPO, 125, False, "0"),
    ],
)
def test_reclasificacion_y_a_tiempo(
    crudo, reclasifica, buffer, espera_reclasificar, on_time
):
    trabajos, _ = _flujo(
        [Registro("1001", "PROD-A", buffer)], crudo, reclasifica=reclasifica
    )
    sqls = [s.sql for s in trabajos[0].sentencias]
    assert (SQL_RECLASIFICAR in sqls) == espera_reclasificar
    if espera_reclasificar:  # mismo orden que _paso_flujo: UPDATE, reclasificar, INSERT
        assert sqls == [SQL_MOVER, SQL_RECLASIFICAR, SQL_HISTORIAL]
    assert _historial(trabajos[0])["on_time"] == on_time


def test_descartes(crudo):
    trabajos, descartes = _flujo(
        [
            Registro("9999", "NADA", 10),
            Registro("1001", "PROD-A", pd.NA),
            Registro("1001", "PROD-A", None),
        ],
        crudo,
    )
    assert trabajos == []
    assert [d[0] for d in descartes] == ["9999", "1001"]  # el repetido se deduplica


def test_contra_flujo(crudo):
    registros = [
        Registro("1001", "PROD-C", 30, origen="Planeacion"),
        Registro("1003", "PROD-E", 101, origen="Ingenieria"),
    ]
    trabajos, descartes = construir_trabajos_contra_flujo(
        registros, destino="Ingenieria", filas_de_pedido=_filas(crudo), ahora=AHORA
    )
    assert descartes == [("1003", "PROD-E", "ya está en el área de destino")]
    (trabajo,) = trabajos
    assert [s.sql for s in trabajo.sentencias] == [
        SQL_RECLASIFICAR_CONTRA_FLUJO,
        SQL_MOVER,
        SQL_HISTORIAL,
    ]
    assert trabajo.sentencias[1].parametros["origen"] == "Planeacion"
    historial = _historial(trabajo)
    assert (historial["retroceso"], historial["calificacion"], historial["origen"]) == (
        "Si",
        "Parcial",
        "Planeacion",
    )


def test_almacen_mp_y_pi():
    registros = [Registro("1", "P", 10), Registro("1", "P", 20)]
    trabajos, _ = construir_trabajos_solo_estado(
        registros, origen="Almacen", destino="Produccion"
    )
    assert len(trabajos) == 1 and [s.sql for s in trabajos[0].sentencias] == [SQL_MOVER]

    registros = [Registro("1", "MP1", 10, op="OP1"), Registro("1", "MP1", 10, op="OP2")]
    trabajos, _ = construir_trabajos_entrega_pi(
        registros, destino="Entregado", ahora=AHORA
    )
    assert len(trabajos) == 2 and trabajos[0].sentencias[0].sql == SQL_ENTREGA_PI
    assert trabajos[1].sentencias[0].parametros["op"] == "OP2"
