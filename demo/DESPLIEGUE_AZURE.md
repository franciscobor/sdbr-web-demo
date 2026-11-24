# Demo en vivo en Azure, a 0 USD

La web corre en **Azure App Service F1 (Free)** y la base en **Azure SQL Database con la oferta
gratuita**. Configurada como se indica aquí, ninguna de las dos puede facturar:

- **App Service F1** es gratuito. Si agota sus 60 minutos de CPU diarios, la app se detiene hasta
  el día siguiente.
- **Azure SQL, oferta gratuita**: 100.000 vCore-segundos, 32 GB de datos y 32 GB de copias al mes
  por base, hasta 10 bases por suscripción. Con "pausar hasta el mes siguiente", al agotar la
  cuota la base se pausa en vez de cobrar.

Azure **no permite poner un tope de gasto** a una suscripción de pago por uso: los presupuestos
solo avisan. Por eso solo se usan servicios que no pueden facturar.

**No crees** Azure Container Registry (unos 5 USD al mes), Log Analytics ni Application Insights.
Tampoco cambies de plan la app ni la base.

## 0. Antes de empezar

- Una suscripción de Azure de pago por uso. La oferta gratuita de Azure SQL **no** sirve con
  "Azure for Students Starter".
- En *Cost Management → Budgets*, un presupuesto de **1 USD** con aviso por correo.
- Todo va en un grupo de recursos propio, por ejemplo `rg-sdbr-demo`. Borrarlo elimina todo.
- **Elige la región con cuidado**: la de la primera base gratuita queda fija para las 10 bases de
  la suscripción, también las del MTA. La app debe ir en la misma región.

## 1. Base de datos

En el portal:

1. *Azure SQL → SQL databases → Create*, y aplicar la oferta gratuita (*Apply offer*).
2. Crear el servidor (`sdbr-demo-<sufijo>.database.windows.net`) con autenticación SQL. Ese
   usuario y su contraseña son `SDBR_DEMO_ADMIN_USUARIO` y `SDBR_DEMO_ADMIN_PASSWORD`; guárdalos
   en tu gestor de contraseñas.
3. Base: `SDBR_DEMO`.
4. *Behavior when free limit is reached*: **Auto-pause the database until next month**.
5. *Networking*: punto de conexión público y **solo tu IP actual** en el firewall. No marques
   *Allow Azure services*.

## 2. Instalar la demo desde tu equipo

Crea `demo/azure.env`. No se versiona: está en `.gitignore`.

```
SDBR_MODO_DEMO=si
SDBR_SQL_SERVIDOR=sdbr-demo-<sufijo>.database.windows.net
SDBR_SQL_BASE=SDBR_DEMO
SDBR_SQL_USUARIO=sdbr_app
SDBR_SQL_PASSWORD=<contraseña nueva y larga para la app>
SDBR_ODBC_DRIVER=ODBC Driver 18 for SQL Server
SDBR_SQL_CONFIAR_CERTIFICADO=no
SDBR_SECRET_KEY=x
SDBR_DEMO_ADMIN_USUARIO=<administrador del servidor>
SDBR_DEMO_ADMIN_PASSWORD=<su contraseña>
```

```bash
./venv/Scripts/python.exe -m demo.instalar --env demo/azure.env
```

El instalador solo lee ese archivo, nunca tu entorno ni el `.env` de producción. Si la base estaba
en pausa y falla con el error 40613, vuelve a ejecutarlo al minuto.

## 3. La aplicación web

1. *App Services → Create → Web App*:
   - *Publish*: Code;
   - *Runtime*: Python 3.12;
   - *OS*: Linux;
   - la misma región;
   - plan nuevo **Free F1**.
2. **Primero, comprueba que es viable.** Abre *Development Tools → SSH* y ejecuta
   `odbcinst -q -d`:
   - si aparece `ODBC Driver 18 for SQL Server`, sigue;
   - si solo aparece el 17, usa `SDBR_ODBC_DRIVER=ODBC Driver 17 for SQL Server`;
   - si no aparece ninguno, **detente**: la alternativa (Container Apps) tiene un riesgo de cobro
     pequeño y hay que decidirla aparte.
3. *Settings → Environment variables*:

   | Variable | Valor |
   |---|---|
   | `SDBR_MODO_DEMO` | `si` |
   | `SDBR_SQL_SERVIDOR` | `sdbr-demo-<sufijo>.database.windows.net` |
   | `SDBR_SQL_BASE` | `SDBR_DEMO` |
   | `SDBR_SQL_USUARIO` / `SDBR_SQL_PASSWORD` | los de la app (`sdbr_app`), **no** los del administrador |
   | `SDBR_SQL_CONFIAR_CERTIFICADO` | `no` |
   | `SDBR_SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
   | `SDBR_COOKIE_SEGURA` | `si` |
   | `SDBR_HOST` / `SDBR_PUERTO` | `0.0.0.0` / `8000` |
   | `SDBR_HILOS` | `4` |
   | `TZ` | `America/Bogota` |
   | `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |

4. *Settings → Configuration → Startup Command*: `python servidor.py`. Es un solo proceso, como
   exige la caché compartida de la web.
5. No configures *Health check* contra una página que lea la base. `/salud` no la lee.
6. Firewall de la base: en la web, *Properties → Outbound IP addresses* (y las adicionales). Añade
   esas IP al firewall del servidor SQL y **quita la tuya** cuando termines de instalar.

## 4. Despliegue desde GitHub (OIDC, sin contraseñas guardadas)

1. *Microsoft Entra ID → App registrations → New registration*, por ejemplo `github-sdbr-demo`.
2. En ella, *Certificates & secrets → Federated credentials → Add*:
   - escenario *GitHub Actions*;
   - repositorio `<tu usuario>/sdbr-web-demo`;
   - entidad *Environment* `azure-demo`.
3. En la web app, *Access control (IAM) → Add role assignment*: **Website Contributor** para esa
   aplicación, solo sobre la web app.
4. En el repositorio, *Settings → Environments*, crear `azure-demo` con:
   - *secrets*: `AZURE_CLIENT_ID` (el *Application (client) ID*), `AZURE_TENANT_ID` y
     `AZURE_SUBSCRIPTION_ID`;
   - *variable*: `AZURE_WEBAPP_NAME`.
5. *Actions → Desplegar en Azure → Run workflow*.

## 5. Comprobar

- `https://<app>.azurewebsites.net`: la primera carga puede tardar alrededor de un minuto. F1 no
  tiene *Always On* y la base puede estar en pausa.
- Entra con `demo.operador` / `sdbr-demo` y mueve una línea.
- Al día siguiente, el primer login restablece la demo.
- *Cost Management*: el coste debe seguir en 0.

## Cuánto aguanta la cuota

Cada vez que la base despierta, consume vCore-segundos hasta que vuelve a pausarse. Por eso:

- no hay ninguna tarea programada;
- el restablecimiento se hace en el primer login del día;
- `/salud` no toca la base.

Con el tráfico de una demo de portafolio la cuota sobra. Si un mes se agotara, la demo quedaría
apagada hasta el día 1, sin coste.
