###############################################################################################
###################################### USUARIOS DE SDBR WEB ###################################
###############################################################################################
# Tablas SDBR_Usuarios y SDBR_Usuarios_Areas (sql/06_usuarios_auditoria.sql). Las contraseñas se
# guardan con hash scrypt de werkzeug.security y se comparan con check_password_hash.

import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from sdbr_web.datos import auditoria
from sdbr_web.datos.conexion import obtener_engine, transaccion
from sdbr_web.dominio.permisos import AREAS_ASIGNABLES, ROLES, Usuario

MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15
LONGITUD_MINIMA = 8
MENSAJE_CREDENCIALES = "Usuario o contraseña incorrectos."

# Hash de una contraseña cualquiera: se comprueba contra él cuando el usuario no existe, para que
# la respuesta tarde lo mismo exista o no (no revela qué usuarios hay).
_HASH_SEÑUELO = generate_password_hash("señuelo-sdbr")

_SQL_POR_NOMBRE = (
    "SELECT Id, Usuario, Nombre, Hash_Password, Rol, Activo, Debe_Cambiar_Password, "
    "Intentos_Fallidos, Bloqueado_Hasta FROM SDBR_Usuarios WHERE Usuario = :usuario"
)
_SQL_POR_ID = (
    "SELECT Id, Usuario, Nombre, Rol, Activo, Debe_Cambiar_Password "
    "FROM SDBR_Usuarios WHERE Id = :id"
)
_SQL_AREAS = "SELECT Area FROM SDBR_Usuarios_Areas WHERE Usuario_Id = :id"

# Flask-Login carga el usuario en CADA petición, y Dash hace muchas: se guarda 30 s.
_CACHE_TTL_SEG = 30
_cache = {}
_cache_lock = threading.Lock()


# __________________________________REGLAS (SIN BASE DE DATOS)__________________________________


def validar_password_nueva(usuario, nueva, repetida=None):
    """Devuelve el motivo por el que la contraseña no vale, o None si vale."""
    if repetida is not None and nueva != repetida:
        return "Las dos contraseñas no coinciden."
    if len(nueva or "") < LONGITUD_MINIMA:
        return f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres."
    if nueva.strip().lower() == (usuario or "").strip().lower():
        return "La contraseña no puede ser igual al usuario."
    return None


def estado_tras_fallo(intentos_previos, ahora):
    """(intentos, bloqueado_hasta) tras un intento fallido. Al llegar al máximo se bloquea."""
    intentos = (intentos_previos or 0) + 1
    if intentos >= MAX_INTENTOS:
        return 0, ahora + timedelta(minutes=MINUTOS_BLOQUEO)
    return intentos, None


def _usuario_desde_fila(fila, areas):
    return Usuario(
        id=int(fila["Id"]),
        usuario=fila["Usuario"],
        nombre=fila["Nombre"],
        rol=fila["Rol"],
        areas=frozenset(areas),
        activo=bool(fila["Activo"]),
        debe_cambiar_password=bool(fila["Debe_Cambiar_Password"]),
    )


# __________________________________________CONSULTAS___________________________________________


def _areas(conexion, id_usuario):
    return [
        str(a).strip()
        for a in conexion.execute(text(_SQL_AREAS), {"id": id_usuario}).scalars()
    ]


def cargar_usuario(id_usuario):
    """Usuario por id (para Flask-Login), o None si no existe o está desactivado."""
    try:
        id_usuario = int(id_usuario)
    except (TypeError, ValueError):
        return None
    ahora = time.monotonic()
    with _cache_lock:
        guardado = _cache.get(id_usuario)
        if guardado and ahora - guardado[1] < _CACHE_TTL_SEG:
            return guardado[0]
    with obtener_engine().connect() as conexion:
        fila = (
            conexion.execute(text(_SQL_POR_ID), {"id": id_usuario}).mappings().first()
        )
        usuario = None
        if fila is not None and fila["Activo"]:
            usuario = _usuario_desde_fila(fila, _areas(conexion, id_usuario))
    with _cache_lock:
        _cache[id_usuario] = (usuario, ahora)
    return usuario


def olvidar_usuario(id_usuario):
    """Tras cambiar un usuario, para que la próxima petición lo relea."""
    with _cache_lock:
        _cache.pop(int(id_usuario), None)


def autenticar(nombre_usuario, password, ahora=None, bloquear=True):
    """Comprueba las credenciales. Devuelve (Usuario, None) o (None, mensaje para el usuario).

    bloquear=False (solo en la demo pública, de cuentas compartidas) no cuenta los fallos ni
    bloquea la cuenta: si no, cualquier visitante podría dejar la demo sin acceso 15 minutos.
    """
    ahora = ahora or datetime.now()
    nombre_usuario = (nombre_usuario or "").strip()
    with transaccion() as conexion:
        fila = (
            conexion.execute(text(_SQL_POR_NOMBRE), {"usuario": nombre_usuario})
            .mappings()
            .first()
        )
        if fila is None:
            check_password_hash(_HASH_SEÑUELO, password or "")
            return None, MENSAJE_CREDENCIALES
        if (
            bloquear
            and fila["Bloqueado_Hasta"] is not None
            and fila["Bloqueado_Hasta"] > ahora
        ):
            hora = fila["Bloqueado_Hasta"].strftime("%H:%M")
            return (
                None,
                f"La cuenta está bloqueada por intentos fallidos hasta las {hora}.",
            )
        if not check_password_hash(fila["Hash_Password"], password or ""):
            if not bloquear:
                return None, MENSAJE_CREDENCIALES
            intentos, bloqueo = estado_tras_fallo(fila["Intentos_Fallidos"], ahora)
            conexion.execute(
                text(
                    "UPDATE SDBR_Usuarios SET Intentos_Fallidos = :intentos, Bloqueado_Hasta = :bloqueo "
                    "WHERE Id = :id"
                ),
                {"intentos": intentos, "bloqueo": bloqueo, "id": fila["Id"]},
            )
            if bloqueo is not None:
                auditoria.registrar(conexion, fila["Usuario"], "bloqueo_cuenta")
                return None, (
                    f"Demasiados intentos fallidos: la cuenta queda bloqueada "
                    f"{MINUTOS_BLOQUEO} minutos."
                )
            return None, MENSAJE_CREDENCIALES
        if not fila["Activo"]:
            return (
                None,
                "La cuenta está desactivada. Consulte con el administrador de SDBR.",
            )
        conexion.execute(
            text(
                "UPDATE SDBR_Usuarios SET Intentos_Fallidos = 0, Bloqueado_Hasta = NULL, "
                "Ultimo_Acceso = :ahora WHERE Id = :id"
            ),
            {"ahora": ahora, "id": fila["Id"]},
        )
        usuario = _usuario_desde_fila(fila, _areas(conexion, fila["Id"]))
    olvidar_usuario(usuario.id)
    return usuario, None


# __________________________________________ESCRITURAS__________________________________________


def cambiar_password(usuario, actual, nueva, repetida):
    """Cambio de contraseña del propio usuario. Devuelve un mensaje de error o None si se hizo."""
    error = validar_password_nueva(usuario.usuario, nueva, repetida)
    if error:
        return error
    if actual == nueva:
        return "La contraseña nueva debe ser distinta de la actual."
    with transaccion() as conexion:
        hash_actual = conexion.execute(
            text("SELECT Hash_Password FROM SDBR_Usuarios WHERE Id = :id"),
            {"id": usuario.id},
        ).scalar()
        if hash_actual is None or not check_password_hash(hash_actual, actual or ""):
            return "La contraseña actual no es correcta."
        conexion.execute(
            text(
                "UPDATE SDBR_Usuarios SET Hash_Password = :hash, Debe_Cambiar_Password = 0 WHERE Id = :id"
            ),
            {"hash": generate_password_hash(nueva), "id": usuario.id},
        )
        auditoria.registrar(conexion, usuario.usuario, "cambio_password")
    olvidar_usuario(usuario.id)
    return None


def crear_usuario(
    nombre_usuario,
    nombre,
    password,
    rol,
    areas=(),
    debe_cambiar=True,
    creado_por="sistema",
):
    """Crea un usuario y devuelve su id. Lanza ValueError si los datos no son válidos."""
    nombre_usuario = (nombre_usuario or "").strip()
    if not nombre_usuario or not (nombre or "").strip():
        raise ValueError("El usuario y el nombre son obligatorios.")
    if rol not in ROLES:
        raise ValueError(f"Rol no válido: {rol}. Debe ser uno de {', '.join(ROLES)}.")
    areas = [a.strip() for a in areas if a and a.strip()]
    desconocidas = [a for a in areas if a not in AREAS_ASIGNABLES]
    if desconocidas:
        raise ValueError(
            f"Áreas no válidas: {', '.join(desconocidas)}. "
            f"Válidas: {', '.join(AREAS_ASIGNABLES)} (Ops se escribe Planeacion)."
        )
    error = validar_password_nueva(nombre_usuario, password)
    if error:
        raise ValueError(error)
    with transaccion() as conexion:
        nuevo_id = conexion.execute(
            text(
                "INSERT INTO SDBR_Usuarios (Usuario, Nombre, Hash_Password, Rol, Debe_Cambiar_Password) "
                "OUTPUT INSERTED.Id VALUES (:usuario, :nombre, :hash, :rol, :cambiar)"
            ),
            {
                "usuario": nombre_usuario,
                "nombre": nombre.strip(),
                "hash": generate_password_hash(password),
                "rol": rol,
                "cambiar": 1 if debe_cambiar else 0,
            },
        ).scalar()
        for area in areas:
            conexion.execute(
                text(
                    "INSERT INTO SDBR_Usuarios_Areas (Usuario_Id, Area) VALUES (:id, :area)"
                ),
                {"id": nuevo_id, "area": area},
            )
        auditoria.registrar(
            conexion,
            creado_por,
            "crear_usuario",
            detalle={"usuario": nombre_usuario, "rol": rol, "areas": areas},
        )
    return int(nuevo_id)


def restablecer_password(nombre_usuario, nueva, por="sistema"):
    """Pone una contraseña temporal, desbloquea la cuenta y obliga a cambiarla al entrar."""
    error = validar_password_nueva(nombre_usuario, nueva)
    if error:
        raise ValueError(error)
    with transaccion() as conexion:
        id_usuario = conexion.execute(
            text("SELECT Id FROM SDBR_Usuarios WHERE Usuario = :u"),
            {"u": nombre_usuario},
        ).scalar()
        if id_usuario is None:
            raise ValueError(f"No existe el usuario {nombre_usuario}.")
        conexion.execute(
            text(
                "UPDATE SDBR_Usuarios SET Hash_Password = :hash, Debe_Cambiar_Password = 1, "
                "Intentos_Fallidos = 0, Bloqueado_Hasta = NULL WHERE Id = :id"
            ),
            {"hash": generate_password_hash(nueva), "id": id_usuario},
        )
        auditoria.registrar(
            conexion, por, "restablecer_password", detalle={"usuario": nombre_usuario}
        )
    olvidar_usuario(id_usuario)
