"""Modelo Ingeniería: abre el flujo S-DBR (portada de sdbr/modelos/modelo_ingenieria.py).

Ingeniería no tiene retrocesos y no reclasifica calificaciones previas. Sus destinos son Ops y
Derogación; Derogación solo la pueden usar los supervisores (antes pedía la contraseña).
"""

import dash

from sdbr_web.componentes.pantalla_sdbr import ConfigPantalla, crear_pantalla
from sdbr_web.dominio.movimientos import NUNCA

CONFIG = ConfigPantalla(
    clave="ingenieria",
    titulo="Modelo Ingeniería",
    area="Ingenieria",
    columna_fecha="Final_Inge",
    columna_lead_time="Buffer_Ing",
    destinos=("Planeacion", "Derogacion"),
    retroceso="No",
    reclasifica=NUNCA,
    nombre_excel="Ingenieria",
)

dash.register_page(
    __name__,
    path="/ingenieria",
    name="Ingeniería",
    title="SDBR · Ingeniería",
    layout=crear_pantalla(CONFIG),
)
