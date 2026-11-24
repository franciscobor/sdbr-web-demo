###############################################################################################
################################ INSTALADOR DE LA BASE DE DEMO ################################
###############################################################################################
# Crea (o rehace desde cero) la base de demostración: esquema, datos sintéticos, usuario de la
# aplicación con permisos mínimos y las cuentas compartidas de la web.
#
#   python -m demo.instalar                       # con demo/docker.env (SQL Server de Docker)
#   python -m demo.instalar --env demo/azure.env  # Azure SQL (archivo propio, sin versionar)
#   python -m demo.instalar --solo-reiniciar      # vuelve al estado inicial sin regenerar
#   python -m demo.instalar --entorno             # solo variables del entorno (docker compose)
#
# Lee UNA sola fuente: el archivo indicado (y nada del entorno) o, con --entorno, solo el entorno.
# Nunca las mezcla ni lee el .env de la raíz (el de producción): en un equipo con las variables
# SDBR_* de producción definidas, mezclarlas haría que apuntara a la base real.
#
# GUARDIA: antes de tocar nada comprueba que SDBR_MODO_DEMO es "si" y que la base está vacía o
# solo tiene objetos de la demo. Ante cualquier otro objeto se detiene sin escribir: así no puede
# borrar las tablas de una base real aunque alguien la configure por error.
#
# Necesita, además de las variables SDBR_* de la aplicación, una cuenta con permisos para crear
# objetos: SDBR_DEMO_ADMIN_USUARIO y SDBR_DEMO_ADMIN_PASSWORD (en Docker, "sa"; en Azure SQL, el
# administrador del servidor). La aplicación se conecta después con SDBR_SQL_USUARIO, que este
# script crea con permisos mínimos.

import argparse
import dataclasses
import ipaddress
import os
import re
import sys
from contextlib import closing
from pathlib import Path

import pyodbc
from dotenv import dotenv_values
from sdbr_web.config import (
    SOLO_ARCHIVO,
    SOLO_ENTORNO,
    ErrorDeConfiguracion,
    cargar_configuracion,
)

from demo.generar_datos import SEMILLA, generar

CARPETA_DEMO = Path(__file__).resolve().parent
CARPETA_SQL = CARPETA_DEMO / "sql"
ENV_DOCKER = CARPETA_DEMO / "docker.env"

# Todo lo que crean los scripts de demo/sql. Si la base tiene cualquier otro objeto, no es una
# base de demo y el instalador se niega a seguir.
OBJETOS_DEMO = frozenset(
    {
        "Demo_Control",
        "Demo_Lineas",
        "Demo_Estado_Inicial",
        "Demo_Historial_Inicial",
        "SDBR_MOV",
        "Mov_Tiempo_Real3",
        "vendedores_pedidos",
        "Pedidos_Fechas_Fin2_V3",
        "SDBR_Usuarios",
        "SDBR_Usuarios_Areas",
        "SDBR_Auditoria",
        "Demo_Reiniciar",
        "Demo_Reiniciar_Si_Toca",
    }
)

AZURE_SQL_DATABASE = 5  # SERVERPROPERTY('EngineEdition')
_NOMBRE_SEGURO = re.compile(r"^[A-Za-z0-9_.\-]+$")
_SEPARADOR_GO = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)
SQL_HOY = (
    "SELECT CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'SA Pacific Standard Time' AS DATE)"
)


class InstalacionRechazada(Exception):
    """La configuración o la base no son de demo: no se toca nada."""


# _________________________________________CONFIGURACIÓN_________________________________________


def leer_configuracion(archivo_env):
    """(config de la aplicación, config del administrador).

    Con un archivo, todo sale SOLO de ese archivo; con archivo_env=None, SOLO del entorno (lo que
    hace docker compose). Nunca se mezclan: un equipo de desarrollo puede tener definidas las
    variables SDBR_* de producción, y mezclarlas haría que el instalador apuntara a la base real.
    """
    origen = SOLO_ENTORNO if archivo_env is None else SOLO_ARCHIVO
    try:
        config = cargar_configuracion(archivo_env, origen=origen)
    except ErrorDeConfiguracion as exc:
        raise InstalacionRechazada(str(exc)) from None
    if not config.modo_demo:
        raise InstalacionRechazada(
            "SDBR_MODO_DEMO no es 'si': el instalador solo trabaja contra bases de demo."
        )
    valores = os.environ if archivo_env is None else dotenv_values(archivo_env)
    usuario = (valores.get("SDBR_DEMO_ADMIN_USUARIO") or "").strip()
    password = valores.get("SDBR_DEMO_ADMIN_PASSWORD") or ""
    if not usuario or not password:
        raise InstalacionRechazada(
            "Faltan SDBR_DEMO_ADMIN_USUARIO o SDBR_DEMO_ADMIN_PASSWORD (cuenta que crea la base)."
        )
    comprobar_servidor(config.sql_servidor)
    for nombre, valor in (
        ("SDBR_SQL_BASE", config.sql_base),
        ("SDBR_SQL_USUARIO", config.sql_usuario),
    ):
        if not _NOMBRE_SEGURO.match(valor):
            raise InstalacionRechazada(
                f"{nombre} solo admite letras, números, '_', '.' y '-'."
            )
    admin = dataclasses.replace(config, sql_usuario=usuario, sql_password=password)
    return config, admin


def comprobar_servidor(servidor):
    """La demo va en Docker local o en Azure: nunca en un servidor de una red privada.

    Rechaza IP de redes privadas (10.x, 172.16-31.x, 192.168.x...) aunque todo lo demás parezca
    de demo: es donde suelen estar las bases reales de una empresa.
    """
    # "host", "host,puerto", "host\instancia" o "tcp:host,puerto"
    host = re.split(r"[,\\]", servidor.strip())[0].removeprefix("tcp:")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return  # un nombre: localhost, el servicio de compose o *.database.windows.net
    if ip.is_private and not ip.is_loopback:
        raise InstalacionRechazada(
            f"El servidor {host} está en una red privada: la demo solo se instala en Docker "
            "local (localhost) o en Azure SQL."
        )


def separar_lotes(texto):
    """Parte un script de SSMS en los lotes separados por GO."""
    return [lote.strip() for lote in _SEPARADOR_GO.split(texto) if lote.strip()]


def comprobar_objetos(nombres):
    """Lanza InstalacionRechazada si hay algún objeto que no sea de la demo."""
    ajenos = sorted(set(nombres) - OBJETOS_DEMO)
    if ajenos:
        muestra = ", ".join(ajenos[:5]) + (" ..." if len(ajenos) > 5 else "")
        raise InstalacionRechazada(
            f"La base tiene {len(ajenos)} objetos que no son de la demo ({muestra}). "
            "Por seguridad no se toca: use una base vacía."
        )


def _literal(texto):
    """Texto como literal de T-SQL (solo para la contraseña del DDL, que no admite parámetros)."""
    return "N'" + texto.replace("'", "''") + "'"


# ___________________________________________BASE DE DATOS_________________________________________


def _conectar(config, base=None, autocommit=False):
    if base:
        config = dataclasses.replace(config, sql_base=base)
    return pyodbc.connect(config.cadena_odbc, autocommit=autocommit, timeout=60)


def asegurar_base(admin):
    """Crea la base si no existe (solo en SQL Server; en Azure se crea en el portal)."""
    with closing(_conectar(admin, base="master", autocommit=True)) as conexion:
        edicion = conexion.execute(
            "SELECT CAST(SERVERPROPERTY('EngineEdition') AS INT)"
        ).fetchval()
        existe = (
            conexion.execute("SELECT DB_ID(?)", admin.sql_base).fetchval() is not None
        )
        if not existe:
            if edicion == AZURE_SQL_DATABASE:
                raise InstalacionRechazada(
                    f"La base {admin.sql_base} no existe. En Azure se crea desde el portal con la "
                    "oferta gratuita (ver demo/DESPLIEGUE_AZURE.md): este script no crea bases "
                    "de pago."
                )
            conexion.execute(f"CREATE DATABASE [{admin.sql_base}]")
            print(f"Base {admin.sql_base} creada.")
    return edicion


def _objetos_de_usuario(cursor):
    return [
        fila[0]
        for fila in cursor.execute(
            "SELECT name FROM sys.objects WHERE is_ms_shipped = 0 "
            "AND type IN ('U', 'V', 'P', 'FN', 'IF', 'TF', 'TR')"
        ).fetchall()
    ]


def _ejecutar_scripts(cursor):
    for script in sorted(CARPETA_SQL.glob("*.sql")):
        for lote in separar_lotes(script.read_text(encoding="utf-8")):
            cursor.execute(lote)


def _insertar(cursor, tabla, filas):
    if not filas:
        return
    columnas = list(filas[0])
    sql = (
        f"INSERT INTO dbo.{tabla} ({', '.join(columnas)}) "
        f"VALUES ({', '.join('?' for _ in columnas)})"
    )
    cursor.fast_executemany = True
    cursor.executemany(sql, [tuple(fila[c] for c in columnas) for fila in filas])


def _cargar_datos(cursor, semilla):
    hoy = cursor.execute(SQL_HOY).fetchval()
    datos = generar(hoy=hoy, semilla=semilla)
    cursor.execute(
        "INSERT INTO dbo.Demo_Control (Id, Fecha_Generacion, Ultimo_Reinicio, Semilla) "
        "VALUES (1, ?, ?, ?)",
        hoy,
        hoy,
        semilla,
    )
    _insertar(cursor, "Demo_Lineas", datos.lineas)
    _insertar(cursor, "SDBR_MOV", datos.estados)
    _insertar(cursor, "Demo_Estado_Inicial", datos.estados)
    _insertar(cursor, "Mov_Tiempo_Real3", datos.historial)
    _insertar(cursor, "Demo_Historial_Inicial", datos.historial)
    _insertar(cursor, "vendedores_pedidos", datos.vendedores)
    return datos


def _crear_usuario_aplicacion(admin, config, edicion):
    """El login de la web, con los permisos justos (como la cuenta de solo lectura de producción)."""
    if config.sql_usuario.lower() == admin.sql_usuario.lower():
        print("Aviso: la aplicación usará la cuenta de administrador (no recomendado).")
        return
    usuario = f"[{config.sql_usuario}]"
    nombre = _literal(config.sql_usuario)
    password = _literal(config.sql_password)
    with closing(_conectar(admin, autocommit=True)) as conexion:
        if edicion == AZURE_SQL_DATABASE:
            # Usuario contenido: vive en la base, sin login en master.
            conexion.execute(
                f"IF USER_ID({nombre}) IS NULL CREATE USER {usuario} WITH PASSWORD = {password} "
                f"ELSE ALTER USER {usuario} WITH PASSWORD = {password}"
            )
        else:
            conexion.execute(
                f"IF SUSER_ID({nombre}) IS NULL CREATE LOGIN {usuario} WITH PASSWORD = {password} "
                f"ELSE ALTER LOGIN {usuario} WITH PASSWORD = {password}"
            )
            conexion.execute(
                f"IF USER_ID({nombre}) IS NULL CREATE USER {usuario} FOR LOGIN {usuario}"
            )
        for sentencia in (
            f"ALTER ROLE db_datareader ADD MEMBER {usuario}",
            f"GRANT UPDATE ON dbo.SDBR_MOV TO {usuario}",
            f"GRANT INSERT, UPDATE ON dbo.Mov_Tiempo_Real3 TO {usuario}",
            f"GRANT INSERT, UPDATE, DELETE ON dbo.SDBR_Usuarios TO {usuario}",
            f"GRANT INSERT, DELETE ON dbo.SDBR_Usuarios_Areas TO {usuario}",
            f"GRANT INSERT ON dbo.SDBR_Auditoria TO {usuario}",
            f"GRANT EXECUTE ON dbo.Demo_Reiniciar_Si_Toca TO {usuario}",
        ):
            conexion.execute(sentencia)


def _crear_cuentas_web(admin):
    # Se importan aquí: sdbr_web.datos usa el pool de la aplicación, que se configura con la
    # cuenta de administrador solo para este paso.
    from sdbr_web.datos import conexion
    from sdbr_web.datos.demo import CUENTAS_DEMO, PASSWORD_DEMO
    from sdbr_web.datos.usuarios import crear_usuario

    conexion.configurar(admin)
    try:
        for usuario, nombre, rol, areas, _texto in CUENTAS_DEMO:
            crear_usuario(
                usuario,
                nombre,
                PASSWORD_DEMO,
                rol,
                areas,
                debe_cambiar=False,
                creado_por="instalador_demo",
            )
    finally:
        conexion.configurar(None)


def instalar(config, admin, semilla=SEMILLA):
    """Rehace la base de demo desde cero. Devuelve los datos generados."""
    edicion = asegurar_base(admin)
    with closing(_conectar(admin)) as conexion:
        cursor = conexion.cursor()
        comprobar_objetos(_objetos_de_usuario(cursor))
        _ejecutar_scripts(cursor)
        datos = _cargar_datos(cursor, semilla)
        conexion.commit()
    _crear_usuario_aplicacion(admin, config, edicion)
    _crear_cuentas_web(admin)
    return datos


def solo_reiniciar(admin):
    with closing(_conectar(admin)) as conexion:
        cursor = conexion.cursor()
        comprobar_objetos(_objetos_de_usuario(cursor))
        if "Demo_Control" not in _objetos_de_usuario(cursor):
            raise InstalacionRechazada("La base de demo no está instalada.")
        cursor.execute("EXEC dbo.Demo_Reiniciar")
        conexion.commit()


def main(argumentos=None):
    analizador = argparse.ArgumentParser(
        description="Instala la base de la demo de SDBR Web"
    )
    fuente = analizador.add_mutually_exclusive_group()
    fuente.add_argument(
        "--env",
        type=Path,
        default=ENV_DOCKER,
        help="archivo con las variables, que se lee SOLO a él (por defecto demo/docker.env)",
    )
    fuente.add_argument(
        "--entorno",
        action="store_true",
        help="lee SOLO las variables del entorno (docker compose, CI); ignora cualquier archivo",
    )
    analizador.add_argument("--semilla", type=int, default=SEMILLA)
    analizador.add_argument(
        "--solo-reiniciar",
        action="store_true",
        help="vuelve al estado inicial sin regenerar los datos",
    )
    args = analizador.parse_args(argumentos)
    try:
        config, admin = leer_configuracion(None if args.entorno else args.env)
        if args.solo_reiniciar:
            solo_reiniciar(admin)
            print("Demo restablecida a su estado inicial.")
            return 0
        datos = instalar(config, admin, args.semilla)
    except InstalacionRechazada as exc:
        print(f"Instalación rechazada: {exc}", file=sys.stderr)
        return 2
    pedidos = len({fila["pedconsecutivo"] for fila in datos.lineas})
    print(
        f"Demo instalada en {config.sql_servidor}/{config.sql_base}: {pedidos} pedidos, "
        f"{len(datos.lineas)} líneas y {len(datos.historial)} movimientos "
        f"(semilla {datos.semilla}, {datos.fecha_generacion})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
