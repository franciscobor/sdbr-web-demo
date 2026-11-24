###############################################################################################
###################################### MARCA Y MODO DEMO ######################################
###############################################################################################
# El código no lleva el nombre ni el logotipo de ninguna empresa: salen de la configuración
# (SDBR_EMPRESA, SDBR_LOGO) y crear_app() los guarda en la configuración de Flask. Así el mismo
# código sirve a producción y a la demo pública con datos ficticios (SDBR_MODO_DEMO).
#
# Se leen en cada petición, no al importar: las páginas de Dash y las plantillas se pintan dentro
# de una petición, y las pruebas pueden cambiar estos valores sin crear otra aplicación.

from flask import current_app, has_app_context

_POR_DEFECTO = {
    "SDBR_EMPRESA": "",
    "SDBR_LOGO": "logo_sdbr.svg",
    "SDBR_MODO_DEMO": False,
}


def _valor(clave):
    if has_app_context():
        return current_app.config.get(clave, _POR_DEFECTO[clave])
    return _POR_DEFECTO[clave]


def empresa():
    """Nombre de la empresa, o "" si no se configuró."""
    return _valor("SDBR_EMPRESA")


def url_logo():
    return "/assets/" + _valor("SDBR_LOGO")


def modo_demo():
    return bool(_valor("SDBR_MODO_DEMO"))


def nombre_sistema():
    """'Sistema S-DBR de <empresa>' o 'Sistema S-DBR' si no hay empresa."""
    nombre = empresa()
    return f"Sistema S-DBR de {nombre}" if nombre else "Sistema S-DBR"


AVISO_DEMO = (
    "Demo con datos ficticios. Los cambios los ven todos los visitantes y la base se "
    "restablece cada día."
)
