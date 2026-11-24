###############################################################################################
####################################### BASE DE LA DEMO #######################################
###############################################################################################
# Solo se usa con SDBR_MODO_DEMO=si, contra la base de demostración que crea demo/instalar.py.
# En producción nada de este módulo se ejecuta.
#
# Las cuentas de la demo son compartidas y su contraseña es pública (sale en la página de login):
# por eso en modo demo no se bloquean por intentos fallidos ni se les puede cambiar la contraseña.
#
# La base se restablece una vez al día, de forma perezosa: el primer login del día ejecuta
# Demo_Reiniciar_Si_Toca. No hay una tarea programada a propósito: en Azure SQL con la oferta
# gratuita, despertar la base cada noche gastaría la cuota mensual aunque nadie visitara la demo.

from sqlalchemy import text

from sdbr_web.datos.conexion import transaccion
from sdbr_web.datos.pedidos import invalidar_cache_pedidos

PASSWORD_DEMO = "sdbr-demo"

# (usuario, nombre, rol, áreas con el nombre de la base, qué puede hacer)
CUENTAS_DEMO = (
    (
        "demo.consulta",
        "Visitante de consulta",
        "consulta",
        (),
        "Ve las pantallas y exporta a Excel.",
    ),
    (
        "demo.operador",
        "Operador de Ingeniería y Ops",
        "operador",
        ("Ingenieria", "Planeacion"),
        "Mueve pedidos que salen de Ingeniería y de Ops.",
    ),
    (
        "demo.supervisor",
        "Supervisor de planta",
        "supervisor",
        (),
        "Mueve desde cualquier área, también hacia Derogación.",
    ),
)


def reiniciar_si_toca():
    """Restablece la base de demo si hoy aún no se hizo. Devuelve True si la restableció."""
    with transaccion() as conexion:
        reiniciada = conexion.execute(text("EXEC dbo.Demo_Reiniciar_Si_Toca")).scalar()
    if reiniciada:
        invalidar_cache_pedidos()
    return bool(reiniciada)
