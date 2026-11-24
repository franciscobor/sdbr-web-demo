"""La web contra una base SQL Server de verdad: lectura, movimiento, login y restablecimiento.

Las pruebas van en orden: la de movimiento deja una línea movida y la última restablece la demo.
"""

from datetime import datetime

import pytest
import sqlalchemy.exc
from sdbr_web.componentes.pantalla_sdbr import preparar
from sdbr_web.datos.conexion import leer_sql, transaccion
from sdbr_web.datos.demo import PASSWORD_DEMO, reiniciar_si_toca
from sdbr_web.datos.movimientos import ejecutar_trabajos
from sdbr_web.datos.pedidos import cargar_pedidos_en_planta, filas_del_pedido
from sdbr_web.datos.usuarios import MAX_INTENTOS, autenticar
from sdbr_web.dominio.buffer import conteo_zonas
from sdbr_web.dominio.movimientos import Registro, construir_trabajos_flujo

COLUMNAS_V3 = {
    "pedconsecutivo",
    "NombCliente",
    "Producto",
    "Descripcion",
    "Cantidad",
    "Estado_SDBR",
    "Estado_Final",
    "NombreFamilia",
    "Buffer",
    "FechaDocumen",
    "Fecha_Venci_Espejo",
    "Final_Inge",
    "Buffer_Ing",
    "Final_Plane",
    "Buffer_Plane",
    "Final_Compras",
    "Buffer_Compras",
    "Buffer_Manuf",
}



def _ingenieria():
    # Se importa después de crear la aplicación: el módulo registra su página en Dash.
    from sdbr_web.paginas.sdbr.ingenieria import CONFIG

    return CONFIG


ESTADO = "SELECT Estado_SDBR FROM SDBR_MOV WHERE pedconsecutivo = :p AND producto = :pr"


def _linea_de_ingenieria():
    crudo = cargar_pedidos_en_planta(forzar=True)
    df = preparar(crudo, _ingenieria())
    fila = df[df["Buffer"].notna()].iloc[0]
    return crudo, Registro(fila["pedconsecutivo"], fila["Producto"], fila["Buffer"])


def test_la_vista_tiene_el_contrato_de_la_web(base_demo):
    crudo = cargar_pedidos_en_planta(forzar=True)
    assert COLUMNAS_V3 <= set(crudo.columns)
    en_planta = sum(
        e["Estado_Final"] == "En_planta" for e in base_demo["datos"].estados
    )
    assert len(crudo) == en_planta
    assert crudo["Buffer"].notna().all()


def test_ingenieria_muestra_las_cinco_zonas(base_demo):
    df = preparar(cargar_pedidos_en_planta(forzar=True), _ingenieria())
    assert len(df) > 50
    assert all(n > 0 for n in conteo_zonas(df["Zona"]))


def test_movimiento_completo_en_una_transaccion(base_demo):
    crudo, registro = _linea_de_ingenieria()
    trabajos, descartes = construir_trabajos_flujo(
        [registro],
        origen="Ingenieria",
        destino="Planeacion",
        retroceso="No",
        reclasifica=_ingenieria().reclasifica,
        filas_de_pedido=lambda pedido: filas_del_pedido(crudo, pedido),
        ahora=datetime.now(),
    )
    assert descartes == []
    movidos, fallos = ejecutar_trabajos(trabajos, "demo.operador", "mover")
    assert (len(movidos), fallos) == (1, [])

    claves = {"p": registro.pedido, "pr": registro.producto}
    assert leer_sql(ESTADO, claves)["Estado_SDBR"].tolist() == ["Planeacion"]
    historial = leer_sql(
        "SELECT TOP 1 Sale_De, Entra_A, Buffer_Zona, Retroceso FROM Mov_Tiempo_Real3 "
        "WHERE Pedido = :p AND Producto = :pr ORDER BY Id DESC",
        claves,
    ).iloc[0]
    assert (historial["Sale_De"], historial["Entra_A"], historial["Retroceso"]) == (
        "Ingenieria",
        "Planeacion",
        "No",
    )
    assert historial["Buffer_Zona"] == int(registro.buffer)
    auditoria = leer_sql(
        "SELECT Usuario, Origen, Destino FROM SDBR_Auditoria "
        "WHERE Accion = 'mover' AND Pedido = :p AND Producto = :pr",
        claves,
    )
    assert auditoria.values.tolist() == [["demo.operador", "Ingenieria", "Planeacion"]]

    # Otro usuario intenta mover la misma línea con datos desfasados: falla y no escribe nada.
    movidos, fallos = ejecutar_trabajos(trabajos, "demo.supervisor", "mover")
    assert movidos == [] and "ya no estaba en Ingenieria" in fallos[0][2]
    assert (
        len(
            leer_sql(
                "SELECT 1 AS x FROM SDBR_Auditoria WHERE Pedido = :p AND Producto = :pr",
                claves,
            )
        )
        == 1
    )


def test_el_usuario_de_la_app_tiene_permisos_minimos(base_demo):
    with pytest.raises(sqlalchemy.exc.DBAPIError, match="permission"):
        with transaccion() as cnx:
            cnx.exec_driver_sql("DELETE FROM Demo_Lineas")
    with pytest.raises(sqlalchemy.exc.DBAPIError, match="permission"):
        with transaccion() as cnx:
            cnx.exec_driver_sql("CREATE TABLE Intrusa (x INT)")


def test_login_de_las_cuentas_demo(base_demo):
    usuario, error = autenticar("demo.operador", PASSWORD_DEMO, bloquear=False)
    assert error is None and usuario.areas == {"Ingenieria", "Planeacion"}
    assert not usuario.debe_cambiar_password

    # Sin bloqueo (modo demo): fallar muchas veces no impide entrar.
    for _ in range(MAX_INTENTOS + 1):
        assert autenticar("demo.operador", "mala", bloquear=False)[0] is None
    assert autenticar("demo.operador", PASSWORD_DEMO, bloquear=False)[0] is not None

    # Con bloqueo (producción): la cuenta queda bloqueada.
    for _ in range(MAX_INTENTOS):
        autenticar("demo.consulta", "mala")
    usuario, error = autenticar("demo.consulta", PASSWORD_DEMO)
    assert usuario is None and "bloqueada" in error


def test_restablecimiento_diario(base_demo, sql_admin):
    # Recién instalada, hoy ya está "restablecida".
    assert reiniciar_si_toca() is False

    sql_admin("UPDATE Demo_Control SET Ultimo_Reinicio = NULL")
    assert reiniciar_si_toca() is True
    assert reiniciar_si_toca() is False

    # Todo vuelve al estado inicial: estados, historial, auditoría y bloqueos.
    datos = base_demo["datos"]
    estados = leer_sql("SELECT pedconsecutivo, producto, Estado_SDBR FROM SDBR_MOV")
    iniciales = {
        (e["pedconsecutivo"], e["producto"]): e["Estado_SDBR"] for e in datos.estados
    }
    assert (
        dict(
            zip(
                zip(estados["pedconsecutivo"], estados["producto"]),
                estados["Estado_SDBR"],
            )
        )
        == iniciales
    )
    assert leer_sql("SELECT COUNT(*) AS n FROM Mov_Tiempo_Real3")["n"][0] == len(
        datos.historial
    )
    assert (
        leer_sql("SELECT COUNT(*) AS n FROM SDBR_Auditoria WHERE Accion = 'mover'")[
            "n"
        ][0]
        == 0
    )
    assert autenticar("demo.consulta", PASSWORD_DEMO)[0] is not None


def test_la_web_de_punta_a_punta(base_demo):
    cliente = base_demo["app"].server.test_client()
    pagina = cliente.get("/login").get_data(as_text=True)
    assert "Cuentas de la demo" in pagina and "/assets/logo_sdbr.svg" in pagina
    r = cliente.post(
        "/login",
        data={"usuario": "demo.operador", "password": PASSWORD_DEMO, "next": "/ingenieria"},
    )
    assert r.status_code == 302 and r.headers["Location"] == "/ingenieria"
    assert cliente.get("/ingenieria").status_code == 200
    assert "datos ficticios" in cliente.get("/_dash-layout").get_data(as_text=True)
    assert cliente.get("/cambiar-password").status_code == 200  # aviso, sin formulario
