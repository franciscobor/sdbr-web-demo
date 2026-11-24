"""Páginas de SDBR Web.

Se registran de forma explícita (Dash Pages con pages_folder=""), no escaneando una carpeta: así
cada módulo se importa una sola vez y con su nombre real de paquete. Para añadir una pantalla,
crear su módulo con dash.register_page(...) y añadirlo a MODULOS.
"""

import importlib

MODULOS = (
    "sdbr_web.paginas.inicio",
    "sdbr_web.paginas.sdbr.ingenieria",
)


def registrar_paginas():
    for modulo in MODULOS:
        importlib.import_module(modulo)
