"""Generador e instalador de la demo, sin base de datos."""

import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from demo import instalar
from demo.generar_datos import AREAS_FLUJO, DEROGACION, FECHA_Y_LEAD, generar
from sdbr_web.dominio.buffer import (
    BLANCO,
    NEGRO,
    SIN_DATO,
    calcular_buffer,
    zona_de_buffer,
)

RAIZ = Path(__file__).resolve().parent.parent
HOY = date(2026, 11, 24)


@pytest.fixture(scope="module")
def datos():
    return generar(hoy=HOY)


def _en_planta(datos):
    lineas = pd.DataFrame(datos.lineas)
    estados = pd.DataFrame(datos.estados).rename(columns={"producto": "Producto"})
    df = lineas.merge(estados, on=["pedconsecutivo", "Producto"])
    return df[df["Estado_Final"] == "En_planta"]


def test_es_reproducible(datos):
    otra = generar(hoy=HOY)
    assert otra.lineas == datos.lineas and otra.historial == datos.historial
    assert generar(hoy=HOY, semilla=1).lineas != datos.lineas


def test_volumen_y_claves(datos):
    pedidos = {fila["pedconsecutivo"] for fila in datos.lineas}
    assert len(pedidos) == 150 and 300 <= len(datos.lineas) <= 600
    claves = [(f["pedconsecutivo"], f["Producto"]) for f in datos.lineas]
    assert len(claves) == len(set(claves))
    assert {e["Estado_SDBR"] for e in datos.estados} == set(AREAS_FLUJO) | {DEROGACION}


def test_fechas_coherentes(datos):
    medianoche = datetime.combine(HOY, datetime.min.time())
    for fila in datos.lineas:
        assert fila["FechaDocumen"] <= medianoche  # ningún pedido del futuro
        assert fila["FechaDocumen"] < fila["Fecha_Venci_Espejo"]
        assert (
            fila["Final_Inge"]
            <= fila["Final_Plane"]
            <= fila["Final_Compras"]
            <= fila["Fecha_Venci_Espejo"]
        )


def test_ingenieria_tiene_todas_las_zonas(datos):
    df = _en_planta(datos)
    ingenieria = df[df["Estado_SDBR"] == "Ingenieria"].reset_index(drop=True)
    columna_fecha, columna_lead = FECHA_Y_LEAD["Ingenieria"]
    hoy = datetime.combine(HOY, datetime.min.time())
    zonas = Counter(
        zona_de_buffer(calcular_buffer(ingenieria, columna_fecha, columna_lead, hoy))
    )
    assert all(zonas[z] >= 3 for z in range(BLANCO, NEGRO + 1)), zonas
    assert zonas[SIN_DATO] == 2  # buffer no calculable: la web lo deja sin color
    assert (
        ingenieria["NombreFamilia"].isna().sum() >= 1
        or df["NombreFamilia"].isna().any()
    )


def test_historial(datos):
    ahora = datetime.combine(HOY, datetime.min.time()) + timedelta(hours=7)
    estados = {(e["pedconsecutivo"], e["producto"]): e for e in datos.estados}
    movimientos = Counter((h["Pedido"], h["Producto"]) for h in datos.historial)
    for clave, estado in estados.items():
        area = estado["Estado_SDBR"]
        esperado = 1 if area == DEROGACION else AREAS_FLUJO.index(area)
        assert movimientos[clave] == esperado
    assert all(h["Fecha_Mov"] <= ahora for h in datos.historial)
    ultimos = Counter(
        (h["Pedido"], h["Sale_De"])
        for h in datos.historial
        if h["Calificacion"] == "Ultimo"
    )
    assert ultimos and max(ultimos.values()) == 1


# ______________________________________________INSTALADOR__________________________________________


def test_separar_lotes():
    texto = "CREATE TABLE a (x INT);\nGO\n  go  \nCREATE VIEW v AS SELECT 1 AS x;\nGO\n"
    assert instalar.separar_lotes(texto) == [
        "CREATE TABLE a (x INT);",
        "CREATE VIEW v AS SELECT 1 AS x;",
    ]


def test_la_guardia_rechaza_una_base_ajena():
    instalar.comprobar_objetos([])  # base vacía
    instalar.comprobar_objetos(["SDBR_MOV", "Demo_Control"])  # base de demo
    with pytest.raises(instalar.InstalacionRechazada, match="no son de la demo"):
        instalar.comprobar_objetos(["SDBR_MOV", "Tabla_Real", "Vista_Real"])


def test_la_guardia_conoce_todo_lo_que_crean_los_scripts():
    creados = set()
    for script in (RAIZ / "demo" / "sql").glob("*.sql"):
        creados |= set(
            re.findall(
                r"CREATE\s+(?:TABLE|VIEW|PROCEDURE)\s+dbo\.(\w+)",
                script.read_text(encoding="utf-8"),
            )
        )
    assert creados == instalar.OBJETOS_DEMO


def _columnas(texto, tabla):
    bloque = re.search(
        rf"CREATE TABLE dbo\.{tabla} \((.*?)\n\s*\);", texto, re.DOTALL
    ).group(1)
    return re.findall(
        r"^\s+(\w+)\s+(?:INT|BIGINT|NVARCHAR|VARCHAR|BIT|DATETIME2)",
        bloque,
        re.MULTILINE,
    )


@pytest.mark.skipif(
    not (RAIZ / "sql" / "06_usuarios_auditoria.sql").exists(),
    reason="sql/06 solo existe en el repositorio privado",
)
@pytest.mark.parametrize(
    "tabla", ["SDBR_Usuarios", "SDBR_Usuarios_Areas", "SDBR_Auditoria"]
)
def test_tablas_de_usuarios_iguales_que_en_produccion(tabla):
    produccion = (RAIZ / "sql" / "06_usuarios_auditoria.sql").read_text(
        encoding="utf-8"
    )
    demo = (RAIZ / "demo" / "sql" / "02_usuarios_auditoria.sql").read_text(
        encoding="utf-8"
    )
    assert _columnas(demo, tabla) == _columnas(produccion, tabla)


# Credenciales de administrador (y una clave de sesión, para no avisar de que falta).
ADMIN = "SDBR_DEMO_ADMIN_USUARIO=sa\nSDBR_DEMO_ADMIN_PASSWORD=y\nSDBR_SECRET_KEY=x\n"


def _archivo(tmp_path, texto):
    archivo = tmp_path / "demo.env"
    archivo.write_text(texto, encoding="utf-8")
    return archivo


def test_instalar_exige_modo_demo(tmp_path):
    base = "SDBR_SQL_USUARIO=app\nSDBR_SQL_PASSWORD=x\n" + ADMIN
    with pytest.raises(instalar.InstalacionRechazada, match="SDBR_MODO_DEMO"):
        instalar.leer_configuracion(_archivo(tmp_path, base + "SDBR_MODO_DEMO=no\n"))

    config, admin = instalar.leer_configuracion(
        _archivo(tmp_path, base + "SDBR_MODO_DEMO=si\n")
    )
    assert (config.sql_usuario, admin.sql_usuario, admin.sql_password) == (
        "app",
        "sa",
        "y",
    )

    sin_admin = "SDBR_SQL_USUARIO=app\nSDBR_SQL_PASSWORD=x\nSDBR_MODO_DEMO=si\nSDBR_SECRET_KEY=x\n"
    with pytest.raises(instalar.InstalacionRechazada, match="SDBR_DEMO_ADMIN"):
        instalar.leer_configuracion(_archivo(tmp_path, sin_admin))


def test_con_archivo_el_entorno_se_ignora(tmp_path, monkeypatch):
    # Un equipo con las variables de producción en el entorno: no deben colarse.
    monkeypatch.setenv("SDBR_SQL_SERVIDOR", "servidor-de-produccion")
    monkeypatch.setenv("SDBR_SQL_BASE", "BASE_REAL")
    monkeypatch.setenv("SDBR_DEMO_ADMIN_USUARIO", "otro")
    config, admin = instalar.leer_configuracion(
        _archivo(
            tmp_path,
            "SDBR_SQL_SERVIDOR=localhost,14330\nSDBR_SQL_BASE=SDBR_DEMO\n"
            "SDBR_SQL_USUARIO=app\nSDBR_SQL_PASSWORD=x\nSDBR_MODO_DEMO=si\n" + ADMIN,
        )
    )
    assert (config.sql_servidor, config.sql_base, admin.sql_usuario) == (
        "localhost,14330",
        "SDBR_DEMO",
        "sa",
    )


def test_sin_archivo_solo_el_entorno(monkeypatch):
    # conftest ya define usuario, contraseña y servidor en el entorno
    monkeypatch.setenv("SDBR_MODO_DEMO", "si")
    monkeypatch.setenv("SDBR_DEMO_ADMIN_USUARIO", "sa")
    monkeypatch.setenv("SDBR_DEMO_ADMIN_PASSWORD", "y")
    config, admin = instalar.leer_configuracion(None)
    assert (config.sql_servidor, admin.sql_usuario) == (
        "servidor-inexistente-de-pruebas",
        "sa",
    )


def test_archivo_inexistente(tmp_path):
    with pytest.raises(instalar.InstalacionRechazada, match="No existe"):
        instalar.leer_configuracion(tmp_path / "no-esta.env")


@pytest.mark.parametrize(
    "servidor",
    [
        "10.20.30.40",
        "10.20.30.40,1433",
        "192.168.1.10\\SQLEXPRESS",
        "tcp:172.16.0.5,1433",
    ],
)
def test_rechaza_servidores_de_red_privada(servidor):
    with pytest.raises(instalar.InstalacionRechazada, match="red privada"):
        instalar.comprobar_servidor(servidor)


@pytest.mark.parametrize(
    "servidor",
    ["localhost,14330", "127.0.0.1,14330", "sqlserver", "demo.database.windows.net"],
)
def test_admite_docker_y_azure(servidor):
    instalar.comprobar_servidor(servidor)


def test_instalar_rechaza_nombres_raros(tmp_path):
    archivo = _archivo(
        tmp_path,
        "SDBR_SQL_USUARIO=app]; DROP TABLE x; --\nSDBR_SQL_PASSWORD=x\n"
        "SDBR_MODO_DEMO=si\n" + ADMIN,
    )
    with pytest.raises(instalar.InstalacionRechazada, match="SDBR_SQL_USUARIO"):
        instalar.leer_configuracion(archivo)


def test_literal_escapa_comillas():
    assert instalar._literal("a'b") == "N'a''b'"


def test_el_instalador_desactiva_el_pool_de_odbc():
    # Con el pool de unixODBC 2.3.12, el DDL del instalador quedaba sin confirmar (ver instalar.py).
    assert instalar.pyodbc.pooling is False
