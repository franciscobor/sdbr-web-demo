###############################################################################################
############################ ADMINISTRACIÓN DE USUARIOS DESDE CONSOLA #########################
###############################################################################################
# Sirve para crear el primer administrador (la web todavía no tiene a nadie que pueda entrar) y
# para resolver incidencias sin la interfaz. Desde la raíz del repositorio:
#
#   venv\Scripts\python.exe -m sdbr_web.usuarios crear-admin <usuario> --nombre "Nombre Apellido"
#   venv\Scripts\python.exe -m sdbr_web.usuarios crear <usuario> --nombre "..." --rol operador --areas Ingenieria Planeacion
#   venv\Scripts\python.exe -m sdbr_web.usuarios restablecer <usuario>
#
# La contraseña se pide por teclado (no queda en el historial de la consola) y el usuario tendrá
# que cambiarla la primera vez que entre.

import argparse
import getpass
import sys

from sdbr_web.config import cargar_configuracion
from sdbr_web.datos import conexion
from sdbr_web.datos.usuarios import crear_usuario, restablecer_password
from sdbr_web.dominio.permisos import ADMIN, AREAS_ASIGNABLES, ROLES


def _pedir_password():
    primera = getpass.getpass("Contraseña temporal: ")
    segunda = getpass.getpass("Repita la contraseña: ")
    if primera != segunda:
        sys.exit("Las contraseñas no coinciden.")
    return primera


def main(argumentos=None):
    analizador = argparse.ArgumentParser(
        prog="python -m sdbr_web.usuarios", description="Usuarios de SDBR Web"
    )
    ordenes = analizador.add_subparsers(dest="orden", required=True)

    admin = ordenes.add_parser("crear-admin", help="crea un usuario administrador")
    admin.add_argument("usuario")
    admin.add_argument("--nombre", required=True)

    crear = ordenes.add_parser("crear", help="crea un usuario con cualquier rol")
    crear.add_argument("usuario")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--rol", required=True, choices=ROLES)
    crear.add_argument(
        "--areas",
        nargs="*",
        default=[],
        choices=AREAS_ASIGNABLES,
        help="áreas desde las que puede mover un operador (Ops = Planeacion)",
    )

    restablecer = ordenes.add_parser(
        "restablecer", help="contraseña temporal y desbloqueo"
    )
    restablecer.add_argument("usuario")

    args = analizador.parse_args(argumentos)
    conexion.configurar(cargar_configuracion())

    try:
        if args.orden == "crear-admin":
            nuevo = crear_usuario(
                args.usuario,
                args.nombre,
                _pedir_password(),
                ADMIN,
                creado_por="consola",
            )
            print(f"Administrador {args.usuario} creado (id {nuevo}).")
        elif args.orden == "crear":
            nuevo = crear_usuario(
                args.usuario,
                args.nombre,
                _pedir_password(),
                args.rol,
                args.areas,
                creado_por="consola",
            )
            print(f"Usuario {args.usuario} creado (id {nuevo}).")
        elif args.orden == "restablecer":
            restablecer_password(args.usuario, _pedir_password(), por="consola")
            print(
                f"Contraseña de {args.usuario} restablecida. Deberá cambiarla al entrar."
            )
    except ValueError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
