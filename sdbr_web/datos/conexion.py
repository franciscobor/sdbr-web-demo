###############################################################################################
################################ CONEXIÓN A SQL SERVER (POOL) #################################
###############################################################################################
# Sustituye a las conexiones globales de la versión de escritorio (nucleo/conexiones.py).
#
# Regla de la web: NADIE comparte conexiones. Cada callback pide una al pool con leer_sql() o
# transaccion() y la devuelve al terminar. pyodbc declara threadsafety=1 y Waitress atiende cada
# petición en un hilo distinto, así que una conexión global se corrompería con dos usuarios a la vez.
#
# Toda consulta va PARAMETRIZADA (text() con :nombre). El navegador puede mandar cualquier cosa:
# nada que venga de él se concatena en una sentencia.

import logging
import threading
import time
from contextlib import contextmanager

import pandas as pd
import pyodbc
from sqlalchemy import create_engine, event, text

registro_log = logging.getLogger(__name__)

_engine = None
_LOCK = threading.Lock()
_config = None

# Solo en modo demo: Azure SQL con la oferta gratuita se pausa sola y la primera conexión tras la
# pausa falla con 40613 mientras la base despierta (menos de un minuto). En producción NO se
# reintenta: varios fallos de login seguidos podrían bloquear la cuenta que usa toda la planta.
ERRORES_DE_ARRANQUE = ("40613", "40197", "40501", "49918", "49919", "49920")
PLAZO_ARRANQUE_SEG = 60
ESPERA_ENTRE_INTENTOS_SEG = 5


def es_error_de_arranque(exc):
    texto = str(exc)
    return any(codigo in texto for codigo in ERRORES_DE_ARRANQUE)


def conectar_con_reintentos(
    conectar,
    plazo_seg=PLAZO_ARRANQUE_SEG,
    espera_seg=ESPERA_ENTRE_INTENTOS_SEG,
    dormir=time.sleep,
    reloj=time.monotonic,
):
    """Llama a conectar() hasta que funcione, mientras el error sea de base en pausa y quede plazo."""
    limite = reloj() + plazo_seg
    while True:
        try:
            return conectar()
        except pyodbc.Error as exc:
            if not es_error_de_arranque(exc) or reloj() + espera_seg > limite:
                raise
            registro_log.warning(
                "La base de datos está despertando; nuevo intento en %s s", espera_seg
            )
            dormir(espera_seg)


def configurar(config):
    """Fija la configuración; el engine se crea en la primera consulta."""
    global _config, _engine
    with _LOCK:
        _config = config
        if _engine is not None:
            _engine.dispose()
            _engine = None


def obtener_engine():
    global _engine
    with _LOCK:
        if _engine is None:
            if _config is None:
                raise RuntimeError(
                    "La conexión a SQL Server no está configurada: llame a configurar()."
                )
            # La conexión se crea con `creator` y no con URL(odbc_connect=...): el dialecto pyodbc
            # de SQLAlchemy le aplica unquote_plus a odbc_connect y un '+' de la contraseña llega
            # al servidor como un espacio ("Login failed for user").
            cadena = _config.cadena_odbc
            if getattr(_config, "modo_demo", False):

                def crear_conexion():
                    return conectar_con_reintentos(lambda: pyodbc.connect(cadena))

            else:

                def crear_conexion():
                    return pyodbc.connect(cadena)

            engine = create_engine(
                "mssql+pyodbc://",
                creator=crear_conexion,
                pool_size=10,
                max_overflow=10,
                pool_pre_ping=True,  # descarta conexiones que SQL Server cerró por inactividad
                pool_recycle=1800,
            )
            timeout = _config.sql_timeout_seg

            @event.listens_for(engine, "connect")
            def _fijar_timeout(conexion_dbapi, _registro):
                # Tiempo máximo por sentencia: una base bloqueada devuelve un error en vez de
                # dejar colgado el hilo de Waitress (equivale a TIMEOUT_ESCRITURA_SEG del escritorio).
                conexion_dbapi.timeout = timeout

            _engine = engine
        return _engine


def leer_sql(consulta, parametros=None):
    """Ejecuta un SELECT y devuelve un DataFrame."""
    with obtener_engine().connect() as conexion:
        return pd.read_sql(text(consulta), conexion, params=parametros or {})


@contextmanager
def transaccion():
    """Conexión con una transacción abierta: commit al salir, rollback si hay una excepción."""
    with obtener_engine().begin() as conexion:
        yield conexion


def es_error_de_timeout(exc):
    texto = str(exc).lower()
    return "hyt00" in texto or "timeout" in texto or "tiempo de espera" in texto


def motivo_breve(exc):
    """Resume un error de la base para mostrarlo en una lista (portado de nucleo/movimientos.py)."""
    if es_error_de_timeout(exc):
        return "base de datos ocupada (tiempo de espera agotado)"
    if es_error_de_arranque(exc):
        return "la base de datos se está activando; vuelva a intentarlo en un minuto"
    texto = str(getattr(exc, "orig", exc)).replace("\n", " ").replace("\r", " ")
    return texto[:120] + ("..." if len(texto) > 120 else "")
