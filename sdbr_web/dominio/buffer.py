###############################################################################################
################################### BUFFER Y ZONAS DE COLOR ###################################
###############################################################################################
# Mismo cálculo que el _datos_listos de cada pantalla de escritorio, vectorizado:
#
#     dias   = (fecha_fin_del_area - hoy) en días
#     Buffer = round((1 - dias / |lead_time_del_area|) * 100)
#
# Zonas (tags del treeview de escritorio):
#     0 blanco  Buffer < 0         sin liberar          "Por liberar"
#     1 verde   0 <= Buffer <= 33                       "Tempranos"
#     2 amarillo 33 < Buffer <= 66                      "Estables"
#     3 rojo    66 < Buffer <= 100                      "Por vencer"
#     4 negro   Buffer > 100       atrasado             "Atrasados"
#
# Diferencia con escritorio: allí un Buffer no calculable (fecha vacía o lead time 0) rompía la
# pantalla entera en .astype(int). Aquí la fila queda con Buffer vacío y zona SIN_DATO, no se
# colorea y no cuenta en las gráficas.

from datetime import date, datetime

import numpy as np
import pandas as pd

SIN_DATO = -1
BLANCO, VERDE, AMARILLO, ROJO, NEGRO = 0, 1, 2, 3, 4

# Orden de las gráficas, el mismo que en escritorio: de lo más urgente a lo menos.
ORDEN_GRAFICAS = (NEGRO, ROJO, AMARILLO, VERDE, BLANCO)
ETIQUETAS_ZONA = {
    NEGRO: "Atrasados",
    ROJO: "Por vencer",
    AMARILLO: "Estables",
    VERDE: "Tempranos",
    BLANCO: "Por liberar",
}


def hoy_a_medianoche():
    """Escritorio compara contra la fecha de hoy a las 00:00, no contra la hora actual."""
    return datetime.combine(date.today(), datetime.min.time())


def calcular_buffer(df, columna_fecha, columna_lead_time, hoy=None):
    """Serie Int64 (admite vacíos) con el % de buffer consumido de cada fila."""
    hoy = hoy or hoy_a_medianoche()
    dias = (pd.to_datetime(df[columna_fecha]) - hoy).dt.total_seconds() / 86400.0
    lead_time = pd.to_numeric(df[columna_lead_time], errors="coerce").abs()
    buffer = (1 - (dias / lead_time)) * 100
    buffer = buffer.replace([np.inf, -np.inf], np.nan).round()
    return buffer.astype("Int64")


def zona_de_buffer(buffer):
    """Serie de enteros con la zona de cada Buffer (SIN_DATO si está vacío)."""
    valores = pd.to_numeric(buffer, errors="coerce").astype(float)
    condiciones = [
        valores.isna(),
        valores < 0,
        valores <= 33,
        valores <= 66,
        valores <= 100,
    ]
    elecciones = [SIN_DATO, BLANCO, VERDE, AMARILLO, ROJO]
    return pd.Series(
        np.select(condiciones, elecciones, default=NEGRO), index=buffer.index
    ).astype(int)


def conteo_zonas(zonas):
    """Cuántas filas hay en cada zona, en ORDEN_GRAFICAS. Las filas SIN_DATO no cuentan."""
    cuenta = pd.Series(zonas).value_counts()
    return [int(cuenta.get(zona, 0)) for zona in ORDEN_GRAFICAS]
