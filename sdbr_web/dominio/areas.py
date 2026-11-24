###############################################################################################
############################## NOMBRE DEL AREA DE OPS EN PANTALLA #############################
###############################################################################################
# En la base el area de Ops se sigue llamando 'Planeacion': SDBR_MOV.Estado_SDBR,
# Mov_Tiempo_Real3 (Sale_De/Entra_A), Poogi, Obstruccion_flujo_v2, Procesos, Familias_V2... En la
# interfaz del SDBR (pantallas, mensajes, dashboards y Excel) siempre se lee 'Ops'.
#
# Se traduce al mostrar y se vuelve a traducir antes de escribir o de filtrar contra la base.
# La tabla Procesos tiene ademas un proceso 'Ops' aparte: en pantalla los dos son el mismo
# (nombres_a_pantalla los junta) y al grabar se usa siempre 'Planeacion'.

OPS_BASE = "Planeacion"
OPS_PANTALLA = "Ops"


# Algunas columnas son char(n) y llegan con relleno ('Planeacion     ' en Poogi_Observaciones_Vista):
# la comparacion ignora los espacios a los lados.


def a_pantalla(area):
    """Nombre de un area tal como se muestra en la interfaz."""
    return OPS_PANTALLA if isinstance(area, str) and area.strip() == OPS_BASE else area


def a_base(area):
    """Nombre de un area tal como se graba y se filtra en la base."""
    return OPS_BASE if area == OPS_PANTALLA else area


def serie_a_pantalla(serie):
    """Serie de pandas con 'Planeacion' traducido a 'Ops'.

    Solo cambia las celdas cuyo valor es el area (con o sin relleno de espacios), no el texto que
    la menciona, como el nombre de una causa de obstruccion.
    """
    return serie.mask(serie.astype(str).str.strip() == OPS_BASE, OPS_PANTALLA)


def nombres_a_pantalla(nombres):
    """Lista de nombres traducida, sin repetidos y en el mismo orden."""
    vistos = []
    for nombre in nombres:
        nombre = a_pantalla(nombre)
        if nombre not in vistos:
            vistos.append(nombre)
    return vistos
