"""Lectura de la configuración. Cada prueba usa su propio .env (o ninguno), nunca el del repositorio."""

import pytest
from sdbr_web.config import ErrorDeConfiguracion, cargar_configuracion

PASSWORD_DE_PRUEBA = "clave+con+mas"


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Entorno mínimo y válido; devuelve la ruta de un .env (vacío) que la prueba puede rellenar."""
    for nombre in (
        "SDBR_SQL_SERVIDOR",
        "SDBR_SQL_BASE",
        "SDBR_ODBC_DRIVER",
        "SDBR_SQL_CONFIAR_CERTIFICADO",
        "SDBR_SQL_TIMEOUT_SEG",
        "SDBR_COOKIE_SEGURA",
        "SDBR_HOST",
        "SDBR_PUERTO",
        "SDBR_HILOS",
        "SDBR_EMPRESA",
        "SDBR_LOGO",
        "SDBR_MODO_DEMO",
    ):
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("SDBR_SQL_USUARIO", "nadie")
    monkeypatch.setenv("SDBR_SQL_PASSWORD", PASSWORD_DE_PRUEBA)
    monkeypatch.setenv("SDBR_SECRET_KEY", "clave-de-pruebas")
    archivo = tmp_path / ".env"
    archivo.write_text("", encoding="utf-8")
    return archivo


def test_valores_por_defecto(entorno):
    config = cargar_configuracion(entorno)
    # Sin valores de la planta en el código: el servidor y la base reales van en el .env.
    assert config.sql_servidor == "localhost"
    assert config.sql_base == "SDBR"
    assert config.odbc_driver == "ODBC Driver 18 for SQL Server"
    assert config.sql_confiar_certificado is True
    assert config.cookie_segura is False
    assert (config.sql_timeout_seg, config.puerto, config.hilos) == (30, 8050, 16)
    assert config.host == "127.0.0.1"
    assert (config.empresa, config.logo, config.modo_demo) == ("", "logo_sdbr.svg", False)


@pytest.mark.parametrize("variable", ["SDBR_SQL_USUARIO", "SDBR_SQL_PASSWORD"])
def test_credencial_ausente_nombra_la_variable(entorno, monkeypatch, variable):
    monkeypatch.delenv(variable)
    with pytest.raises(ErrorDeConfiguracion, match=variable):
        cargar_configuracion(entorno)


@pytest.mark.parametrize("variable", ["SDBR_SQL_USUARIO", "SDBR_SQL_PASSWORD"])
@pytest.mark.parametrize("valor", ["", "   "])
def test_credencial_vacia_nombra_la_variable(entorno, monkeypatch, variable, valor):
    monkeypatch.setenv(variable, valor)
    with pytest.raises(ErrorDeConfiguracion, match=variable + " está vacía"):
        cargar_configuracion(entorno)


def test_el_error_no_muestra_la_password(entorno, monkeypatch):
    monkeypatch.delenv("SDBR_SQL_USUARIO")
    with pytest.raises(ErrorDeConfiguracion) as error:
        cargar_configuracion(entorno)
    assert PASSWORD_DE_PRUEBA not in str(error.value)
    assert (
        error.value.__suppress_context__
    )  # el ValidationError original no sale en la traza


def test_entero_invalido_sigue_siendo_value_error(entorno, monkeypatch):
    monkeypatch.setenv("SDBR_PUERTO", "ochenta")
    with pytest.raises(ValueError, match="SDBR_PUERTO"):
        cargar_configuracion(entorno)


def test_el_entorno_manda_sobre_el_env(entorno):
    entorno.write_text(
        "SDBR_SQL_USUARIO=del-archivo\nSDBR_SQL_BASE=PRODUCCIÓN\nSDBR_VARIABLE_DEL_ESCRITORIO=x\n",
        encoding="utf-8",
    )
    config = cargar_configuracion(entorno)
    assert config.sql_usuario == "nadie"  # del entorno
    assert config.sql_base == "PRODUCCIÓN"  # solo está en el .env, leído en UTF-8


def test_credenciales_desde_el_env(entorno, monkeypatch):
    monkeypatch.delenv("SDBR_SQL_USUARIO")
    monkeypatch.delenv("SDBR_SQL_PASSWORD")
    entorno.write_text(
        f"SDBR_SQL_USUARIO=del-archivo\nSDBR_SQL_PASSWORD={PASSWORD_DE_PRUEBA}\n",
        encoding="utf-8",
    )
    config = cargar_configuracion(entorno)
    assert config.sql_usuario == "del-archivo"
    assert config.sql_password == PASSWORD_DE_PRUEBA


def test_la_password_con_mas_llega_intacta_a_la_cadena(entorno):
    config = cargar_configuracion(entorno)
    assert "PWD=" + PASSWORD_DE_PRUEBA + ";" in config.cadena_odbc


def test_repr_no_muestra_secretos(entorno):
    texto = repr(cargar_configuracion(entorno))
    assert PASSWORD_DE_PRUEBA not in texto
    assert "clave-de-pruebas" not in texto


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("si", True),
        ("Sí", True),
        ("1", True),
        ("yes", True),
        ("no", False),
        ("quizás", False),
    ],
)
def test_si_no(entorno, monkeypatch, valor, esperado):
    monkeypatch.setenv("SDBR_COOKIE_SEGURA", valor)
    monkeypatch.setenv("SDBR_SQL_CONFIAR_CERTIFICADO", valor)
    config = cargar_configuracion(entorno)
    assert config.cookie_segura is esperado
    assert config.sql_confiar_certificado is esperado


def test_sin_secret_key_avisa_y_usa_una_temporal(entorno, monkeypatch):
    monkeypatch.setenv("SDBR_SECRET_KEY", "")
    with pytest.warns(RuntimeWarning, match="SDBR_SECRET_KEY"):
        config = cargar_configuracion(entorno)
    assert len(config.secret_key) == 64


def test_marca_y_modo_demo(entorno, monkeypatch):
    monkeypatch.setenv("SDBR_EMPRESA", "  Empresa Ejemplo  ")
    monkeypatch.setenv("SDBR_LOGO", "logo.png")
    monkeypatch.setenv("SDBR_MODO_DEMO", "sí")
    config = cargar_configuracion(entorno)
    assert (config.empresa, config.logo, config.modo_demo) == (
        "Empresa Ejemplo",
        "logo.png",
        True,
    )


@pytest.mark.parametrize("logo", ["../secreto.png", "https://otro.sitio/logo.png", " "])
def test_el_logo_es_un_archivo_de_assets(entorno, monkeypatch, logo):
    monkeypatch.setenv("SDBR_LOGO", logo)
    with pytest.raises(ErrorDeConfiguracion, match="SDBR_LOGO"):
        cargar_configuracion(entorno)
