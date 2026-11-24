###############################################################################################
############################ EJECUCIÓN DE LOS MOVIMIENTOS ENTRE ÁREAS ##########################
###############################################################################################
# Ejecuta los trabajos que arma sdbr_web/dominio/movimientos.py.
#
# Diferencia con escritorio: allí las conexiones iban con autocommit y un fallo entre el UPDATE y
# el INSERT dejaba el movimiento a medias. Aquí cada trabajo (UPDATE + reclasificación + INSERT +
# auditoría) es UNA transacción: o se escribe entero o no se escribe nada.
#
# Igual que en escritorio, un trabajo que falla no detiene a los demás, salvo un tiempo de espera
# agotado: si la base está bloqueada, insistir con el resto solo alarga la espera del usuario.

import logging

from sqlalchemy import text

from sdbr_web.datos import auditoria
from sdbr_web.datos.conexion import es_error_de_timeout, motivo_breve, transaccion
from sdbr_web.datos.pedidos import invalidar_cache_pedidos
from sdbr_web.dominio.areas import a_pantalla

registro_log = logging.getLogger(__name__)


class LineaYaMovida(Exception):
    """El UPDATE no encontró la línea en el área de origen: otro usuario la movió antes."""


def ejecutar_trabajos(trabajos, usuario, accion):
    """Ejecuta cada trabajo en su transacción. Devuelve (movidos, fallos).

    fallos es una lista de (pedido, producto, motivo). La caché de pedidos se invalida siempre,
    también si todo falló: el fallo puede venir de datos desfasados.
    """
    movidos, fallos = [], []
    try:
        for posicion, trabajo in enumerate(trabajos):
            try:
                with transaccion() as conexion:
                    for sentencia in trabajo.sentencias:
                        resultado = conexion.execute(
                            text(sentencia.sql), sentencia.parametros
                        )
                        if sentencia.exige_filas and resultado.rowcount == 0:
                            raise LineaYaMovida(
                                f"ya no estaba en {a_pantalla(trabajo.origen)} "
                                "(¿la movió otro usuario?)"
                            )
                    auditoria.registrar(
                        conexion,
                        usuario,
                        accion,
                        trabajo.pedido,
                        trabajo.producto,
                        trabajo.origen,
                        trabajo.destino,
                        trabajo.detalle,
                    )
                movidos.append(trabajo)
            except LineaYaMovida as exc:
                fallos.append((trabajo.pedido, trabajo.producto, str(exc)))
            except Exception as exc:
                registro_log.exception(
                    "Fallo al mover %s / %s", trabajo.pedido, trabajo.producto
                )
                fallos.append((trabajo.pedido, trabajo.producto, motivo_breve(exc)))
                if es_error_de_timeout(exc):
                    for resto in trabajos[posicion + 1 :]:
                        fallos.append(
                            (
                                resto.pedido,
                                resto.producto,
                                "no se intentó: la base de datos está ocupada",
                            )
                        )
                    break
    finally:
        invalidar_cache_pedidos()
    return movidos, fallos
