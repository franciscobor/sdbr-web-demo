# La base de demo: cómo se construye (y cómo repetirlo en otro proyecto)

Esta carpeta convierte SDBR Web en una demo pública **sin cambiar su código**. La aplicación se
conecta a una base SQL Server con datos inventados que tiene los mismos nombres y columnas que la
de producción. El método está pensado para repetirse tal cual en otros sistemas, como la futura
versión web del MTA.

| Archivo | Qué hace |
|---|---|
| `sql/01_esquema.sql` | Réplica del contrato de datos del flujo S-DBR y la vista de pedidos con fechas vivas |
| `sql/02_usuarios_auditoria.sql` | Las tablas de usuarios y auditoría de la web |
| `sql/03_procedimientos.sql` | Restablecimiento diario (`Demo_Reiniciar_Si_Toca`) |
| `generar_datos.py` | Pedidos, líneas e historial sintéticos con semilla fija (módulo puro) |
| `instalar.py` | Crea o rehace la base, con guardias contra producción |
| `docker.env` | Variables del SQL Server de Docker (contraseñas solo locales) |
| `DESPLIEGUE_AZURE.md` | La demo en vivo a 0 USD: Azure SQL gratuita + App Service F1 |

## El método, en seis pasos

1. **Inventariar el contrato de datos.** Se buscan en el código de la web todos los objetos que
   lee y escribe (`git grep -nE "FROM|JOIN|INTO|UPDATE" -- <paquete web>`). Se replican esos
   objetos y nada más: ni las vistas intermedias ni el ERP.
2. **Replicarlo en T-SQL** con los mismos nombres, columnas y tipos compatibles (`sql/`). Si en
   producción una vista sale de diez tablas, aquí sale de una tabla `Demo_*` que llena el
   generador. Lo que la web escribe (aquí, `SDBR_MOV` y `Mov_Tiempo_Real3`) son tablas de verdad,
   para que los movimientos se vean en la vista.
3. **Generar datos sintéticos con semilla fija** (`generar_datos.py`):
   - reproducibles y sin ningún dato real;
   - con todos los casos que la interfaz debe mostrar (aquí, las cinco zonas de color, líneas sin
     familia y buffers no calculables);
   - un módulo puro, probado sin base (`tests/test_demo_datos.py`).
4. **Fechas vivas.** Los datos se generan una vez, pero la vista suma a todas las fechas los días
   transcurridos desde la generación, y el restablecimiento hace lo mismo con el historial. La
   demo se ve igual hoy que dentro de un año.
5. **Instalar con guardias** (`instalar.py`). Se niega a ejecutarse si:
   - `SDBR_MODO_DEMO` no es "si";
   - la base tiene algún objeto que no sea de la demo;
   - el servidor es una IP de red privada.

   Lee una sola fuente de configuración, un archivo o el entorno, y nunca las mezcla: en un
   equipo de desarrollo el entorno puede tener las variables de producción. La aplicación se
   conecta con un usuario de permisos mínimos que crea el propio instalador.
6. **Publicar por lista blanca.** El repositorio público no es una copia del privado: un script
   del repositorio privado copia solo una lista de archivos, busca en ellos rastros de la empresa
   (nombre, servidores, cuentas, rutas de red, correos) y corre las pruebas sobre el árbol
   exportado. Solo si todo está limpio sustituye el contenido del clon público. El commit y el
   push los hace una persona.

El **modo demo** de la aplicación (`SDBR_MODO_DEMO=si`) añade lo que una demo pública necesita y
producción no:

- un aviso de datos ficticios;
- las cuentas compartidas en la página de login, sin bloqueo por intentos fallidos y sin poder
  cambiar su contraseña;
- el restablecimiento diario, perezoso, en el primer login de cada día;
- reintentos de conexión mientras Azure SQL despierta de su pausa.

## Regla para las pantallas nuevas

Cada pantalla que se migre y lea un objeto que no esté en `sql/` añade aquí su réplica, sus datos
en `generar_datos.py` y su nombre en `OBJETOS_DEMO` de `instalar.py`. Una prueba comprueba que
`OBJETOS_DEMO` coincide con lo que crean los scripts.

## Para el MTA

Se copian `instalar.py` (cambiando `OBJETOS_DEMO`), `docker-compose.yml`, `Dockerfile` y los
workflows. Se escriben de nuevo:

- el `sql/` con el contrato del MTA;
- su generador (inventario, consumos y buffers de stock en vez de pedidos);
- su `docker.env`.

En Azure, el MTA usa otra de las 10 bases gratuitas de la **misma suscripción y región** y otra
app F1.
