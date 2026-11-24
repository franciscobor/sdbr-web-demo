"""Página de inicio: el logotipo configurado y el acceso a las pantallas ya migradas."""

import dash
import dash_bootstrap_components as dbc
from dash import html
from flask_login import current_user

from sdbr_web import __version__, marca

AVISO_PILOTO = (
    "Por ahora solo está disponible la pantalla de Ingeniería (menú S-DBR). El resto de opciones "
    "aparecen como pendientes y siguen funcionando en la aplicación de escritorio."
)
AVISO_DEMO = (
    "Esta demo muestra la pantalla de Ingeniería del flujo S-DBR (menú S-DBR), con pedidos "
    "ficticios. Pruebe a filtrar, exportar a Excel y mover pedidos a Ops o a Derogación según la "
    "cuenta con la que entró. El resto de pantallas están en migración."
)


def layout(**_parametros):
    nombre = getattr(current_user, "nombre", "")
    demo = marca.modo_demo()
    return dbc.Container(
        [
            html.Div(
                html.Img(
                    src=marca.url_logo(),
                    style={"maxWidth": "45%", "maxHeight": "220px", "height": "auto"},
                ),
                className="text-center my-5",
            ),
            html.H3(f"Bienvenido, {nombre}", className="text-center"),
            html.P(
                f"{marca.nombre_sistema()} · versión web {__version__}",
                className="text-center text-muted",
            ),
            html.Div(
                dbc.Alert(
                    [
                        html.Strong("Demo. " if demo else "Versión piloto. "),
                        AVISO_DEMO if demo else AVISO_PILOTO,
                    ],
                    color="info",
                ),
                className="mx-auto",
                style={"maxWidth": "720px"},
            ),
        ],
        fluid=True,
    )


dash.register_page(__name__, path="/", name="Inicio", title="SDBR", layout=layout)
