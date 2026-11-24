###############################################################################################
############################ COLORES DE LAS ZONAS Y GRÁFICOS DE PRIORIDAD #####################
###############################################################################################
# Los cinco colores son los de la metodología S-DBR y los que la planta ya conoce: no son una
# paleta decorativa y no se cambian. Siempre van acompañados de su nombre (leyenda, etiqueta de
# la barra, tooltip), nunca solo del color.
#
# Sustituyen a la torta y las barras de matplotlib de escritorio, con los mismos datos.

import plotly.graph_objects as go

from sdbr_web.dominio.buffer import (
    AMARILLO,
    BLANCO,
    ETIQUETAS_ZONA,
    NEGRO,
    ORDEN_GRAFICAS,
    ROJO,
    VERDE,
)

COLOR_FONDO = {
    NEGRO: "#000000",
    ROJO: "#e53935",
    AMARILLO: "#fdd835",
    VERDE: "#43a047",
    BLANCO: "#ffffff",
}
COLOR_TEXTO = {
    NEGRO: "#ffffff",
    ROJO: "#000000",
    AMARILLO: "#000000",
    VERDE: "#000000",
    BLANCO: "#000000",
}
BORDE = "#9e9e9e"  # el blanco necesita borde para verse sobre el fondo blanco
SIN_DATOS = "#e0e0e0"

_FUENTE = dict(
    family="system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    size=13,
    color="#212529",
)


def estilo_filas():
    """getRowStyle de AG Grid: fondo y texto de cada fila según su zona."""
    return {
        "styleConditions": [
            {
                "condition": f"params.data.Zona === {zona}",
                "style": {
                    "backgroundColor": COLOR_FONDO[zona],
                    "color": COLOR_TEXTO[zona],
                },
            }
            for zona in ORDEN_GRAFICAS
        ]
    }


def _base(figura, titulo):
    figura.update_layout(
        title=dict(text=titulo, x=0.5, font=dict(size=15)),
        font=_FUENTE,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="#ffffff", font=_FUENTE),
    )
    return figura


def figura_torta(conteos):
    """Participación de cada zona. Sin filas, una torta gris y sin porcentajes (como escritorio)."""
    total = sum(conteos)
    etiquetas = [ETIQUETAS_ZONA[z] for z in ORDEN_GRAFICAS]
    if total:
        traza = go.Pie(
            labels=etiquetas,
            values=conteos,
            sort=False,
            direction="clockwise",
            hole=0.45,
            marker=dict(
                colors=[COLOR_FONDO[z] for z in ORDEN_GRAFICAS],
                line=dict(color=BORDE, width=1),
            ),
            textinfo="percent",
            textfont=dict(color=[COLOR_TEXTO[z] for z in ORDEN_GRAFICAS]),
            hovertemplate="%{label}: %{value} líneas (%{percent})<extra></extra>",
        )
    else:
        traza = go.Pie(
            labels=["Sin pedidos"],
            values=[1],
            hole=0.45,
            textinfo="none",
            marker=dict(colors=[SIN_DATOS]),
            hoverinfo="skip",
        )
    figura = go.Figure(traza)
    figura.update_layout(
        legend=dict(orientation="h", y=-0.05, x=0.5, xanchor="center"),
        showlegend=bool(total),
    )
    return _base(figura, "Sistema Único de Prioridades")


def figura_barras(conteos):
    """Número de líneas por zona, con el valor escrito sobre cada barra."""
    etiquetas = [ETIQUETAS_ZONA[z] for z in ORDEN_GRAFICAS]
    figura = go.Figure(
        go.Bar(
            x=etiquetas,
            y=conteos,
            marker=dict(
                color=[COLOR_FONDO[z] for z in ORDEN_GRAFICAS],
                line=dict(color=BORDE, width=1),
            ),
            text=conteos,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}: %{y} líneas<extra></extra>",
        )
    )
    figura.update_layout(
        bargap=0.35,
        showlegend=False,
        yaxis=dict(
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=True,
            zerolinecolor="#bdbdbd",
            rangemode="tozero",
            title=None,
        ),
        xaxis=dict(title=None),
    )
    return _base(figura, "Líneas por zona de buffer")
