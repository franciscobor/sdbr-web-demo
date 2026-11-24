###############################################################################################
########################## CONSULTA COMPARTIDA DE PEDIDOS EN PLANTA ###########################
###############################################################################################
# Portada de sdbr/nucleo/pedidos.py. La vista Pedidos_Fechas_Fin2_V3 no es sargable por
# Estado_Final/Estado_SDBR: cada consulta cuesta ~1,5 s fijos (ver DIAGNOSTICO_RENDIMIENTO.md).
# Se hace una sola consulta con el superconjunto Estado_Final='En_planta' y cada pantalla filtra
# en memoria.
#
# En la web la caché vive en el único proceso del servidor y la comparten TODOS los usuarios:
# la vista se consulta como mucho una vez cada CACHE_TTL_SEG, no una vez por puesto. Por eso el
# servidor no debe levantarse con varios procesos: cada uno tendría su caché y las
# invalidaciones de un proceso no se verían en los demás.
#
# Importar siempre como `from sdbr_web.datos.pedidos import ...` (una sola ruta de import, una
# sola caché).

import threading
import time

from sdbr_web.datos.conexion import leer_sql

CACHE_TTL_SEG = 10
_CACHE_LOCK = threading.Lock()
_cache = {"df": None, "ts": 0.0}

CONSULTA_PEDIDOS = (
    "SELECT * FROM Pedidos_Fechas_Fin2_V3 WHERE Estado_Final = 'En_planta'"
)


def cargar_pedidos_en_planta(forzar=False):
    """DataFrame crudo de los pedidos en planta. No se modifica: las pantallas trabajan con copias."""
    with (
        _CACHE_LOCK
    ):  # serializa la consulta: diez usuarios a la vez no lanzan diez consultas
        ahora = time.monotonic()
        if (
            not forzar
            and _cache["df"] is not None
            and ahora - _cache["ts"] < CACHE_TTL_SEG
        ):
            return _cache["df"]
        df = leer_sql(CONSULTA_PEDIDOS)
        _cache["df"] = df
        _cache["ts"] = ahora
        return df


def invalidar_cache_pedidos():
    """Obligatorio tras cualquier escritura que cambie Estado_SDBR."""
    with _CACHE_LOCK:
        _cache["df"] = None


def filas_del_pedido(crudo, pedido):
    """Filas de un pedido dentro de un DataFrame crudo ya cargado."""
    return crudo[crudo["pedconsecutivo"].astype(str).str.strip() == str(pedido).strip()]


def datos_del_pedido(pedido):
    """Filas del pedido desde la consulta compartida."""
    return filas_del_pedido(cargar_pedidos_en_planta(), pedido)
