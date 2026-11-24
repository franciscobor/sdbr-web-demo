###############################################################################################
############################################ AUDITORÍA ########################################
###############################################################################################
# Cada escritura hecha desde la web deja una fila en SDBR_Auditoria con el usuario que la hizo.
# Se registra en la MISMA transacción que la escritura: si una falla, no queda la otra.

import json

from sqlalchemy import text

SQL_AUDITORIA = (
    "INSERT INTO SDBR_Auditoria (Usuario, Accion, Pedido, Producto, Origen, Destino, Detalle) "
    "VALUES (:usuario, :accion, :pedido, :producto, :origen, :destino, :detalle)"
)


def registrar(
    conexion,
    usuario,
    accion,
    pedido=None,
    producto=None,
    origen=None,
    destino=None,
    detalle=None,
):
    """Añade la fila de auditoría usando la conexión (y la transacción) de la escritura."""
    conexion.execute(
        text(SQL_AUDITORIA),
        {
            "usuario": usuario,
            "accion": accion,
            "pedido": pedido,
            "producto": producto,
            "origen": origen,
            "destino": destino,
            "detalle": json.dumps(detalle, ensure_ascii=False, default=str)
            if detalle
            else None,
        },
    )
