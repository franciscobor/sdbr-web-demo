"""Arranque de SDBR Web con Waitress (servidor WSGI de producción que funciona en Windows).

Desde la raíz del repositorio:

    venv\\Scripts\\python.exe servidor.py            # producción / piloto
    venv\\Scripts\\python.exe servidor.py --debug    # herramientas de depuración de Dash

UN SOLO PROCESO con varios hilos: la caché de pedidos y la de usuarios viven en memoria y se
comparten entre todos los usuarios. Varios procesos tendrían cachés distintas y una pantalla no
vería los movimientos hechos desde otra.
"""

import argparse
import logging
from logging.handlers import RotatingFileHandler

from sdbr_web.config import RAIZ_REPOSITORIO, cargar_configuracion


def configurar_registro():
    carpeta = RAIZ_REPOSITORIO / "logs"
    carpeta.mkdir(exist_ok=True)
    formato = logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
    )
    archivo = RotatingFileHandler(
        carpeta / "sdbr_web.log", maxBytes=5_000_000, backupCount=10, encoding="utf-8"
    )
    archivo.setFormatter(formato)
    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(archivo)
    raiz.addHandler(consola)


def main():
    analizador = argparse.ArgumentParser(description="Servidor de SDBR Web")
    analizador.add_argument(
        "--debug",
        action="store_true",
        help="servidor de desarrollo de Dash con recarga y herramientas de depuración",
    )
    args = analizador.parse_args()

    configurar_registro()
    config = cargar_configuracion()

    from sdbr_web.app import crear_app

    app = crear_app(config)
    logging.getLogger(__name__).info(
        "SDBR Web en http://%s:%s (%s hilos)", config.host, config.puerto, config.hilos
    )
    if args.debug:
        app.run(host=config.host, port=config.puerto, debug=True)
        return

    from waitress import serve

    serve(
        app.server,
        host=config.host,
        port=config.puerto,
        threads=config.hilos,
        ident="SDBR",
    )


if __name__ == "__main__":
    main()
