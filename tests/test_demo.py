"""Piezas del modo demo que no necesitan base: reintento de arranque en frío y login sin bloqueo."""

from contextlib import contextmanager
from datetime import datetime

import pyodbc
import pytest
from sdbr_web.datos import usuarios
from sdbr_web.datos.conexion import (
    conectar_con_reintentos,
    es_error_de_arranque,
    motivo_breve,
)
from sdbr_web.datos.demo import CUENTAS_DEMO, PASSWORD_DEMO
from sdbr_web.dominio.permisos import AREAS_ASIGNABLES, ROLES
from werkzeug.security import generate_password_hash

PAUSADA = pyodbc.Error(
    "42000", "[42000] Database 'demo' on server 'x' is not currently available. (40613)"
)


class Reloj:
    """Reloj falso: dormir() lo adelanta en vez de esperar."""

    def __init__(self):
        self.ahora = 0.0
        self.esperas = []

    def __call__(self):
        return self.ahora

    def dormir(self, segundos):
        self.esperas.append(segundos)
        self.ahora += segundos


def _conectar_que_falla(veces, error=PAUSADA):
    estado = {"intentos": 0}

    def conectar():
        estado["intentos"] += 1
        if estado["intentos"] <= veces:
            raise error
        return "conexión"

    return conectar, estado


def test_reintenta_mientras_la_base_despierta():
    reloj = Reloj()
    conectar, estado = _conectar_que_falla(3)
    resultado = conectar_con_reintentos(
        conectar, plazo_seg=60, espera_seg=5, dormir=reloj.dormir, reloj=reloj
    )
    assert resultado == "conexión"
    assert estado["intentos"] == 4 and reloj.esperas == [5, 5, 5]


def test_se_rinde_al_agotar_el_plazo():
    reloj = Reloj()
    conectar, estado = _conectar_que_falla(100)
    with pytest.raises(pyodbc.Error):
        conectar_con_reintentos(
            conectar, plazo_seg=20, espera_seg=5, dormir=reloj.dormir, reloj=reloj
        )
    assert estado["intentos"] == 5  # en 0, 5, 10, 15 y 20 s


def test_no_reintenta_otros_errores():
    # Un "Login failed" no es una base en pausa: reintentar podría bloquear la cuenta.
    reloj = Reloj()
    login_fallido = pyodbc.Error("28000", "[28000] Login failed for user 'x'. (18456)")
    conectar, estado = _conectar_que_falla(1, login_fallido)
    with pytest.raises(pyodbc.Error):
        conectar_con_reintentos(
            conectar, plazo_seg=60, espera_seg=5, dormir=reloj.dormir, reloj=reloj
        )
    assert estado["intentos"] == 1 and reloj.esperas == []


def test_mensaje_de_base_en_pausa():
    assert es_error_de_arranque(PAUSADA)
    assert "activando" in motivo_breve(PAUSADA)


def test_cuentas_demo_validas():
    assert usuarios.validar_password_nueva("demo.operador", PASSWORD_DEMO) is None
    for usuario, _nombre, rol, areas, _texto in CUENTAS_DEMO:
        assert usuario.startswith("demo.") and rol in ROLES
        assert set(areas) <= set(AREAS_ASIGNABLES)
        assert usuarios.validar_password_nueva(usuario, PASSWORD_DEMO) is None


# ______________________________________LOGIN CON Y SIN BLOQUEO______________________________________


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def mappings(self):
        return self

    def first(self):
        return self._filas[0] if self._filas else None

    def scalars(self):
        return iter(self._filas)


class _ConexionFalsa:
    """Responde a las consultas de autenticar() y apunta las sentencias que escriben."""

    def __init__(self, fila):
        self.fila = fila
        self.escrituras = []

    def execute(self, sentencia, parametros=None):
        sql = str(sentencia)
        if sql.startswith("SELECT Id, Usuario"):
            return _Resultado([self.fila])
        if sql.startswith("SELECT Area"):
            return _Resultado([])
        self.escrituras.append(sql)
        return _Resultado([])


@pytest.fixture
def conexion_falsa(monkeypatch):
    fila = {
        "Id": 7,
        "Usuario": "demo.operador",
        "Nombre": "Operador",
        "Hash_Password": generate_password_hash(PASSWORD_DEMO),
        "Rol": "operador",
        "Activo": True,
        "Debe_Cambiar_Password": False,
        "Intentos_Fallidos": usuarios.MAX_INTENTOS - 1,
        "Bloqueado_Hasta": None,
    }
    conexion = _ConexionFalsa(fila)

    @contextmanager
    def transaccion():
        yield conexion

    monkeypatch.setattr(usuarios, "transaccion", transaccion)
    return conexion


def test_con_bloqueo_el_ultimo_fallo_bloquea(conexion_falsa):
    usuario, error = usuarios.autenticar("demo.operador", "mala")
    assert usuario is None and "bloqueada" in error
    assert any("Bloqueado_Hasta" in sql for sql in conexion_falsa.escrituras)


def test_sin_bloqueo_no_cuenta_fallos(conexion_falsa):
    usuario, error = usuarios.autenticar("demo.operador", "mala", bloquear=False)
    assert usuario is None and error == usuarios.MENSAJE_CREDENCIALES
    assert conexion_falsa.escrituras == []


def test_sin_bloqueo_entra_aunque_la_cuenta_estuviera_bloqueada(conexion_falsa):
    conexion_falsa.fila["Bloqueado_Hasta"] = datetime(2999, 1, 1)
    usuario, _ = usuarios.autenticar("demo.operador", PASSWORD_DEMO, bloquear=False)
    assert usuario is not None and usuario.usuario == "demo.operador"
    usuario, error = usuarios.autenticar("demo.operador", PASSWORD_DEMO)
    assert usuario is None and "bloqueada" in error
