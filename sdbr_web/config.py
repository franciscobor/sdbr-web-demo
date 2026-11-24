###############################################################################################
################################ CONFIGURACIÓN DE LA APLICACIÓN ###############################
###############################################################################################
# Todo lo que cambia entre el equipo de desarrollo y el servidor sale de variables de entorno o
# del archivo .env de la raíz del repositorio (sin versionar; plantilla en .env.ejemplo).
# Ningún valor secreto vive en el código.
#
# pydantic-settings lee y valida las variables SDBR_* (_Entorno); el resto de la aplicación solo ve
# la Configuracion congelada. El usuario y la contraseña de SQL Server son obligatorios: si faltan o
# están vacíos, cargar_configuracion() se detiene nombrando la variable, en vez de arrancar y fallar
# después con un "Login failed" a cada consulta.

import secrets
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_REPOSITORIO = Path(__file__).resolve().parent.parent

_PREFIJO = "SDBR_"

# Los drivers modernos (ODBC Driver 17/18) aceptan Encrypt y TrustServerCertificate; el antiguo
# {SQL Server} que trae Windows no los conoce.
_DRIVERS_MODERNOS = ("ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server")

# Motivo legible de cada tipo de error de pydantic; los demás se muestran con su mensaje original.
_MOTIVOS = {
    "missing": "no está definida",
    "vacia": "está vacía",
    "int_parsing": "debe ser un número entero",
}


def _si(valor):
    return str(valor).strip().lower() in ("1", "si", "sí", "true", "yes")


class ErrorDeConfiguracion(ValueError):
    """Falta una variable obligatoria o alguna tiene un valor inválido."""


class _Entorno(BaseSettings):
    """Variables SDBR_* del entorno y del .env. Las del entorno tienen prioridad sobre el .env."""

    model_config = SettingsConfigDict(
        env_prefix=_PREFIJO,
        # Como python-dotenv. Sin esto, en Windows el .env se leería con la página de códigos local.
        env_file_encoding="utf-8",
        # El mismo .env lo lee el paquete de escritorio sdbr/: una variable que la web no usa no
        # es un error.
        extra="ignore",
    )

    # Sin valores de la planta en el código: el servidor y la base de producción van en el .env.
    sql_servidor: str = "localhost"
    sql_base: str = "SDBR"
    sql_usuario: str
    sql_password: SecretStr
    odbc_driver: str = "ODBC Driver 18 for SQL Server"
    sql_confiar_certificado: bool = True
    sql_timeout_seg: int = 30
    secret_key: SecretStr = SecretStr("")
    cookie_segura: bool = False
    host: str = "127.0.0.1"
    puerto: int = 8050
    hilos: int = 16
    # Marca: nombre de la empresa (vacío: solo "SDBR") y logotipo, un archivo de sdbr_web/assets.
    empresa: str = ""
    logo: str = "logo_sdbr.svg"
    # Demo pública con datos ficticios (ver demo/README.md). Nunca en producción.
    modo_demo: bool = False

    @field_validator("sql_usuario", "sql_password")
    @classmethod
    def _no_vacio(cls, valor):
        texto = valor.get_secret_value() if isinstance(valor, SecretStr) else valor
        if not texto.strip():
            raise PydanticCustomError("vacia", "está vacía")
        return valor

    @field_validator("logo")
    @classmethod
    def _logo_sin_rutas(cls, valor):
        # Se sirve como /assets/<logo>: un nombre de archivo, no una ruta ni una URL.
        if not valor.strip() or any(c in valor for c in "/\\:"):
            raise PydanticCustomError(
                "logo", "debe ser el nombre de un archivo de sdbr_web/assets"
            )
        return valor.strip()

    @field_validator(
        "sql_confiar_certificado", "cookie_segura", "modo_demo", mode="before"
    )
    @classmethod
    def _si_no(cls, valor):
        # La regla de siempre: "si", "sí", "1", "true" o "yes" es sí y cualquier otro texto es no.
        # pydantic no conoce "si" y rechazaría lo que no reconoce.
        return _si(valor) if isinstance(valor, str) else valor


class _SoloArchivo(_Entorno):
    """Las mismas variables, pero leídas SOLO del archivo: el entorno se ignora."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (init_settings, dotenv_settings)


# De dónde sale la configuración (ver cargar_configuracion).
ENTORNO_Y_ARCHIVO, SOLO_ARCHIVO, SOLO_ENTORNO = "entorno_y_archivo", "solo_archivo", "solo_entorno"


def _leer_entorno(archivo_env, origen=ENTORNO_Y_ARCHIVO):
    try:
        if origen == SOLO_ARCHIVO:
            if archivo_env is None or not Path(archivo_env).is_file():
                raise ErrorDeConfiguracion(f"No existe el archivo de configuración {archivo_env}.")
            return _SoloArchivo(_env_file=archivo_env)
        if origen == SOLO_ENTORNO:
            return _Entorno(_env_file=None)
        return _Entorno(_env_file=archivo_env or RAIZ_REPOSITORIO / ".env")
    except ValidationError as exc:
        # El mensaje de pydantic incluye los valores recibidos, contraseña incluida: se arma uno
        # propio con solo los nombres de las variables, y `from None` deja fuera el original.
        problemas = []
        for error in exc.errors(include_url=False, include_input=False):
            variable = _PREFIJO + str(error["loc"][0]).upper()
            problemas.append(f"{variable} {_MOTIVOS.get(error['type'], error['msg'])}")
        raise ErrorDeConfiguracion(
            "Configuración de SDBR Web incompleta o inválida: "
            + "; ".join(problemas)
            + ". Revise el entorno o el .env (plantilla en .env.ejemplo)."
        ) from None


@dataclass(frozen=True)
class Configuracion:
    sql_servidor: str
    sql_base: str
    sql_usuario: str
    sql_password: str = field(repr=False)
    odbc_driver: str
    sql_confiar_certificado: bool
    sql_timeout_seg: int
    secret_key: str = field(repr=False)
    cookie_segura: bool
    host: str
    puerto: int
    hilos: int
    empresa: str = ""
    logo: str = "logo_sdbr.svg"
    modo_demo: bool = False

    @property
    def cadena_odbc(self):
        """Cadena de conexión pyodbc. MARS se conserva por paridad con la versión de escritorio."""
        partes = [
            "DRIVER={" + self.odbc_driver + "}",
            "SERVER=" + self.sql_servidor,
            "DATABASE=" + self.sql_base,
            "UID=" + self.sql_usuario,
            "PWD=" + self.sql_password,
            "MARS_Connection=yes",
        ]
        if self.odbc_driver in _DRIVERS_MODERNOS:
            # El SQL Server interno no tiene un certificado emitido por una CA de confianza:
            # con el Driver 18 (Encrypt=yes por defecto) la conexión fallaría sin esto.
            partes.append("Encrypt=yes")
            if self.sql_confiar_certificado:
                partes.append("TrustServerCertificate=yes")
        return ";".join(partes) + ";"


def cargar_configuracion(archivo_env=None, origen=ENTORNO_Y_ARCHIVO):
    """Lee la configuración del entorno y del .env (si existe).

    Las variables ya definidas en el entorno (por ejemplo, las del servicio de Windows) tienen
    prioridad sobre el .env. Lanza ErrorDeConfiguracion si falta SDBR_SQL_USUARIO o
    SDBR_SQL_PASSWORD, o si un valor no tiene el tipo esperado.

    origen=SOLO_ARCHIVO lee únicamente `archivo_env` y SOLO_ENTORNO únicamente el entorno. Las
    herramientas de la demo nunca mezclan las dos fuentes: en un equipo con las variables de
    producción definidas, el entorno podría apuntar a la base real sin que nadie lo note.
    """
    entorno = _leer_entorno(archivo_env, origen)

    secret_key = entorno.secret_key.get_secret_value()
    if not secret_key:
        # Sin clave fija, cada reinicio invalida las sesiones abiertas. Sirve en desarrollo; en el
        # servidor SDBR_SECRET_KEY es obligatoria (ver despliegue).
        warnings.warn(
            "SDBR_SECRET_KEY no está definida: se usa una clave temporal y las sesiones "
            "se perderán al reiniciar.",
            RuntimeWarning,
            stacklevel=2,
        )
        secret_key = secrets.token_hex(32)

    return Configuracion(
        sql_servidor=entorno.sql_servidor,
        sql_base=entorno.sql_base,
        sql_usuario=entorno.sql_usuario,
        sql_password=entorno.sql_password.get_secret_value(),
        odbc_driver=entorno.odbc_driver,
        sql_confiar_certificado=entorno.sql_confiar_certificado,
        sql_timeout_seg=entorno.sql_timeout_seg,
        secret_key=secret_key,
        cookie_segura=entorno.cookie_segura,
        host=entorno.host,
        puerto=entorno.puerto,
        hilos=entorno.hilos,
        empresa=entorno.empresa.strip(),
        logo=entorno.logo,
        modo_demo=entorno.modo_demo,
    )
