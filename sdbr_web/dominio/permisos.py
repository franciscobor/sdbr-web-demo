###############################################################################################
###################################### USUARIOS Y PERMISOS ####################################
###############################################################################################
# Sustituyen a la contraseña compartida de SDBR_Passwords. Roles, de menos a más:
#
#   consulta    ve pantallas y dashboards y exporta a Excel.
#   operador    además mueve pedidos que salen de sus áreas asignadas y registra Poogi de ellas.
#   supervisor  además mueve desde o hacia Derogación, usa Derogaciones, Contra Flujo y la
#               Modificación Planeación. Es lo que hoy exige la contraseña.
#   admin       todo, más Parametrización, usuarios y auditoría.
#
# Las áreas se escriben como en la base ('Planeacion', no 'Ops').
#
# Estas funciones son la ÚNICA fuente de los permisos: los callbacks que escriben las consultan
# siempre en el servidor, aunque la interfaz ya haya ocultado el botón.

from dataclasses import dataclass, field

CONSULTA, OPERADOR, SUPERVISOR, ADMIN = "consulta", "operador", "supervisor", "admin"
ROLES = (CONSULTA, OPERADOR, SUPERVISOR, ADMIN)
_NIVEL = {rol: nivel for nivel, rol in enumerate(ROLES)}

# Áreas que un operador puede tener asignadas.
AREAS_ASIGNABLES = ("Ingenieria", "Planeacion", "Almacen", "Produccion", "Despachos")

# Un movimiento que sale de una de estas áreas o entra en ella exige supervisor.
AREAS_DE_SUPERVISOR = frozenset({"Derogacion"})


@dataclass(frozen=True)
class Usuario:
    id: int
    usuario: str
    nombre: str
    rol: str
    areas: frozenset = field(default_factory=frozenset)
    activo: bool = True
    debe_cambiar_password: bool = False

    # Interfaz que espera Flask-Login.
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.activo

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


def tiene_rol(usuario, rol_minimo):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False
    return _NIVEL.get(usuario.rol, -1) >= _NIVEL[rol_minimo]


def puede_mover(usuario, origen, destino):
    """¿Puede el usuario mover una línea de `origen` a `destino`? (nombres de la base)"""
    if not tiene_rol(usuario, OPERADOR):
        return False
    if origen in AREAS_DE_SUPERVISOR or destino in AREAS_DE_SUPERVISOR:
        return tiene_rol(usuario, SUPERVISOR)
    if tiene_rol(usuario, SUPERVISOR):
        return True
    return origen in usuario.areas


def puede_contra_flujo(usuario):
    return tiene_rol(usuario, SUPERVISOR)


def puede_registrar_poogi(usuario, area):
    if tiene_rol(usuario, SUPERVISOR):
        return True
    return tiene_rol(usuario, OPERADOR) and area in usuario.areas


def puede_modificar_planeacion(usuario):
    return tiene_rol(usuario, SUPERVISOR)


def puede_parametrizar(usuario):
    return tiene_rol(usuario, ADMIN)


def puede_administrar(usuario):
    return tiene_rol(usuario, ADMIN)
