###############################################################################################
##################################### FILTROS DE LAS PANTALLAS ################################
###############################################################################################
# Las seis cajas de búsqueda de escritorio (Pedido, Cliente, Producto, Descripción, Fecha,
# Familia) con dos diferencias deliberadas:
#   - se combinan (Y lógico): en escritorio cada caja filtraba la consulta completa y olvidaba las
#     demás;
#   - el texto se busca literal, no como expresión regular: en escritorio escribir un paréntesis
#     o un asterisco hacía fallar el filtro.
# Igual que en escritorio, no distingue mayúsculas y busca el texto en cualquier parte del campo.

import pandas as pd


def aplicar_filtros(df, valores, columnas):
    """Filtra df con los textos de `valores` ({campo: texto}) sobre `columnas` ({campo: columna}).

    Los campos vacíos o que no tienen columna se ignoran.
    """
    mascara = pd.Series(True, index=df.index)
    for campo, texto in (valores or {}).items():
        texto = (texto or "").strip()
        columna = columnas.get(campo)
        if not texto or columna is None or columna not in df.columns:
            continue
        mascara &= (
            df[columna]
            .astype(str)
            .str.contains(texto, case=False, regex=False, na=False)
        )
    return df[mascara]
