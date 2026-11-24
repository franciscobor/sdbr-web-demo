###############################################################################################
####################### CONSTRUCCIÓN DE LOS MOVIMIENTOS ENTRE ÁREAS (PURO) ####################
###############################################################################################
# Portado de sdbr/nucleo/lote.py (_construir_trabajos, _paso_flujo), de
# sdbr/modelos/modelo_global2.py (Contra Flujo) y de modelo_almacen_mp.py / modelo_almacen_pi.py.
#
# Estas funciones NO tocan la base: reciben las líneas marcadas y los datos ya cargados y
# devuelven las sentencias (parametrizadas) de cada trabajo. Las ejecuta
# sdbr_web/datos/movimientos.py, cada trabajo en su propia transacción.
#
# Un movimiento suelto (doble clic) es un lote de una línea, igual que en escritorio.
#
# Se conserva la escritura de escritorio valor a valor (mismas columnas y mismos textos, fechas
# incluidas como 'AAAA-MM-DD HH:MM:SS'), con dos cambios:
#   1. Todo va parametrizado: ningún valor se concatena en el SQL.
#   2. El UPDATE de SDBR_MOV exige que la línea siga en el área de origen (AND Estado_SDBR =
#      :origen) y el trabajo falla si no actualiza nada. Así dos usuarios no pueden mover la
#      misma línea a la vez, y el LIKE del producto ya no arrastra líneas de otras áreas.
#
# Se conserva a propósito `producto LIKE '%<producto>%'` (paridad con escritorio, de lo que
# depende la simulación de Parcial/Último). Es un riesgo señalado: un código contenido en otro
# mueve las dos líneas si están en la misma área.

from dataclasses import dataclass, field

import pandas as pd

FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"

# Cómo reclasifica cada pantalla la salida 'Ultimo' anterior del área (ver _paso_flujo en lote.py).
NUNCA, SIEMPRE, A_TIEMPO = "nunca", "siempre", "a_tiempo"

SQL_MOVER = (
    "UPDATE SDBR_MOV SET Estado_SDBR = :destino "
    "WHERE pedconsecutivo = :pedido AND producto LIKE :patron AND Estado_SDBR = :origen"
)
SQL_HISTORIAL = (
    "INSERT INTO Mov_Tiempo_Real3 (Fecha_Mov, Pedido, Producto, Sale_De, Entra_A, Fecha_PSL, "
    "Tiempo_Pedido, On_time, Buffer_Zona, Retroceso, Calificacion) VALUES (:fecha, :pedido, "
    ":producto, :origen, :destino, :fecha_psl, :buffer_global, :on_time, :buffer_zona, "
    ":retroceso, :calificacion)"
)
# Si al pedido le quedaba UNA sola salida 'Ultimo' de esta área, deja de serlo porque ahora sale
# otra línea. En escritorio era un SELECT seguido de un UPDATE condicional; aquí es una sola
# sentencia con el mismo efecto.
SQL_RECLASIFICAR = (
    "UPDATE Mov_Tiempo_Real3 SET Calificacion = 'Parcial' "
    "WHERE Pedido = :pedido AND Calificacion = 'Ultimo' AND Sale_De = :origen "
    "AND (SELECT COUNT(*) FROM Mov_Tiempo_Real3 "
    "WHERE Pedido = :pedido AND Calificacion = 'Ultimo' AND Sale_De = :origen) = 1"
)
# Contra Flujo: si el pedido ya había salido hacia adelante del área a la que ahora vuelve, esa
# calificación deja de ser definitiva.
SQL_RECLASIFICAR_CONTRA_FLUJO = (
    "UPDATE Mov_Tiempo_Real3 SET Calificacion = 'Parcial' "
    "WHERE Pedido = :pedido AND Producto LIKE :patron AND EXISTS (SELECT 1 FROM Mov_Tiempo_Real3 "
    "WHERE Sale_De = :destino AND Retroceso = 'No' AND Pedido = :pedido)"
)
SQL_ENTREGA_PI = (
    "UPDATE Entrega_PI_Ensamble SET Estado_PI_Ensamble = :destino, Fecha = :fecha "
    "WHERE Pedido = :pedido AND producto LIKE :patron AND OP = :op"
)


@dataclass(frozen=True)
class Registro:
    """Una línea marcada en la pantalla, con el buffer recalculado en el servidor."""

    pedido: str
    producto: str
    buffer: object = None  # int, o None/NA si no se pudo calcular
    origen: str = None  # Contra Flujo: área en la que está la línea
    op: str = None  # Almacén PI


@dataclass(frozen=True)
class Sentencia:
    sql: str
    parametros: dict
    exige_filas: bool = (
        False  # si no afecta a ninguna fila, el trabajo falla y se revierte
    )


@dataclass
class Trabajo:
    pedido: str
    producto: str
    origen: str
    destino: str
    sentencias: list
    detalle: dict = field(default_factory=dict)  # va a SDBR_Auditoria


def patron_producto(producto):
    return "%" + producto + "%"


def deduplicar(registros, claves=("pedido", "producto")):
    """Quita los registros repetidos conservando el orden (el orden decide quién es 'Ultimo')."""
    vistos = set()
    unicos = []
    for registro in registros:
        clave = tuple(getattr(registro, nombre) for nombre in claves)
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(registro)
    return unicos


def datos_globales(filas_pedido):
    """(buffer global, fecha PSL) del pedido como los escribe escritorio, o None si no está."""
    unicos = filas_pedido[
        ["pedconsecutivo", "Buffer", "Fecha_Venci_Espejo"]
    ].drop_duplicates()
    if unicos.empty:
        return None
    ultima = unicos.iloc[-1]
    fecha_psl = pd.to_datetime(ultima["Fecha_Venci_Espejo"])
    return str(ultima["Buffer"]), fecha_psl.strftime(FORMATO_FECHA)


def _buffer_valido(registro):
    return registro.buffer is not None and not pd.isna(registro.buffer)


def _sentencia_historial(
    fecha, registro, origen, destino, globales, on_time, retroceso, calificacion
):
    buffer_global, fecha_psl = globales
    return Sentencia(
        SQL_HISTORIAL,
        {
            "fecha": fecha,
            "pedido": registro.pedido,
            "producto": registro.producto,
            "origen": origen,
            "destino": destino,
            "fecha_psl": fecha_psl,
            "buffer_global": buffer_global,
            "on_time": str(on_time),
            "buffer_zona": str(int(registro.buffer)),
            "retroceso": retroceso,
            "calificacion": calificacion,
        },
    )


def _sentencia_mover(registro, origen, destino):
    return Sentencia(
        SQL_MOVER,
        {
            "destino": destino,
            "pedido": registro.pedido,
            "patron": patron_producto(registro.producto),
            "origen": origen,
        },
        exige_filas=True,
    )


def construir_trabajos_flujo(
    registros, *, origen, destino, retroceso, reclasifica, filas_de_pedido, ahora
):
    """Flujo estándar: Ingeniería, Ops, Almacén, Producción y Derogaciones.

    filas_de_pedido(pedido) devuelve las filas crudas de Pedidos_Fechas_Fin2_V3 del pedido.
    Devuelve (trabajos, descartes); descartes es una lista de (pedido, producto, motivo).
    """
    fecha = ahora.strftime(FORMATO_FECHA)
    trabajos, descartes = [], []
    globales_por_pedido = {}
    pendientes = {}  # pedido -> {índice: producto} de las líneas que siguen en el área

    for registro in deduplicar(registros):
        ped = registro.pedido
        if ped not in globales_por_pedido:
            filas = filas_de_pedido(ped)
            globales_por_pedido[ped] = datos_globales(filas)
            en_area = filas[filas["Estado_SDBR"] == origen]
            pendientes[ped] = dict(
                zip(en_area.index, en_area["Producto"].astype(str).fillna(""))
            )
        globales = globales_por_pedido[ped]
        if globales is None:
            descartes.append(
                (
                    ped,
                    registro.producto,
                    "el pedido ya no aparece entre los pedidos en planta",
                )
            )
            continue
        if not _buffer_valido(registro):
            descartes.append(
                (ped, registro.producto, "la línea no tiene un buffer calculable")
            )
            continue

        # Parcial o Último: se simula la secuencia de moverlas de una en una en este orden.
        restantes = pendientes[ped]
        calificacion = "Ultimo" if len(restantes) == 1 else "Parcial"
        for indice in [
            i for i, nombre in restantes.items() if registro.producto in nombre
        ]:
            restantes.pop(indice, None)

        if int(registro.buffer) > 100:
            on_time = 0
            reclasificar = reclasifica == SIEMPRE
        else:
            on_time = 1
            reclasificar = reclasifica in (SIEMPRE, A_TIEMPO)

        sentencias = [_sentencia_mover(registro, origen, destino)]
        if reclasificar:
            sentencias.append(
                Sentencia(SQL_RECLASIFICAR, {"pedido": ped, "origen": origen})
            )
        sentencias.append(
            _sentencia_historial(
                fecha,
                registro,
                origen,
                destino,
                globales,
                on_time,
                retroceso,
                calificacion,
            )
        )
        trabajos.append(
            Trabajo(
                ped,
                registro.producto,
                origen,
                destino,
                sentencias,
                {
                    "calificacion": calificacion,
                    "on_time": on_time,
                    "buffer": int(registro.buffer),
                    "retroceso": retroceso,
                },
            )
        )
    return trabajos, descartes


def construir_trabajos_contra_flujo(registros, *, destino, filas_de_pedido, ahora):
    """Contra Flujo: el origen sale de cada línea, siempre 'Parcial' y Retroceso='Si'."""
    fecha = ahora.strftime(FORMATO_FECHA)
    trabajos, descartes = [], []
    globales_por_pedido = {}

    for registro in deduplicar(registros):
        ped, prod, origen = registro.pedido, registro.producto, registro.origen
        if origen == destino:
            descartes.append((ped, prod, "ya está en el área de destino"))
            continue
        if ped not in globales_por_pedido:
            globales_por_pedido[ped] = datos_globales(filas_de_pedido(ped))
        globales = globales_por_pedido[ped]
        if globales is None:
            descartes.append(
                (ped, prod, "el pedido ya no aparece entre los pedidos en planta")
            )
            continue
        if not _buffer_valido(registro):
            descartes.append((ped, prod, "la línea no tiene un buffer calculable"))
            continue

        on_time = 0 if int(registro.buffer) > 100 else 1
        sentencias = [
            Sentencia(
                SQL_RECLASIFICAR_CONTRA_FLUJO,
                {"pedido": ped, "patron": patron_producto(prod), "destino": destino},
            ),
            _sentencia_mover(registro, origen, destino),
            _sentencia_historial(
                fecha, registro, origen, destino, globales, on_time, "Si", "Parcial"
            ),
        ]
        trabajos.append(
            Trabajo(
                ped,
                prod,
                origen,
                destino,
                sentencias,
                {
                    "calificacion": "Parcial",
                    "on_time": on_time,
                    "buffer": int(registro.buffer),
                    "retroceso": "Si",
                },
            )
        )
    return trabajos, descartes


def construir_trabajos_solo_estado(registros, *, origen, destino):
    """Almacén MP: solo cambia Estado_SDBR, sin historial (como en escritorio)."""
    trabajos = [
        Trabajo(
            r.pedido,
            r.producto,
            origen,
            destino,
            [_sentencia_mover(r, origen, destino)],
        )
        for r in deduplicar(registros)
    ]
    return trabajos, []


def construir_trabajos_entrega_pi(registros, *, destino, ahora):
    """Almacén PI: marca la entrega en Entrega_PI_Ensamble (clave pedido + código + OP)."""
    fecha = ahora.strftime(FORMATO_FECHA)
    trabajos = []
    for r in deduplicar(registros, claves=("pedido", "producto", "op")):
        sentencia = Sentencia(
            SQL_ENTREGA_PI,
            {
                "destino": destino,
                "fecha": fecha,
                "pedido": r.pedido,
                "patron": patron_producto(r.producto),
                "op": r.op,
            },
            exige_filas=True,
        )
        trabajos.append(
            Trabajo(r.pedido, r.producto, "Almacen", destino, [sentencia], {"op": r.op})
        )
    return trabajos, []
