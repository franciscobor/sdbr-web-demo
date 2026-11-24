###############################################################################################
############################## FÁBRICA DE LAS PANTALLAS DEL FLUJO S-DBR #######################
###############################################################################################
# En escritorio había siete copias casi idénticas de la misma pantalla (modelo_ingenieria,
# modelo_plane, modelo_almacen...). Aquí hay UNA: cada pantalla es una ConfigPantalla y
# crear_pantalla() le da su layout y sus callbacks.
#
# Lo que hace cada pantalla, igual que en escritorio:
#   - lee la caché compartida de pedidos en planta y filtra en memoria las líneas de su área;
#   - calcula el % de buffer y la zona de color de cada línea;
#   - pinta la rejilla coloreada, la torta y las barras, y las seis cajas de búsqueda;
#   - mueve una línea (doble clic) o varias (casillas + "Mover seleccionados") a otra área;
#   - exporta a Excel lo que se ve tras filtrar.
#
# Reglas de seguridad de los callbacks que escriben:
#   - el permiso se comprueba SIEMPRE en el servidor (dominio/permisos.py);
#   - del navegador solo se aceptan claves (pedido, producto). El buffer, la calificación y el
#     estado se recalculan en el servidor con datos recién leídos.

import json
import logging
from dataclasses import dataclass
from datetime import datetime

import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, ctx, dcc, html, no_update
from flask_login import current_user

from sdbr_web.componentes.zonas import estilo_filas, figura_barras, figura_torta
from sdbr_web.datos.conexion import motivo_breve
from sdbr_web.datos.movimientos import ejecutar_trabajos
from sdbr_web.datos.pedidos import (
    cargar_pedidos_en_planta,
    filas_del_pedido,
    invalidar_cache_pedidos,
)
from sdbr_web.dominio.areas import a_pantalla, serie_a_pantalla
from sdbr_web.dominio.buffer import calcular_buffer, conteo_zonas, zona_de_buffer
from sdbr_web.dominio.filtros import aplicar_filtros
from sdbr_web.dominio.movimientos import NUNCA, Registro, construir_trabajos_flujo
from sdbr_web.dominio.permisos import puede_mover
from sdbr_web.exportacion import descarga_excel

registro_log = logging.getLogger(__name__)

LOTE_CONFIRMAR_DESDE = (
    20  # desde aquí se pide confirmación expresa antes de mover un lote
)
MAX_FALLOS_EN_RESUMEN = 10

FILTROS = (
    ("pedido", "Pedido", "pedconsecutivo"),
    ("cliente", "Cliente", "NombCliente"),
    ("producto", "Producto", "Producto"),
    ("descripcion", "Descripción", "Descripcion"),
    ("fecha", "Fecha (AAAA-MM-DD)", "fecha_Venci"),
    ("familia", "Familia", "NombreFamilia"),
)
COLUMNAS_FILTRO = {campo: columna for campo, _, columna in FILTROS}

COLUMNAS = [
    "pedconsecutivo",
    "NombCliente",
    "Producto",
    "Descripcion",
    "fecha_Venci",
    "Cantidad",
    "Estado_SDBR",
    "Buffer",
    "NombreFamilia",
]

DEFINICION_COLUMNAS = [
    {"field": "pedconsecutivo", "headerName": "Pedido", "minWidth": 95},
    {"field": "NombCliente", "headerName": "Cliente", "minWidth": 180},
    {"field": "Producto", "headerName": "Producto", "minWidth": 120},
    {"field": "Descripcion", "headerName": "Descripción", "minWidth": 220},
    {"field": "fecha_Venci", "headerName": "Fecha venc.", "minWidth": 110},
    {
        "field": "Cantidad",
        "headerName": "Cantidad",
        "type": "rightAligned",
        "minWidth": 95,
    },
    {"field": "Estado_SDBR", "headerName": "Estado", "minWidth": 100},
    {
        "field": "Buffer",
        "headerName": "% Buffer",
        "type": "rightAligned",
        "minWidth": 100,
    },
    {"field": "NombreFamilia", "headerName": "Familia", "minWidth": 140},
]

TEXTOS_REJILLA = {
    "noRowsToShow": "No hay líneas que mostrar",
    "loadingOoo": "Cargando...",
    "ariaChecked": "marcada",
    "ariaUnchecked": "sin marcar",
}


@dataclass(frozen=True)
class ConfigPantalla:
    clave: str  # prefijo de los ids y nombre interno ('ingenieria')
    titulo: str  # 'Modelo Ingeniería'
    area: str  # Estado_SDBR en la base ('Ingenieria', 'Planeacion'...)
    columna_fecha: str  # fecha fin del área ('Final_Inge')
    columna_lead_time: str  # lead time del área ('Buffer_Ing')
    destinos: tuple  # destinos del movimiento, con el nombre de la base
    retroceso: str = "No"
    reclasifica: str = NUNCA
    nombre_excel: str = ""


# ______________________________________DATOS (SIN INTERFAZ)______________________________________


def id_fila(indice, pedido, producto, buffer):
    """Id de la fila en la rejilla. Lleva la clave para que el doble clic no dependa de rowData."""
    return json.dumps(
        [int(indice), pedido, producto, None if pd.isna(buffer) else int(buffer)],
        ensure_ascii=False,
    )


def preparar(crudo, cfg, hoy=None):
    """Las líneas del área con Buffer, Zona e id. Mismo cálculo que _datos_listos de escritorio."""
    df = crudo[crudo["Estado_SDBR"] == cfg.area].copy().reset_index(drop=True)
    df["Buffer"] = calcular_buffer(df, cfg.columna_fecha, cfg.columna_lead_time, hoy)
    df["Zona"] = zona_de_buffer(df["Buffer"])
    df["fecha_Venci"] = pd.to_datetime(df[cfg.columna_fecha]).dt.strftime("%Y-%m-%d")
    df["pedconsecutivo"] = df["pedconsecutivo"].astype(str).str.strip()
    df["Producto"] = df["Producto"].astype(str).str.strip()
    familia = df["NombreFamilia"].astype("object")
    df["NombreFamilia"] = familia.where(
        familia.notna() & (familia.astype(str).str.strip() != ""), "SIN FAMILIA"
    )
    df["Estado_SDBR"] = serie_a_pantalla(df["Estado_SDBR"])
    df["id"] = [
        id_fila(i, p, pr, b)
        for i, p, pr, b in zip(
            df.index, df["pedconsecutivo"], df["Producto"], df["Buffer"]
        )
    ]
    return df[COLUMNAS + ["Zona", "id"]]


def filas_para_rejilla(df):
    """Registros JSON: los vacíos de pandas (NaN, NA, NaT) pasan a None."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def para_excel(df, cfg):
    """Lo que se exporta: las columnas de escritorio, con la fecha bajo su nombre original."""
    return df.drop(columns=["Zona", "id"]).rename(
        columns={"fecha_Venci": cfg.columna_fecha}
    )


def destinos_permitidos(usuario, cfg):
    return [d for d in cfg.destinos if puede_mover(usuario, cfg.area, d)]


def registros_del_lote(lote, df, cfg):
    """Traduce las claves que mandó el navegador a Registros con el buffer recalculado aquí."""
    registros, descartes = [], []
    for item in lote:
        pedido, producto = str(item["pedido"]).strip(), str(item["producto"]).strip()
        filas = df[(df["pedconsecutivo"] == pedido) & (df["Producto"] == producto)]
        if filas.empty:
            descartes.append(
                (pedido, producto, f"ya no está en {a_pantalla(cfg.area)}")
            )
            continue
        registros.append(Registro(pedido, producto, filas.iloc[0]["Buffer"]))
    return registros, descartes


def texto_resumen(total, movidos, fallos, destino):
    lineas = [f"Se movieron {movidos} de {total} registros a {a_pantalla(destino)}."]
    if fallos:
        lineas.append("No se pudieron mover:")
        lineas.extend(
            f"• {pedido} · {producto}: {motivo}"
            for pedido, producto, motivo in fallos[:MAX_FALLOS_EN_RESUMEN]
        )
        if len(fallos) > MAX_FALLOS_EN_RESUMEN:
            lineas.append(f"... y {len(fallos) - MAX_FALLOS_EN_RESUMEN} más.")
    return lineas


# ______________________________________________FÁBRICA___________________________________________


def crear_pantalla(cfg):
    """Registra los callbacks de la pantalla y devuelve su función de layout."""
    k = cfg.clave
    ids = {
        nombre: f"{k}-{nombre}"
        for nombre in (
            "rejilla",
            "torta",
            "barras",
            "resumen",
            "error",
            "recargar",
            "limpiar",
            "version",
            "btn-mover",
            "btn-excel",
            "descarga",
            "modal",
            "lote",
            "modal-lista",
            "modal-aviso",
            "destino",
            "confirmar",
            "confirmar-fila",
            "mover",
            "cerrar",
            "resultado",
        )
    }
    ids_filtro = [f"{k}-filtro-{campo}" for campo, _, _ in FILTROS]

    def leer_visibles(valores, forzar=False):
        crudo = cargar_pedidos_en_planta(forzar=forzar)
        df = preparar(crudo, cfg)
        visibles = aplicar_filtros(
            df, dict(zip(COLUMNAS_FILTRO, valores)), COLUMNAS_FILTRO
        )
        return df, visibles

    # _________________________________CARGA, FILTROS Y GRÁFICOS_________________________________
    @callback(
        Output(ids["rejilla"], "rowData"),
        Output(ids["torta"], "figure"),
        Output(ids["barras"], "figure"),
        Output(ids["resumen"], "children"),
        Output(ids["error"], "children"),
        Output(ids["error"], "is_open"),
        Input(ids["recargar"], "n_clicks"),
        Input(ids["version"], "data"),
        *[Input(i, "value") for i in ids_filtro],
    )
    def cargar(_n, _version, *valores):
        try:
            df, visibles = leer_visibles(
                valores, forzar=ctx.triggered_id == ids["recargar"]
            )
        except Exception as exc:
            registro_log.exception("No se pudieron cargar los pedidos de %s", cfg.area)
            vacio = [0] * 5
            return (
                [],
                figura_torta(vacio),
                figura_barras(vacio),
                "",
                f"No fue posible cargar los pedidos: {motivo_breve(exc)}",
                True,
            )
        conteos = conteo_zonas(visibles["Zona"])
        if len(visibles) == len(df):
            resumen = f"{len(df)} líneas"
        else:
            resumen = f"{len(visibles)} de {len(df)} líneas"
        return (
            filas_para_rejilla(visibles),
            figura_torta(conteos),
            figura_barras(conteos),
            resumen,
            None,
            False,
        )

    @callback(
        *[Output(i, "value") for i in ids_filtro],
        Input(ids["limpiar"], "n_clicks"),
        prevent_initial_call=True,
    )
    def limpiar_filtros(_n):
        return [""] * len(ids_filtro)

    @callback(
        Output(ids["btn-mover"], "children"),
        Output(ids["btn-mover"], "disabled"),
        Input(ids["rejilla"], "selectedRows"),
    )
    def contar_seleccion(seleccionadas):
        n = len(seleccionadas or [])
        return (
            "Mover seleccionados" if n == 0 else f"Mover seleccionados ({n})"
        ), n == 0

    # __________________________________________EXCEL____________________________________________
    @callback(
        Output(ids["descarga"], "data"),
        Input(ids["btn-excel"], "n_clicks"),
        *[State(i, "value") for i in ids_filtro],
        prevent_initial_call=True,
    )
    def exportar(_n, *valores):
        _, visibles = leer_visibles(valores)
        return descarga_excel(para_excel(visibles, cfg), cfg.nombre_excel or cfg.clave)

    # _____________________________VENTANA DE MOVIMIENTO (ABRIR/CERRAR)__________________________
    @callback(
        Output(ids["modal"], "is_open"),
        Output(ids["lote"], "data"),
        Output(ids["modal-lista"], "children"),
        Output(ids["modal-aviso"], "children"),
        Output(ids["destino"], "options"),
        Output(ids["destino"], "value"),
        Output(ids["confirmar-fila"], "style"),
        Output(ids["confirmar"], "value"),
        Output(ids["resultado"], "children"),
        Output(ids["mover"], "disabled"),
        Input(ids["btn-mover"], "n_clicks"),
        Input(ids["rejilla"], "cellDoubleClicked"),
        Input(ids["cerrar"], "n_clicks"),
        State(ids["rejilla"], "selectedRows"),
        prevent_initial_call=True,
    )
    def abrir_o_cerrar(_n_mover, doble_clic, _n_cerrar, seleccionadas):
        disparo = ctx.triggered_id
        if disparo == ids["cerrar"]:
            return (
                False,
                [],
                [],
                None,
                [],
                None,
                {"display": "none"},
                False,
                None,
                True,
            )

        if disparo == ids["rejilla"]:
            if not doble_clic or not doble_clic.get("rowId"):
                return (no_update,) * 10
            _, pedido, producto, buffer = json.loads(doble_clic["rowId"])
            lote = [{"pedido": pedido, "producto": producto, "buffer": buffer}]
        else:
            lote, vistos = [], set()
            for fila in seleccionadas or []:
                clave = (fila["pedconsecutivo"], fila["Producto"])
                if clave not in vistos:
                    vistos.add(clave)
                    lote.append(
                        {
                            "pedido": clave[0],
                            "producto": clave[1],
                            "buffer": fila.get("Buffer"),
                        }
                    )
        if not lote:
            return (no_update,) * 10

        destinos = destinos_permitidos(current_user, cfg)
        aviso = None
        if not destinos:
            aviso = dbc.Alert(
                f"Su usuario no tiene permiso para mover pedidos desde "
                f"{a_pantalla(cfg.area)}.",
                color="warning",
                className="mb-0",
            )
        lista = dbc.Table(
            [
                html.Thead(
                    html.Tr(
                        [html.Th("Pedido"), html.Th("Producto"), html.Th("% Buffer")]
                    )
                )
            ]
            + [
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(i["pedido"]),
                                html.Td(i["producto"]),
                                html.Td("" if i["buffer"] is None else i["buffer"]),
                            ]
                        )
                        for i in lote
                    ]
                )
            ],
            size="sm",
            striped=True,
            className="mb-0",
        )
        opciones = [{"label": a_pantalla(d), "value": d} for d in destinos]
        confirmar = (
            {"display": "block"}
            if len(lote) >= LOTE_CONFIRMAR_DESDE
            else {"display": "none"}
        )
        return (
            True,
            lote,
            lista,
            aviso,
            opciones,
            None,
            confirmar,
            False,
            None,
            not destinos,
        )

    # __________________________________________MOVER____________________________________________
    @callback(
        Output(ids["resultado"], "children", allow_duplicate=True),
        Output(ids["lote"], "data", allow_duplicate=True),
        Output(ids["version"], "data"),
        Input(ids["mover"], "n_clicks"),
        State(ids["lote"], "data"),
        State(ids["destino"], "value"),
        State(ids["confirmar"], "value"),
        State(ids["version"], "data"),
        prevent_initial_call=True,
        running=[(Output(ids["mover"], "disabled"), True, False)],
    )
    def mover(_n, lote, destino, confirmado, version):
        def alerta(lineas, color):
            lineas = [lineas] if isinstance(lineas, str) else lineas
            return dbc.Alert(
                [html.Div(linea) for linea in lineas], color=color, className="mb-0"
            )

        if not lote:
            return (
                alerta(
                    "No hay registros pendientes de mover. Cierre la ventana.",
                    "secondary",
                ),
                no_update,
                no_update,
            )
        if destino not in cfg.destinos:
            return (
                alerta("Seleccione el proceso siguiente antes de mover.", "warning"),
                no_update,
                no_update,
            )
        usuario = current_user
        if not puede_mover(usuario, cfg.area, destino):
            return (
                alerta(
                    f"Su usuario no puede mover pedidos de {a_pantalla(cfg.area)} a "
                    f"{a_pantalla(destino)}.",
                    "danger",
                ),
                no_update,
                no_update,
            )
        if len(lote) >= LOTE_CONFIRMAR_DESDE and not confirmado:
            return (
                alerta(
                    f"Va a mover {len(lote)} registros de una vez: marque la confirmación.",
                    "warning",
                ),
                no_update,
                no_update,
            )

        try:
            crudo = cargar_pedidos_en_planta(forzar=True)
            df = preparar(crudo, cfg)
        except Exception as exc:
            registro_log.exception("No se pudieron releer los pedidos antes de mover")
            return (
                alerta(
                    f"No fue posible leer los pedidos: {motivo_breve(exc)}", "danger"
                ),
                no_update,
                no_update,
            )

        registros, descartes = registros_del_lote(lote, df, cfg)
        trabajos, descartes_dominio = construir_trabajos_flujo(
            registros,
            origen=cfg.area,
            destino=destino,
            retroceso=cfg.retroceso,
            reclasifica=cfg.reclasifica,
            filas_de_pedido=lambda pedido: filas_del_pedido(crudo, pedido),
            ahora=datetime.now(),
        )
        descartes += descartes_dominio
        if trabajos:
            movidos, fallos = ejecutar_trabajos(trabajos, usuario.usuario, "mover")
        else:
            movidos, fallos = [], []
            invalidar_cache_pedidos()
        fallos = descartes + fallos
        registro_log.info(
            "%s movió %d de %d líneas de %s a %s",
            usuario.usuario,
            len(movidos),
            len(lote),
            cfg.area,
            destino,
        )

        color = "success" if not fallos else ("warning" if movidos else "danger")
        return (
            alerta(texto_resumen(len(lote), len(movidos), fallos, destino), color),
            [],
            (version or 0) + 1,
        )

    # __________________________________________LAYOUT___________________________________________
    def layout(**_parametros):
        puede = bool(destinos_permitidos(current_user, cfg))
        opciones_rejilla = {
            "localeText": TEXTOS_REJILLA,
            "suppressCellFocus": True,
            "animateRows": False,
            "enableCellTextSelection": True,
        }
        if puede:
            opciones_rejilla["rowSelection"] = {
                "mode": "multiRow",
                "checkboxes": True,
                "headerCheckbox": True,
                "selectAll": "filtered",
                "enableClickSelection": False,
            }

        filtros = dbc.Row(
            [
                dbc.Col(
                    dbc.Input(
                        id=id_,
                        placeholder=etiqueta,
                        type="search",
                        debounce=True,
                        size="sm",
                        value="",
                    ),
                    md=2,
                    xs=6,
                    className="mb-2",
                )
                for id_, (_, etiqueta, _) in zip(ids_filtro, FILTROS)
            ],
            className="g-2",
        )

        botones = html.Div(
            [
                dbc.Button(
                    "Actualizar",
                    id=ids["recargar"],
                    color="secondary",
                    outline=True,
                    size="sm",
                    className="me-2",
                ),
                dbc.Button(
                    "Limpiar filtros",
                    id=ids["limpiar"],
                    color="secondary",
                    outline=True,
                    size="sm",
                    className="me-2",
                ),
                dbc.Button(
                    "Exportar a Excel",
                    id=ids["btn-excel"],
                    color="success",
                    outline=True,
                    size="sm",
                    className="me-2",
                ),
                dbc.Button(
                    "Mover seleccionados",
                    id=ids["btn-mover"],
                    color="primary",
                    size="sm",
                    disabled=True,
                    style={} if puede else {"display": "none"},
                ),
            ],
            className="d-flex flex-wrap justify-content-end",
        )

        cabecera = dbc.Row(
            [
                dbc.Col(
                    [
                        html.H4(cfg.titulo, className="mb-0"),
                        html.Small(id=ids["resumen"], className="text-muted"),
                    ],
                    md=5,
                ),
                dbc.Col(
                    botones,
                    md=7,
                    className="d-flex align-items-center justify-content-end",
                ),
            ],
            className="mb-2 align-items-center",
        )

        rejilla = dag.AgGrid(
            id=ids["rejilla"],
            columnDefs=DEFINICION_COLUMNAS,
            rowData=[],
            getRowId="params.data.id",
            getRowStyle=estilo_filas(),
            defaultColDef={
                "sortable": True,
                "resizable": True,
                "suppressHeaderMenuButton": True,
            },
            dashGridOptions=opciones_rejilla,
            columnSize="responsiveSizeToFit",
            className="rejilla-sdbr",
            style={"height": "calc(100vh - 270px)", "minHeight": "420px"},
        )

        grafico = {"displaylogo": False, "displayModeBar": False}
        modal = dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle("Movimiento flujo de trabajo"), close_button=False
                ),
                dbc.ModalBody(
                    [
                        html.Div(id=ids["modal-aviso"], className="mb-2"),
                        html.Div(
                            id=ids["modal-lista"],
                            style={"maxHeight": "280px", "overflowY": "auto"},
                            className="mb-3",
                        ),
                        dbc.Row(
                            [
                                dbc.Label(
                                    "Proceso siguiente",
                                    width="auto",
                                    className="fw-bold",
                                ),
                                dbc.Col(
                                    dcc.Dropdown(
                                        id=ids["destino"],
                                        options=[],
                                        clearable=False,
                                        placeholder="Seleccione el destino",
                                    )
                                ),
                            ],
                            className="mb-3 align-items-center",
                        ),
                        html.Div(
                            dbc.Checkbox(
                                id=ids["confirmar"],
                                value=False,
                                label="Confirmo el movimiento de todos estos registros. "
                                "El movimiento no se puede deshacer.",
                            ),
                            id=ids["confirmar-fila"],
                            style={"display": "none"},
                            className="mb-3",
                        ),
                        dcc.Loading(html.Div(id=ids["resultado"]), type="dot"),
                    ]
                ),
                dbc.ModalFooter(
                    [
                        dbc.Button(
                            "Cerrar", id=ids["cerrar"], color="secondary", outline=True
                        ),
                        dbc.Button("Mover", id=ids["mover"], color="primary"),
                    ]
                ),
            ],
            id=ids["modal"],
            is_open=False,
            backdrop="static",
            size="lg",
            scrollable=True,
        )

        return html.Div(
            [
                cabecera,
                filtros,
                dbc.Alert(
                    id=ids["error"], color="danger", is_open=False, dismissable=True
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            dcc.Loading(rejilla, type="circle", delay_show=300),
                            lg=8,
                            className="mb-3",
                        ),
                        dbc.Col(
                            [
                                dcc.Graph(
                                    id=ids["torta"],
                                    config=grafico,
                                    style={"height": "330px"},
                                ),
                                dcc.Graph(
                                    id=ids["barras"],
                                    config=grafico,
                                    style={"height": "300px"},
                                ),
                            ],
                            lg=4,
                        ),
                    ]
                ),
                modal,
                dcc.Store(id=ids["version"], data=0),
                dcc.Store(id=ids["lote"], data=[]),
                dcc.Download(id=ids["descarga"]),
            ]
        )

    return layout
