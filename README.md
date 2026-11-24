# SDBR Web · demo

> **English summary.** Web version of an S-DBR (*Simplified Drum-Buffer-Rope*, Theory of
> Constraints) production-flow system, migrated from a Tkinter desktop app to Flask + Dash. This
> repository is a public demo: same code as the production system, running against a SQL Server
> database filled with **synthetic data** for a fictitious company. Run it locally with
> `docker compose up --build` and open <http://localhost:8050>.

SDBR Web gestiona el flujo de pedidos de una planta de manufactura según la metodología
**S-DBR** de la Teoría de Restricciones: cada línea de pedido avanza por Ingeniería → Ops →
Almacén → Producción → Despachos, y en cada área se prioriza por el **buffer consumido**, con
cinco zonas de color.

| Zona | Buffer consumido | Significado |
|---|---|---|
| Blanco | < 0 % | todavía no se ha liberado |
| Verde | 0–33 % | va con tiempo |
| Amarillo | 33–66 % | estable |
| Rojo | 66–100 % | a punto de vencer |
| Negro | > 100 % | atrasado |

Es la migración a web de un sistema de escritorio que se usa en una planta real. **Esta demo usa
una empresa ficticia y datos inventados**: el código es el mismo, solo cambia la base de datos.

## Pruébalo

Necesitas Docker Desktop.

```bash
docker compose up --build
```

Abre <http://localhost:8050>. Todas las cuentas usan la contraseña `sdbr-demo`:

| Usuario | Rol | Qué puede hacer |
|---|---|---|
| `demo.consulta` | consulta | Ve las pantallas y exporta a Excel |
| `demo.operador` | operador | Mueve los pedidos que salen de Ingeniería y de Ops |
| `demo.supervisor` | supervisor | Mueve desde cualquier área, también hacia Derogación |

En la pantalla **S-DBR → Ingeniería** puedes:

- filtrar por pedido, cliente, producto, descripción, fecha o familia;
- exportar a Excel lo que estás viendo;
- mover un pedido con doble clic, o varios a la vez marcándolos.

Cada movimiento es una transacción y queda auditado. Los cambios son compartidos y la base vuelve
a su estado inicial cada día.

Compose levanta tres contenedores:

1. **SQL Server 2022**, edición Developer.
2. Un **instalador** que crea la base `SDBR_DEMO` con 150 pedidos ficticios y termina.
3. La **web**, que se conecta con un usuario de permisos mínimos.

## Arquitectura

```
Navegador ──► Waitress (un proceso, varios hilos)
               └─ Flask: login, sesión de 12 h y guardia de acceso
                   └─ Dash multipágina: rejilla AG Grid, gráficos Plotly y callbacks
                       ├─ dominio/  lógica pura y probada: buffer, zonas, filtros, permisos, movimientos
                       └─ datos/    pool SQLAlchemy + pyodbc → SQL Server (todo parametrizado)
```

Decisiones de diseño:

- **Ninguna conexión compartida.** Cada callback pide una conexión al pool: pyodbc no admite
  compartir conexiones entre hilos.
- **Del navegador solo se aceptan claves** (pedido y producto). El buffer, la calificación y los
  permisos se recalculan en el servidor con datos recién leídos.
- **Cada movimiento es una transacción**: UPDATE, historial y auditoría. El UPDATE exige que la
  línea siga en el área de origen: si otro usuario ya la movió, el movimiento falla y se avisa.
- **Usuarios propios**: hash scrypt, bloqueo tras 5 intentos fallidos, cambio de contraseña
  obligatorio en el primer acceso y roles `consulta` < `operador` < `supervisor` < `admin`. En la
  demo, las cuentas compartidas no se bloquean ni pueden cambiar su contraseña.
- **Una sola fábrica de pantallas.** La aplicación de escritorio tenía siete copias casi idénticas
  de cada pantalla del flujo; aquí cada una es una configuración (`ConfigPantalla`).
- **Sin CDN.** Bootstrap y los recursos se sirven desde la propia aplicación, porque la red de la
  planta puede no tener Internet.

### La base de demo

`demo/sql/` reproduce, con los mismos nombres y columnas, solo los objetos que la web lee y
escribe en producción (su "contrato"): la vista de pedidos en planta, la tabla de estados, el
historial de movimientos y las tablas de usuarios y auditoría. `demo/generar_datos.py` inventa
los pedidos con una semilla fija.

La vista **desplaza las fechas** según los días transcurridos desde la generación, así que el
reparto de colores no envejece. `demo/instalar.py` se niega a ejecutarse contra cualquier base
que no esté vacía o sea de demo, y contra cualquier servidor de una red privada.

## Desarrollo

Requisitos: Python 3.12 y el
[ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).

```bash
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt     # en Linux/Mac: venv/bin/python

./venv/Scripts/python.exe -m pytest                              # pruebas unitarias, sin base
./venv/Scripts/python.exe -m pyflakes sdbr_web servidor.py tests demo

docker compose up -d sqlserver                                   # solo SQL Server
SDBR_PRUEBAS_INTEGRACION=si ./venv/Scripts/python.exe -m pytest tests_integracion
```

Para ejecutar la web fuera de Docker: `python -m demo.instalar` y luego `cp .env.ejemplo .env` y
`python servidor.py`.

El CI de GitHub Actions corre las pruebas unitarias, las de integración contra un SQL Server 2022
real y la construcción de la imagen.

## Estructura

```
sdbr_web/     la aplicación: app, config, dominio/, datos/, componentes/, paginas/, plantillas/
demo/         base de demo: sql/, generador de datos, instalador y despliegue en Azure
tests/        pruebas unitarias (no tocan ninguna base)
tests_integracion/   pruebas contra SQL Server
```

## Estado

La aplicación de escritorio sigue en producción mientras dura la migración. En la web ya están el
acceso con usuarios propios y la pantalla de Ingeniería; el resto de pantallas del flujo, las de
mejora continua (Poogi) y los dashboards se migran por fases.

---

Todos los derechos reservados. El código se publica como muestra de trabajo (portafolio); no se
concede licencia de uso.
