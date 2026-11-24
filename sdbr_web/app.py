###############################################################################################
####################################### APLICACIÓN SDBR WEB ###################################
###############################################################################################
# Un servidor Flask con tres capas:
#   1. Acceso (Flask + Flask-Login): /login, /logout y /cambiar-password, con plantillas Jinja.
#   2. Guardia (before_request): sin sesión no se ve ninguna página ni responde ningún callback.
#   3. Dash multipágina: las pantallas del SDBR.
#
# crear_app() se llama UNA vez por proceso (servidor.py). Los callbacks de las páginas se
# registran al importar sus módulos y Dash los consume con la primera aplicación que arranca.

import logging
from datetime import timedelta
from urllib.parse import urlsplit

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, html
from flask import (
    Flask,
    has_request_context,
    redirect,
    render_template,
    request,
    session,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from sdbr_web import __version__, marca
from sdbr_web.componentes.navegacion import barra_navegacion
from sdbr_web.config import cargar_configuracion
from sdbr_web.datos import conexion
from sdbr_web.datos.conexion import motivo_breve
from sdbr_web.datos.demo import CUENTAS_DEMO, PASSWORD_DEMO, reiniciar_si_toca
from sdbr_web.datos.usuarios import (
    LONGITUD_MINIMA,
    autenticar,
    cambiar_password,
    cargar_usuario,
)
from sdbr_web.paginas import registrar_paginas

registro_log = logging.getLogger(__name__)

# Rutas que se sirven sin sesión: el login y los archivos estáticos que necesita para pintarse.
_RUTAS_LIBRES = ("/login", "/salud", "/favicon.ico")
_PREFIJOS_LIBRES = ("/assets/", "/_dash-component-suites/", "/_favicon.ico")
_RUTAS_CAMBIO_PASSWORD = ("/cambiar-password", "/logout")


def _destino_seguro(siguiente):
    """Solo redirige dentro de la propia aplicación (evita /login?next=https://otro-sitio)."""
    if not siguiente:
        return "/"
    partes = urlsplit(siguiente)
    if (
        partes.scheme
        or partes.netloc
        or not siguiente.startswith("/")
        or siguiente.startswith("//")
    ):
        return "/"
    return siguiente


def _registrar_acceso(server):
    login_manager = LoginManager(server)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def _cargar(id_usuario):
        try:
            return cargar_usuario(id_usuario)
        except Exception:
            # Sin base no se puede validar la sesión: se trata como anónima y el login mostrará
            # el error de conexión. La cookie sigue ahí y la sesión vuelve cuando la base vuelve.
            registro_log.exception("No se pudo cargar el usuario %s", id_usuario)
            return None

    @server.before_request
    def _exigir_sesion():
        ruta = request.path
        if ruta in _RUTAS_LIBRES or ruta.startswith(_PREFIJOS_LIBRES):
            return None
        es_dash = ruta.startswith("/_dash-") or ruta.startswith("/_reload-hash")
        if not current_user.is_authenticated:
            if es_dash:
                return (
                    "La sesión ha caducado. Recargue la página para volver a entrar.",
                    401,
                )
            return redirect("/login?next=" + request.full_path.rstrip("?"))
        if current_user.debe_cambiar_password and ruta not in _RUTAS_CAMBIO_PASSWORD:
            if es_dash:
                return "Debe cambiar la contraseña antes de continuar.", 403
            return redirect("/cambiar-password")
        return None

    @server.context_processor
    def _datos_de_marca():
        # Lo que necesitan base.html y login.html para pintar la marca y el aviso de la demo.
        return {
            "empresa": marca.empresa(),
            "url_logo": marca.url_logo(),
            "modo_demo": marca.modo_demo(),
            "aviso_demo": marca.AVISO_DEMO,
            "cuentas_demo": CUENTAS_DEMO,
            "password_demo": PASSWORD_DEMO,
        }

    @server.route("/salud")
    def salud():
        # No toca la base: una sonda de disponibilidad no debe despertar la base en pausa de la demo.
        return {"estado": "ok", "version": __version__}

    @server.route("/login", methods=["GET", "POST"])
    def login():
        siguiente = _destino_seguro(request.values.get("next"))
        if request.method == "GET":
            if current_user.is_authenticated:
                return redirect(siguiente)
            return render_template(
                "login.html",
                error=None,
                usuario="",
                siguiente=siguiente,
                version=__version__,
            )
        nombre = request.form.get("usuario", "").strip()
        demo = marca.modo_demo()
        if demo:
            # El primer acceso del día devuelve la demo a su estado inicial. Un fallo aquí no
            # impide entrar: la demo seguiría con los movimientos de ayer.
            try:
                reiniciar_si_toca()
            except Exception:
                registro_log.exception("No se pudo restablecer la base de la demo")
        try:
            usuario, error = autenticar(
                nombre, request.form.get("password", ""), bloquear=not demo
            )
        except Exception as exc:
            registro_log.exception("Fallo de la base al autenticar a %s", nombre)
            usuario, error = (
                None,
                f"No fue posible conectar con la base de datos: {motivo_breve(exc)}",
            )
        if usuario is None:
            registro_log.info(
                "Acceso rechazado para '%s' desde %s", nombre, request.remote_addr
            )
            return render_template(
                "login.html",
                error=error,
                usuario=nombre,
                siguiente=siguiente,
                version=__version__,
            ), 401
        session.clear()
        session.permanent = True
        login_user(usuario)
        registro_log.info("Acceso de %s desde %s", usuario.usuario, request.remote_addr)
        return redirect(
            "/cambiar-password" if usuario.debe_cambiar_password else siguiente
        )

    @server.route("/logout")
    def logout():
        logout_user()
        session.clear()
        return redirect("/login")

    @server.route("/cambiar-password", methods=["GET", "POST"])
    @login_required
    def cambiar_password_vista():
        datos = {
            "nombre": current_user.nombre,
            "obligatorio": current_user.debe_cambiar_password,
            "longitud_minima": LONGITUD_MINIMA,
            "version": __version__,
        }
        if marca.modo_demo():
            # Las cuentas de la demo son compartidas: si un visitante cambiara la contraseña,
            # los demás no podrían entrar.
            error = "En la demo las cuentas son compartidas y su contraseña no se puede cambiar."
            codigo = 200 if request.method == "GET" else 403
            return render_template(
                "cambiar_password.html", error=error, bloqueado=True, **datos
            ), codigo
        if request.method == "GET":
            return render_template("cambiar_password.html", error=None, **datos)
        try:
            error = cambiar_password(
                current_user,
                request.form.get("actual", ""),
                request.form.get("nueva", ""),
                request.form.get("repetida", ""),
            )
        except Exception as exc:
            registro_log.exception(
                "Fallo al cambiar la contraseña de %s", current_user.usuario
            )
            error = f"No fue posible guardar la contraseña: {motivo_breve(exc)}"
        if error:
            return render_template("cambiar_password.html", error=error, **datos), 400
        return redirect("/")


def _layout_principal():
    usuario = current_user if has_request_context() else None
    partes = [
        barra_navegacion(usuario),
        dbc.Container(dash.page_container, fluid=True, className="pb-4"),
    ]
    if marca.modo_demo():
        partes.insert(0, html.Div(marca.AVISO_DEMO, className="franja-demo"))
    return html.Div(partes)


def crear_app(config=None):
    config = config or cargar_configuracion()
    conexion.configurar(config)

    server = Flask(__name__, template_folder="plantillas")
    server.config.update(
        SECRET_KEY=config.secret_key,
        SESSION_COOKIE_NAME="sdbr_sesion",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.cookie_segura,
        PERMANENT_SESSION_LIFETIME=timedelta(
            hours=12
        ),  # un turno; después hay que volver a entrar
        # Marca y modo demo, leídos en cada petición por sdbr_web/marca.py
        SDBR_EMPRESA=config.empresa,
        SDBR_LOGO=config.logo,
        SDBR_MODO_DEMO=config.modo_demo,
    )
    _registrar_acceso(server)

    app = dash.Dash(
        __name__,
        server=server,
        use_pages=True,
        pages_folder="",
        title=f"SDBR {__version__}" + (" · demo" if config.modo_demo else ""),
        update_title=None,
        suppress_callback_exceptions=True,  # cada página trae sus propios componentes
        serve_locally=True,  # nada de CDN: la planta puede no tener Internet
    )
    registrar_paginas()
    app.layout = _layout_principal

    @app.callback(
        Output("navegacion-menus", "is_open"),
        Input("navegacion-desplegar", "n_clicks"),
        State("navegacion-menus", "is_open"),
        prevent_initial_call=True,
    )
    def _desplegar_menu(_n, abierto):
        return not abierto

    return app
