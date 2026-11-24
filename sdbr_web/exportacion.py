###############################################################################################
####################################### EXPORTACIÓN A EXCEL ###################################
###############################################################################################
# En escritorio el Excel se guardaba en la carpeta Descargas del puesto (nucleo/exportacion.py).
# En la web eso sería la carpeta del SERVIDOR: aquí el archivo se genera en memoria y se le
# entrega al navegador del usuario con dcc.send_bytes.
#
# Se conservan las reglas de escritorio: nombre con la fecha del día, hoja con el nombre base
# recortado a los 31 caracteres que admite Excel y sheet_name por palabra clave (pandas 3).

import io
from datetime import date

from dash import dcc

LARGO_MAXIMO_HOJA = 31


def excel_en_memoria(df, hoja):
    buffer = io.BytesIO()
    df.to_excel(
        buffer, sheet_name=hoja[:LARGO_MAXIMO_HOJA], index=False, engine="openpyxl"
    )
    return buffer.getvalue()


def nombre_archivo(nombre_base, hoy=None):
    return f"{nombre_base}_{(hoy or date.today()).strftime('%Y-%m-%d')}.xlsx"


def descarga_excel(df, nombre_base, hoja=None):
    """Lo que devuelve un callback a la propiedad `data` de un dcc.Download."""
    contenido = excel_en_memoria(df, hoja or nombre_base)
    return dcc.send_bytes(contenido, nombre_archivo(nombre_base))
