"""Prueba de humo de la aplicación completa, sin base de datos.

Se sustituyen la autenticación, la carga de usuarios, la caché de pedidos y la ejecución de
movimientos; el resto (guardia de sesión, layout, callbacks de Dash) corre de verdad.
"""

import io
import json

import pandas as pd
import pytest
import sdbr_web.app as modulo_app
import sdbr_web.componentes.pantalla_sdbr as pantalla
from sdbr_web.dominio.movimientos import SQL_HISTORIAL
from sdbr_web.dominio.permisos import Usuario

USUARIOS = {
    "1": Usuario(1, "ana", "Ana Operadora", "operador", frozenset({"Ingenieria"})),
    "2": Usuario(2, "luis", "Luis Consulta", "consulta", frozenset()),
    "3": Usuario(
        3,
        "nuevo",
        "Usuario Nuevo",
        "operador",
        frozenset({"Ingenieria"}),
        debe_cambiar_password=True,
    ),
}


@pytest.fixture(scope="session")
def app():
    # La aplicación se crea una sola vez: Dash consume los callbacks globales al arrancar.
    return modulo_app.crear_app()


@pytest.fixture
def cliente(app, monkeypatch, crudo):
    monkeypatch.setattr(
        modulo_app, "cargar_usuario", lambda id_: USUARIOS.get(str(id_))
    )
    llamadas_login = []

    def autenticar(nombre, password, bloquear=True):
        llamadas_login.append((nombre, bloquear))
        if password != "correcta":
            return None, "Usuario o contraseña incorrectos."
        return next((u for u in USUARIOS.values() if u.usuario == nombre), None), "x"

    monkeypatch.setattr(modulo_app, "autenticar", autenticar)
    reinicios = []
    monkeypatch.setattr(
        modulo_app, "reiniciar_si_toca", lambda: reinicios.append(1) or True
    )
    monkeypatch.setattr(
        pantalla, "cargar_pedidos_en_planta", lambda forzar=False: crudo
    )
    monkeypatch.setattr(pantalla, "invalidar_cache_pedidos", lambda: None)
    ejecutados = []

    def ejecutar(trabajos, usuario, accion):
        ejecutados.append((trabajos, usuario, accion))
        return trabajos, []

    monkeypatch.setattr(pantalla, "ejecutar_trabajos", ejecutar)
    c = app.server.test_client()
    c.ejecutados = ejecutados
    c.llamadas_login = llamadas_login
    c.reinicios = reinicios
    return c


@pytest.fixture
def demo(app, monkeypatch):
    """La misma aplicación en modo demo: la marca y el modo se leen en cada petición."""
    monkeypatch.setitem(app.server.config, "SDBR_MODO_DEMO", True)


def _entrar(cliente, usuario):
    return cliente.post(
        "/login",
        data={"usuario": usuario, "password": "correcta", "next": "/ingenieria"},
    )


def _dependencia(cliente, salida):
    deps = cliente.get("/_dash-dependencies").get_json()
    return next(d for d in deps if salida in d["output"])


def _llamar(cliente, salida, valores_entrada, valores_estado=(), disparo=None):
    """Invoca un callback como lo haría el navegador."""
    dep = _dependencia(cliente, salida)
    entradas = [dict(e, value=v) for e, v in zip(dep["inputs"], valores_entrada)]
    estados = [dict(e, value=v) for e, v in zip(dep["state"], valores_estado)]
    salidas = [
        {"id": parte.split(".")[0], "property": parte.split(".")[1]}
        for parte in dep["output"].strip(".").split("...")
    ]
    cuerpo = {
        "output": dep["output"],
        "outputs": salidas if len(salidas) > 1 else salidas[0],
        "inputs": entradas,
        "state": estados,
        "changedPropIds": [disparo] if disparo else [],
    }
    return cliente.post("/_dash-update-component", json=cuerpo)


def test_login_y_guardia(cliente):
    assert cliente.get("/ingenieria").status_code == 302
    assert _entrar(cliente, "ana").headers["Location"] == "/ingenieria"
    assert cliente.get("/ingenieria").status_code == 200
    assert cliente.get("/_dash-layout").status_code == 200
    cliente.get("/logout")
    assert cliente.get("/_dash-layout").status_code == 401


def test_redireccion_externa_bloqueada(cliente):
    r = cliente.post(
        "/login",
        data={"usuario": "ana", "password": "correcta", "next": "//malicioso.com"},
    )
    assert r.headers["Location"] == "/"


def test_credenciales_incorrectas(cliente):
    r = cliente.post("/login", data={"usuario": "ana", "password": "mala"})
    assert r.status_code == 401 and "incorrectos" in r.get_data(as_text=True)


def test_obliga_a_cambiar_la_contraseña(cliente):
    assert _entrar(cliente, "nuevo").headers["Location"] == "/cambiar-password"
    assert cliente.get("/ingenieria").headers["Location"] == "/cambiar-password"
    assert cliente.get("/_dash-layout").status_code == 403


def test_carga_filtros_y_graficos(cliente):
    _entrar(cliente, "ana")
    r = _llamar(
        cliente, "ingenieria-rejilla.rowData", [None, 0, "", "", "", "", "", ""]
    )
    assert r.status_code == 200
    respuesta = r.get_json()["response"]
    filas = respuesta["ingenieria-rejilla"]["rowData"]
    assert [(f["Producto"], f["Buffer"], f["Zona"]) for f in filas] == [
        ("PROD-A", 50, 2),
        ("PROD-B", 125, 4),
        ("PROD-D", -50, 0),
        ("PROD-E", 10, 1),
    ]
    assert filas[2]["NombreFamilia"] == "SIN FAMILIA"
    assert respuesta["ingenieria-barras"]["figure"]["data"][0]["y"] == [1, 0, 1, 1, 1]
    assert respuesta["ingenieria-resumen"]["children"] == "4 líneas"

    r = _llamar(
        cliente, "ingenieria-rejilla.rowData", [None, 0, "1001", "", "", "", "", ""]
    )
    respuesta = r.get_json()["response"]
    assert len(respuesta["ingenieria-rejilla"]["rowData"]) == 2
    assert respuesta["ingenieria-resumen"]["children"] == "2 de 4 líneas"


def test_exportar_excel(cliente):
    _entrar(cliente, "ana")
    r = _llamar(cliente, "ingenieria-descarga.data", [1], ["", "otro", "", "", "", ""])
    datos = r.get_json()["response"]["ingenieria-descarga"]["data"]
    assert datos["filename"].startswith("Ingenieria_") and datos["filename"].endswith(
        ".xlsx"
    )
    import base64

    excel = pd.read_excel(io.BytesIO(base64.b64decode(datos["content"])))
    assert excel["Producto"].tolist() == ["PROD-E"]
    assert "Final_Inge" in excel.columns and "Zona" not in excel.columns


def test_mover_con_permiso(cliente):
    _entrar(cliente, "ana")
    # El navegador manda un buffer falso (0): el servidor lo recalcula (125 → no a tiempo).
    lote = [{"pedido": "1001", "producto": "PROD-B", "buffer": 0}]
    r = _llamar(cliente, "ingenieria-version.data", [1], [lote, "Planeacion", False, 0])
    respuesta = r.get_json()["response"]
    assert respuesta["ingenieria-version"]["data"] == 1
    ((trabajos, usuario, accion),) = cliente.ejecutados
    assert (usuario, accion) == ("ana", "mover")
    historial = next(
        s for s in trabajos[0].sentencias if s.sql == SQL_HISTORIAL
    ).parametros
    assert (historial["buffer_zona"], historial["on_time"]) == ("125", "0")


def test_mover_sin_permiso(cliente):
    _entrar(cliente, "ana")  # operador: no puede ir a Derogación
    lote = [{"pedido": "1001", "producto": "PROD-B", "buffer": 125}]
    r = _llamar(cliente, "ingenieria-version.data", [1], [lote, "Derogacion", False, 0])
    assert "no puede mover" in json.dumps(r.get_json(), ensure_ascii=False)
    assert cliente.ejecutados == []

    cliente.get("/logout")
    _entrar(cliente, "luis")  # consulta: no puede mover nada, aunque fuerce la petición
    r = _llamar(cliente, "ingenieria-version.data", [1], [lote, "Planeacion", False, 0])
    assert "no puede mover" in json.dumps(r.get_json(), ensure_ascii=False)
    assert cliente.ejecutados == []


def test_lote_grande_exige_confirmacion(cliente):
    _entrar(cliente, "ana")
    lote = [
        {"pedido": "1001", "producto": f"P{i}", "buffer": 1}
        for i in range(pantalla.LOTE_CONFIRMAR_DESDE)
    ]
    r = _llamar(cliente, "ingenieria-version.data", [1], [lote, "Planeacion", False, 0])
    assert "marque la confirmación" in json.dumps(r.get_json(), ensure_ascii=False)
    assert cliente.ejecutados == []


def test_linea_que_ya_no_esta_en_el_area(cliente):
    _entrar(cliente, "ana")
    lote = [{"pedido": "1001", "producto": "PROD-C", "buffer": 1}]  # PROD-C está en Ops
    r = _llamar(cliente, "ingenieria-version.data", [1], [lote, "Planeacion", False, 0])
    texto = json.dumps(r.get_json(), ensure_ascii=False)
    assert "ya no está en Ingenieria" in texto and "Se movieron 0 de 1" in texto


# _____________________________________________MARCA_____________________________________________


def test_sin_empresa_no_hay_marca_de_nadie(cliente):
    pagina = cliente.get("/login").get_data(as_text=True)
    assert "/assets/logo_sdbr.svg" in pagina
    assert "Cuentas de la demo" not in pagina


def test_marca_configurada(app, cliente, monkeypatch):
    monkeypatch.setitem(app.server.config, "SDBR_EMPRESA", "Empresa Ejemplo")
    monkeypatch.setitem(app.server.config, "SDBR_LOGO", "otro.png")
    pagina = cliente.get("/login").get_data(as_text=True)
    assert "Empresa Ejemplo" in pagina and "/assets/otro.png" in pagina
    _entrar(cliente, "ana")
    layout = json.dumps(cliente.get("/_dash-layout").get_json())
    assert "/assets/otro.png" in layout


def test_produccion_bloquea_y_no_restablece(cliente):
    _entrar(cliente, "ana")
    assert cliente.llamadas_login == [("ana", True)]
    assert cliente.reinicios == []


# ___________________________________________MODO DEMO___________________________________________


def test_demo_muestra_las_cuentas_y_el_aviso(cliente, demo):
    pagina = cliente.get("/login").get_data(as_text=True)
    assert "Cuentas de la demo" in pagina and "demo.operador" in pagina
    assert "datos ficticios" in pagina
    _entrar(cliente, "ana")
    layout = json.dumps(cliente.get("/_dash-layout").get_json(), ensure_ascii=False)
    assert "datos ficticios" in layout
    assert "/cambiar-password" not in layout  # el menú no ofrece cambiar la contraseña


def test_demo_login_sin_bloqueo_y_con_restablecimiento(cliente, demo):
    cliente.post("/login", data={"usuario": "ana", "password": "mala"})
    _entrar(cliente, "ana")
    assert cliente.llamadas_login == [("ana", False), ("ana", False)]
    assert cliente.reinicios == [1, 1]


def test_demo_entra_aunque_falle_el_restablecimiento(cliente, demo, monkeypatch):
    def falla():
        raise RuntimeError("base caída")

    monkeypatch.setattr(modulo_app, "reiniciar_si_toca", falla)
    assert _entrar(cliente, "ana").headers["Location"] == "/ingenieria"


def test_demo_no_deja_cambiar_la_contraseña(cliente, demo):
    _entrar(cliente, "ana")
    pagina = cliente.get("/cambiar-password")
    assert pagina.status_code == 200
    texto = pagina.get_data(as_text=True)
    assert "no se puede cambiar" in texto and 'name="nueva"' not in texto
    r = cliente.post(
        "/cambiar-password",
        data={"actual": "correcta", "nueva": "otra-clave-1", "repetida": "otra-clave-1"},
    )
    assert r.status_code == 403
