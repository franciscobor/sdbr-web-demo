###############################################################################################
####################################### BARRA DE NAVEGACIÓN ###################################
###############################################################################################
# Los cinco menús de la versión de escritorio (interfaz/menu.py) más Administración. Cada opción
# lleva su ruta (None mientras no esté migrada: se muestra deshabilitada como "pendiente") y,
# si hace falta, el permiso que la muestra. El permiso del menú es solo comodidad: cada callback
# que escribe vuelve a comprobarlo en el servidor.

import dash_bootstrap_components as dbc
from dash import html

from sdbr_web import __version__, marca
from sdbr_web.dominio import permisos as p

# (etiqueta, ruta o None si está pendiente de migrar, permiso o None si basta con haber entrado)
MENUS = (
    (
        "Parametrización",
        (
            ("Obstrucciones de flujo", None, p.puede_parametrizar),
            ("Familias", None, p.puede_parametrizar),
        ),
    ),
    (
        "Planeación",
        (
            ("Modificación Planeación", None, p.puede_modificar_planeacion),
            ("Contra Flujo Pedido", None, p.puede_contra_flujo),
            ("Tambor Planta", None, None),
            ("Seguimiento a pedidos", None, None),
            ("Frente de carga", None, None),
            ("Vigilancia a ingreso de pedidos", None, None),
        ),
    ),
    (
        "S-DBR",
        (
            ("Modelo Global", None, None),
            ("Ingeniería", "/ingenieria", None),
            ("Ops", None, None),
            ("Almacén", None, None),
            ("Almacén · Entrega Fabricación MP, PI", None, None),
            ("Almacén · Entrega Ensamble PI", None, None),
            ("Producción", None, None),
        ),
    ),
    (
        "Poogi",
        (
            ("Ingeniería", None, None),
            ("Ops", None, None),
            ("Almacén", None, None),
            ("Producción", None, None),
        ),
    ),
    (
        "Clientes",
        (
            ("Despachos", None, None),
            ("Derogaciones", None, p.puede_contra_flujo),
            ("Indicadores", None, None),
            ("OTIF", None, None),
            ("Indicadores de tiempo", None, None),
        ),
    ),
    (
        "Administración",
        (
            ("Usuarios", None, p.puede_administrar),
            ("Auditoría", None, p.puede_administrar),
        ),
    ),
)


def _opcion(etiqueta, ruta):
    if ruta is None:
        return dbc.DropdownMenuItem(f"{etiqueta} (pendiente)", disabled=True)
    return dbc.DropdownMenuItem(etiqueta, href=ruta)


def barra_navegacion(usuario):
    insignia = dbc.NavbarBrand(
        [
            html.Img(
                src=marca.url_logo(),
                height="28px",
                className="me-2 bg-white rounded p-1",
            ),
            f"SDBR {__version__}",
        ],
        href="/",
        className="d-flex align-items-center",
    )

    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return dbc.Navbar(
            dbc.Container([insignia], fluid=True), color="primary", dark=True
        )

    menus = []
    for titulo, opciones in MENUS:
        visibles = [
            _opcion(etiqueta, ruta)
            for etiqueta, ruta, permiso in opciones
            if permiso is None or permiso(usuario)
        ]
        if visibles:
            menus.append(
                dbc.DropdownMenu(visibles, label=titulo, nav=True, in_navbar=True)
            )

    opciones_cuenta = [dbc.DropdownMenuItem(f"Rol: {usuario.rol}", header=True)]
    if not marca.modo_demo():  # en la demo las cuentas son compartidas
        opciones_cuenta.append(
            dbc.DropdownMenuItem(
                "Cambiar contraseña", href="/cambiar-password", external_link=True
            )
        )
    opciones_cuenta += [
        dbc.DropdownMenuItem(divider=True),
        dbc.DropdownMenuItem("Salir", href="/logout", external_link=True),
    ]
    cuenta = dbc.DropdownMenu(
        opciones_cuenta,
        label=usuario.nombre,
        nav=True,
        in_navbar=True,
        align_end=True,
    )

    return dbc.Navbar(
        dbc.Container(
            [
                insignia,
                dbc.NavbarToggler(id="navegacion-desplegar"),
                dbc.Collapse(
                    [
                        dbc.Nav(menus, navbar=True, className="me-auto"),
                        dbc.Nav([cuenta], navbar=True),
                    ],
                    id="navegacion-menus",
                    navbar=True,
                    is_open=False,
                ),
            ],
            fluid=True,
        ),
        color="primary",
        dark=True,
        className="mb-3",
    )
