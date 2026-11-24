from datetime import datetime, timedelta

from sdbr_web.datos.usuarios import (
    LONGITUD_MINIMA,
    MAX_INTENTOS,
    MINUTOS_BLOQUEO,
    estado_tras_fallo,
    validar_password_nueva,
)
from sdbr_web.dominio.permisos import (
    Usuario,
    puede_administrar,
    puede_contra_flujo,
    puede_mover,
    puede_parametrizar,
    puede_registrar_poogi,
)


def _u(rol, *areas):
    return Usuario(1, "u", "U", rol, frozenset(areas))


def test_matriz_de_movimientos():
    consulta, operador = _u("consulta", "Ingenieria"), _u("operador", "Ingenieria")
    supervisor, admin = _u("supervisor"), _u("admin")
    assert not puede_mover(consulta, "Ingenieria", "Planeacion")
    assert puede_mover(operador, "Ingenieria", "Planeacion")
    assert not puede_mover(operador, "Planeacion", "Almacen")  # no es su área
    assert not puede_mover(
        operador, "Ingenieria", "Derogacion"
    )  # Derogación: supervisor
    assert not puede_mover(operador, "Derogacion", "Ingenieria")
    assert puede_mover(supervisor, "Ingenieria", "Derogacion")
    assert puede_mover(supervisor, "Almacen", "Produccion")  # cualquier área
    assert puede_mover(admin, "Derogacion", "Ingenieria")
    assert not puede_mover(None, "Ingenieria", "Planeacion")


def test_permisos_por_rol():
    assert not puede_contra_flujo(_u("operador")) and puede_contra_flujo(
        _u("supervisor")
    )
    assert not puede_parametrizar(_u("supervisor")) and puede_parametrizar(_u("admin"))
    assert puede_administrar(_u("admin")) and not puede_administrar(_u("supervisor"))
    assert puede_registrar_poogi(_u("operador", "Almacen"), "Almacen")
    assert not puede_registrar_poogi(_u("operador", "Almacen"), "Produccion")
    assert not puede_registrar_poogi(_u("consulta", "Almacen"), "Almacen")


def test_reglas_de_contraseña():
    assert validar_password_nueva("jperez", "a" * (LONGITUD_MINIMA - 1))
    assert validar_password_nueva("jperez12", "JPEREZ12")
    assert validar_password_nueva("jperez", "segura-123", "otra-cosa")
    assert validar_password_nueva("jperez", "segura-123", "segura-123") is None


def test_bloqueo_tras_intentos_fallidos():
    ahora = datetime(2026, 11, 23, 8, 0)
    assert estado_tras_fallo(0, ahora) == (1, None)
    assert estado_tras_fallo(None, ahora) == (1, None)
    assert estado_tras_fallo(MAX_INTENTOS - 1, ahora) == (
        0,
        ahora + timedelta(minutes=MINUTOS_BLOQUEO),
    )
