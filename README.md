# NOC Alerts Tool

## Descripción

Herramienta de automatización para el equipo NOC. Consulta alertas críticas de NewRelic via Noctools, cruza con tickets de Jira y genera mensajes formateados para escalar por Slack y Telegram. Incluye registro de escalamientos con detalle de servicio y canal al cual se escala.

---

## Requisitos

- Python 3.8+
- Google Chrome instalado
- Acceso a Noctools
- Bot Token de Slack configurado (por organización o por workspace)
- Bot Token de Telegram configurado
- `pip install pip_system_certs` (requerido en entornos con proxy corporativo que intercepta HTTPS)

> ⚠️ En entornos corporativos con proxy que intercepta tráfico HTTPS (ej: proxy corporativo, firewall), las llamadas a la API de Slack pueden fallar con `SSL: CERTIFICATE_VERIFY_FAILED`. Instalar `pip_system_certs` para que Python use el almacén de certificados de Windows en lugar de su propio almacén.

---

## Archivos del proyecto

| Archivo | Descripción |
|---|---|
| `noctools_alerts.py` | Script principal |
| `.env` | Credenciales y configuración (no subir a GitHub) |
| `canales.csv` | Base de mapeo de servicios → canales Slack y grupos Telegram (no subir a GitHub) |
| `alerts.log` | Registro de escalados (no subir a GitHub) |
| `chromedriver.exe` | Driver para Selenium (no subir a GitHub) |

> ⚠️ `.env`, `canales.csv`, `alerts.log` y `chromedriver.exe` están excluidos del repositorio via `.gitignore`.

---

## Instalación

1. Clonar el repositorio

```bash
git clone https://github.com/asampedro/noctools.git
cd noctools
```

2. Instalar dependencias

```bash
pip install requests python-dotenv selenium webdriver-manager pip_system_certs
```

3. (Opcional) Descargar ChromeDriver compatible con tu versión de Chrome desde https://googlechromelabs.github.io/chrome-for-testing/ y colocar el `chromedriver.exe` en la carpeta del proyecto. Si no se encuentra o la versión no coincide con la de Chrome instalada, el script descarga automáticamente la versión compatible via `webdriver-manager` y la instala en el directorio del proyecto, sobrescribiendo la versión anterior.

4. Copiar `.env.example` a `.env` y completar los valores

---

## Configuración

### `.env` — Credenciales y configuración

Todas las variables se dividen en dos grupos: **obligatorias** (sin defaults en el código) y **opcionales** (con defaults incluidos).

#### Cookies de sesión Noctools

```
COOKIE_SESSIONID=...
COOKIE_CSRFTOKEN=...
COOKIE_CF_AUTHORIZATION=...
COOKIE_CF_APP_SESSION=...
COOKIE_JWT_SESSION=...
COOKIE_CF_BM=...
```

#### Slack Bot Tokens

Los tokens se nombran dinámicamente: `SLACK_BOT_TOKEN_{NOMBRE}` donde `{NOMBRE}` es el valor de la columna `organizacion` o `workspace` del CSV (en mayúsculas). El nombre debe ser alfanumérico, sin espacios ni caracteres especiales.

```
# Token de organización (compartido por todos los workspaces dentro de la org)
SLACK_BOT_TOKEN_MIORG=xoxb-...

# Token de workspace standalone (workspace fuera de una organización)
SLACK_BOT_TOKEN_MIWS=xoxb-...
```

> Si la app de Slack está instalada a nivel de organización, un solo token funciona para todos los workspaces dentro de esa org. Solo se define `SLACK_BOT_TOKEN_{ORG}` y en el CSV se completa la columna `organizacion`. Si un workspace está fuera de la organización, se define `SLACK_BOT_TOKEN_{WORKSPACE}` y en el CSV la columna `organizacion` queda vacía.

#### Telegram Bot Token

```
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
```

> El bot debe ser miembro de los grupos a los que va a enviar mensajes. Los grupos privados tienen IDs negativos (ej. `-1001234567890`).

#### URLs internas (OBLIGATORIAS)

Estas URLs no tienen defaults en el código y deben estar si o si en `.env`. Si falta alguna, el script se detiene al iniciar indicando cuáles faltan.

```
URL_ALERTS_NO_ACK=https://noctools.internal/alerts/getAlerts/newrelic/0
URL_ALERTS_ACK=https://noctools.internal/alerts/getAlerts/newrelic/1
URL_NAGIOS_DASHBOARD=https://noctools.internal/nagios/dashboard
URL_NOC_DUTY=https://noctools.internal/nocduty/incidentes
URL_NOC_DUTY_INCIDENTES=https://noctools.internal/nocduty/incjson
URL_JIRA_BROWSE=https://jira.internal/browse
```

#### Parámetros opcionales (con defaults incluidos en el código)

Si no se definen, el script usa los valores por defecto mostrados a continuación:

| Variable | Default | Descripción |
|---|---|---|
| `SLACK_API` | `https://slack.com/api/chat.postMessage` | Endpoint de la API de Slack |
| `SLACK_SUBDOMAIN_{WORKSPACE}` | — | Subdominio de Slack para permalinks en Telegram (uno por workspace) |
| `TELEGRAM_API` | `https://api.telegram.org` | Endpoint de la API de Telegram |
| `USER_AGENT` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/150.0.0.0 Safari/537.36` | User-Agent para requests HTTP |
| `ACCEPT_LANGUAGE` | `es-419,es;q=0.9,en;q=0.8` | Header accept-language |
| `TICKETS_FILTER` | `RA_FA_A_TA_O_I` | Filtro del path del endpoint de tickets Jira |
| `TICKETS_LOOKBACK_DAYS` | `2` | Días hacia atrás para consultar tickets (fallback de NocDuty) |
| `SELENIUM_TIMEOUT` | `180` | Timeout de Selenium en segundos (3 min) |
| `SELENIUM_POST_LOGIN_SLEEP` | `3` | Segundos de espera después del login |
| `REQUESTS_TIMEOUT` | `15` | Timeout para requests a Noctools (segundos) |
| `SLACK_TIMEOUT` | `10` | Timeout para requests a Slack API (segundos) |
| `TELEGRAM_TIMEOUT` | `10` | Timeout para requests a Telegram API (segundos) |
| `DEFAULT_WORKSPACE` | `MYDEFAULT` | Fallback de workspace si el CSV no trae el campo |
| `DEFAULT_ORGANIZATION` | — | Fallback de organización si el CSV no trae el campo |
| `TELEGRAM_START_HOUR` | `18` | Hora de inicio del horario de envío de Telegram |
| `TELEGRAM_END_HOUR` | `0` | Hora de fin del horario de envío de Telegram |
| `TELEGRAM_TIMEZONE` | `UTC` | Zona horaria para el chequeo de horario de Telegram y saludo dinámico |

> El horario de Telegram soporta cruce de medianoche (ej: `18` a `0` = de 18:00 a 00:00).

> Los subdominios de Slack se nombran dinámicamente: `SLACK_SUBDOMAIN_{WORKSPACE}` donde `{WORKSPACE}` es el valor de la columna `workspace` del CSV (en mayúsculas). El subdominio es la parte que va antes de `.slack.com` en la URL del workspace. Ejemplo: `SLACK_SUBDOMAIN_MIWS=mi-subdominio` → `https://mi-subdominio.slack.com/...`. Si no están configurados, el mensaje de Telegram se envía igual pero sin el link de Slack, y el script avisa por consola.

### `canales.csv` — Mapeo de servicios a canales de Slack y grupos de Telegram

```
servicio,canal_nombre,canal_id,workspace,organizacion,telegram_group_id
example-service,team-channel-1,CXXXXXXXXX,MYDEFAULT,MIORG,@noc_alerts
fraud-example,ext-noc-fraud-support,CXXXXXXXXX,MYEXTERNALS,,
new-service,new-team-channel,CXXXXXXXXX,NEWWS,OTHERORG,
```

> Los campos `workspace` y `organizacion` determinan qué bot token se usa para enviar el mensaje a Slack. La organización pondera sobre el workspace: si `organizacion` tiene valor, se busca `SLACK_BOT_TOKEN_{ORGANIZACION}`. Si está vacía, se busca `SLACK_BOT_TOKEN_{WORKSPACE}`.

> Si ambos campos están vacíos, el script usa los defaults (`DEFAULT_ORGANIZATION` y/o `DEFAULT_WORKSPACE`) e informa que falta completar el CSV.

> El campo `telegram_group_id` es opcional. Si está vacío, el script no envía a Telegram para ese servicio. Los grupos privados de Telegram tienen IDs negativos (ej. `-1001234567890`).

> El archivo se lee con `encoding="utf-8-sig"` para manejar archivos con o sin BOM (común en Windows).

---

## Parámetros

### Modo alertas

| Parámetro | Descripción | Compatible con |
|---|---|---|
| `showack` | Muestra alarmas con acknowledged | `send` |
| `send` | Envía mensajes por Slack (siempre) y Telegram (si está en horario) | `showack`, `log` |
| `log` | Registra escalados en alerts.log | `send` |

> ⚠️ El parámetro `log` no puede usarse junto con `showack`.

> En modo `send`, Slack envía siempre sin restricción horaria. Telegram envía solo si el envío a Slack fue exitoso (mensaje principal + hilo), el servicio tiene `telegram_group_id` configurado en el CSV y la hora actual está dentro del rango `TELEGRAM_START_HOUR`-`TELEGRAM_END_HOUR`.

### Modo test

| Parámetro | Descripción |
|---|---|
| `test` | Envía un mensaje de prueba a un canal de Slack o grupo de Telegram |

**Sintaxis:**

```bash
# Slack (default, sin flag)
python noctools_alerts.py test "mensaje" "channel_id" "workspace_o_organizacion"

# Slack (con flag explícito)
python noctools_alerts.py test --slack "mensaje" "channel_id" "workspace_o_organizacion"

# Telegram
python noctools_alerts.py test --telegram "mensaje" "chat_id"
```

**Ejemplos:**

```bash
python noctools_alerts.py test "mensaje de prueba" "CXXXXXXXXX" "MIORG"
python noctools_alerts.py test --slack "mensaje de prueba" "CXXXXXXXXX" "MIORG"
python noctools_alerts.py test --telegram "mensaje de prueba" "-1001234567890"
```

El modo `test` envía un mensaje simple (sin hilo) a Slack o Telegram. Acepta cualquier `channel_id` o `chat_id` sin importar si está en `canales.csv`. El mensaje soporta formato mrkdwn de Slack (`*negrita*`, `@mentions`) o Markdown de Telegram (`*negrita*`, `@mentions`).

**Validación contra el CSV:**

- **Slack:** busca `channel_id` + `workspace` juntos en el CSV
  - Si encuentra: `Enviando TEST Message al canal 'nombre_del_canal' en workspace 'MYDEFAULT'`
  - Si no encuentra: `El canal a testear en el workspace 'MYDEFAULT' con ID 'CXXXXXXXXX' no se encuentra en la base`
- **Telegram:** busca `chat_id` en el CSV
  - Si encuentra: `Enviando TEST Message al grupo 'nombre_del_grupo' en Telegram`
  - Si no encuentra: `El grupo a testear con ID '-1001234567890' no se encuentra en la base`

En ambos casos el mensaje se envía.

**Resultado del envío:**

- Si funciona: `✅ Mensaje de TEST enviado correctamente`
- Si falla: `❌ Error enviando mensaje: {error}` (Slack) o `❌ Error enviando mensaje a Telegram: {error}` (Telegram)

> El modo `test` no consulta las URLs internas de Noctools, por lo que no requiere las URLs obligatorias del `.env`.

---

## Validación de envío (`send`)

Antes de enviar un mensaje a Slack, el script valida que estén presentes:
- Nombre de servicio
- Canal completo (nombre, id, workspace u organización)
- Ticket Jira
- Critical Alert Events (descripción del incidente)
- Links: App Overview, Errors, Issues
- Slack Bot Token

Si algo falta, no envía a Slack ni a Telegram y detalla qué campos faltan.

El envío a Slack se considera exitoso solo cuando tanto el mensaje principal como el hilo se envían correctamente. Si cualquiera de los dos falla, Telegram no se envía.

---

## Obtención del ticket de Jira

El ticket de Jira se obtiene en dos pasos:

1. **Fuente principal:** el JSON de alertas incluye el campo `"ticket"` directamente en cada servicio. El script lo lee de ahí.
2. **Fallback (NocDuty):** el script consulta el endpoint de NocDuty (`URL_NOC_DUTY_INCIDENTES`) **solo si ningún servicio crítico tiene el campo `"ticket"`**, lo que indica que el JSON está fallando. La búsqueda en NocDuty es case-insensitive por nombre de servicio.

### Lógica de fallback

El fallback a NocDuty no se hace por servicio individual, sino que se evalúa globalmente:

| Escenario | Comportamiento |
|---|---|
| Todos los servicios tienen ticket en el JSON | El JSON funciona. No se consulta NocDuty. Muestra: `🎫 Tickets obtenidos del JSON de alertas.` |
| Algunos servicios tienen ticket, otros no | El JSON funciona. Los que no tienen ticket aún no fueron creados en Jira. No se consulta NocDuty. El ticket se muestra como `Ticket de Jira no creado` |
| Ningún servicio tiene ticket en el JSON | El JSON está fallando. Se consulta NocDuty. Muestra: `🎫 Consultando tickets Jira (fallback)...` |

**Resultado del fallback (cuando se consulta NocDuty):**

| Resultado | Comportamiento |
|---|---|
| NocDuty responde y encuentra tickets | Se usan los tickets. Muestra: `ℹ️ Ticket no encontrado en alertas. Obtenido via NocDuty: {ticket}` |
| NocDuty no responde | Muestra: `⚠️ NocDuty no disponible. Falló la consulta del ticket de Jira.` El ticket se muestra como `Falló la consulta del ticket de Jira` |

---

---

### Códigos de filtro de NocDuty

El parámetro `TICKETS_FILTER` controla qué estados de ticket se incluyen en la consulta del fallback. Cada código representa un estado del ciclo de vida del ticket:

| Código | Estado | Descripción |
|---|---|---|
| `R` | Creating | Se está creando el ticket |
| `I` | Create with fails | Algo falló durante la creación del ticket |
| `O` | Opened | Ticket abierto |
| `A` | Acknowledged | Ticket con ACK |
| `RA` | Running ACK | Se está procesando el ACK |
| `FA` | ACK with fails | Algo falló durante el ACK del ticket |
| `TA` | ACK Triggered | Se inició el proceso de ACK |
| `C` | Closed | Ticket cerrado |
| `RC` | Closing | Ticket en proceso de cerrado |
| `FC` | Closed with fails | Ticket cerrado pero ocurrieron errores en el proceso de cerrado |

> El filtro por defecto `RA_FA_A_TA_O_I` incluye todos los tickets que no estén cerrados ni en proceso de creación pura. Los códigos se concatenan con `_` como separador.

> `TICKETS_LOOKBACK_DAYS` controla cuántos días hacia atrás se consultan los tickets. Por defecto `2`, ya que es muy improbable que un ticket esté más de 24 horas abierto.

---

## Deduplicación de Critical Alert Events

`extract_incident_description` deduplica descripciones repetidas en `long_plugin_output`. Si una misma descripción aparece múltiples veces, se muestra una sola vez con un contador `(xN)`. Esto evita que mensajes con alertas duplicadas superen el límite de tamaño de Slack.

---

## Envío a Telegram (`send`)

En modo `send`, después de enviar a Slack, el script intenta enviar a Telegram para cada servicio **solo si el envío a Slack fue exitoso** (mensaje principal + hilo):

| Condición | Comportamiento |
|---|---|
| Envío a Slack falló | `⚠️ Telegram no enviado: el envío a Slack falló.` |
| `telegram_group_id` vacío en CSV | `⚠️ Telegram: group_id no configurado en la base para este servicio. Mensaje no enviado.` |
| Fuera de horario | `⚠️ Telegram fuera de horario (18:00-0:00 America/Argentina/Buenos_Aires). Mensaje no enviado.` |
| `TELEGRAM_BOT_TOKEN` no configurado | `❌ Token de Telegram no disponible. Verificá TELEGRAM_BOT_TOKEN en .env` |
| Envío exitoso | `✅ Enviado correctamente a Telegram {chat_id}` |

> El horario de Telegram soporta cruce de medianoche. Ejemplos válidos: `18` a `0` (18:00-00:00), `22` a `2` (22:00-02:00).

### Permalink de Slack en Telegram

Cuando el envío a Slack es exitoso, el script construye un permalink al mensaje principal de Slack y lo incluye como último link en el mensaje de Telegram (`💬 [Ver en Slack](url)`). El permalink se arma con el subdominio del workspace (`SLACK_SUBDOMAIN_{WORKSPACE}`), el `channel_id` y el `ts` del mensaje:

```
https://{subdominio}.slack.com/archives/{channel_id}/p{ts_sin_punto}
```

Si el subdominio del workspace no está configurado en `.env`, el mensaje de Telegram se envía igual pero sin el link de Slack, y el script avisa por consola: `⚠️ No se pudo generar el link de Slack: subdominio no configurado para workspace '...'`

### Saludo dinámico

El saludo del mensaje (en Slack, Telegram y consola) varía según la hora actual (usando `TELEGRAM_TIMEZONE`):

| Horario | Saludo |
|---|---|
| 18:00 - 04:59 | `Estimados, buenas noches, los molesto...` |
| 05:00 - 11:59 | `Estimados, buenos dias, los molesto...` |
| 12:00 - 17:59 | `Estimados, buenas tardes, los molesto...` |

> El saludo se calcula una vez por ejecución usando `get_greeting()` y respeta `TELEGRAM_TIMEZONE`. El rango de "buenas noches" cruza medianoche (18→05). El saludo es independiente del horario de envío de Telegram.

---

## Log condicional (`log`)

- Si `send=True` y falló el envío a Slack (mensaje principal o hilo) → no loguea, muestra error
- Si el servicio no está en CSV → no loguea, muestra error
- Si falta Ticket Jira → no loguea, muestra error
- Si `send=False` y `log=True` → loguea normalmente si hay canal y ticket

> El log registra escalamientos a Slack. Telegram no se loguea.

---

## Renovación de cookies

El script verifica si las cookies están vencidas chequeando **dos endpoints**: alertas (`URL_ALERTS_NO_ACK`) y tickets de NocDuty (`build_tickets_url()`). Si cualquiera devuelve login HTML o redirección, dispara Selenium para renovar.

Al renovar, Selenium abre Chrome automáticamente para que el usuario inicie sesión en Noctools. Las cookies se actualizan solas en el `.env`, incluyendo `CF_AppSession`.

El script busca `chromedriver.exe` local primero. Si no lo encuentra, o si la versión local es incompatible con la versión instalada de Chrome, descarga automáticamente la versión compatible via `webdriver-manager` y la instala en el directorio del proyecto sobrescribiendo la versión anterior. El usuario no necesita actualizar el `chromedriver.exe` manualmente cuando Chrome se actualiza.

---

## Uso

### `python noctools_alerts.py`

```
📝 Modo log inactivo
🔍 Consultando Noctools...
🎫 Tickets obtenidos del JSON de alertas.

============================================================
  ALARMAS CRITICAL — 21/07/2026 10:30
  Modo: SIN ACKNOWLEDGED
  Total: 1
============================================================

┌─ Servicio: example-service
│  Host:        Example Host [PROD]
│  Criticidad:  HIGH
│  Acknowledged: ❌ No
│  Do not call:  📞 No
│  Equipo:      example-team@company.com
│  Ticket Jira: NOC-000001
│  En Database: ✅ Sí
│  Workspace:    MYDEFAULT
│  Organización: MIORG
│  Telegram:     @noc_alerts
└──────────────────────────────────────────────────────────

📋 MENSAJE PRINCIPAL (pegar en el canal):
*🔴 Alerta example-service*

💬 HILO (pegar como reply al mensaje anterior):
Estimados, buenas tardes, los molesto porque vemos alertada la app *example-service* con el siguiente error:

*Critical Alert Events:*
• example-service query result is > 5.0 for 10 minutes on 'API Errors'

*Links:*
• 🎫 Ticket Jira (NOC-000001): https://jira.internal/browse/NOC-000001
• 📊 App Overview: https://one.newrelic.com/...
• ❌ Errors: https://one.newrelic.com/...
• 🚨 Issues: https://one.newrelic.com/...

📝 Modo log inactivo
------------------------------------------------------------
```

### `python noctools_alerts.py send log`

```
📝 Modo log activo
🔍 Consultando Noctools...
🎫 Tickets obtenidos del JSON de alertas.
...
📤 Enviando a Slack #team-channel-1 [MYDEFAULT/MIORG]...
✅ Enviado correctamente a Slack #team-channel-1 [MYDEFAULT/MIORG]
📤 Enviando a Telegram @noc_alerts...
✅ Enviado correctamente a Telegram @noc_alerts

📝 Logueado: NOC-000001 | Nagios NR | Example Host [PROD] | example-service --> Se escala via slack con team-channel-1.
------------------------------------------------------------
```

Si Slack falla (Telegram no se envía):

```
📤 Enviando a Slack #team-channel-1 [MYDEFAULT/MIORG]...
❌ Error al enviar mensaje a Slack #team-channel-1 [MYDEFAULT/MIORG], "fallo el envío del mensaje principal"
⚠️  Telegram no enviado: el envío a Slack falló.
```

Si Telegram no tiene group_id configurado:

```
📤 Enviando a Slack #team-channel-1 [MYDEFAULT/MIORG]...
✅ Enviado correctamente a Slack #team-channel-1 [MYDEFAULT/MIORG]
📤 Enviando a Telegram ...
⚠️  Telegram: group_id no configurado en la base para este servicio. Mensaje no enviado.
```

Si Telegram está fuera de horario:

```
📤 Enviando a Slack #team-channel-1 [MYDEFAULT/MIORG]...
✅ Enviado correctamente a Slack #team-channel-1 [MYDEFAULT/MIORG]
📤 Enviando a Telegram @noc_alerts...
⚠️  Telegram fuera de horario (18:00-0:00 America/Argentina/Buenos_Aires). Mensaje no enviado.
```

Si el subdominio de Slack no está configurado (el mensaje de Telegram se envía sin el link):

```
✅ Enviado correctamente a Slack #team-channel-1 [MYDEFAULT/MIORG]
⚠️  No se pudo generar el link de Slack: subdominio no configurado para workspace 'mydefault'.
📤 Enviando a Telegram @noc_alerts...
✅ Enviado correctamente a Telegram @noc_alerts
```

### `python noctools_alerts.py showack log`

```
⚠️  El parámetro 'log' no puede usarse junto con 'showack'. No se loguearán entradas.
📝 Modo log inactivo
🔍 Consultando Noctools...
...
```

### `python noctools_alerts.py test --slack "mensaje de prueba" "CXXXXXXXXX" "MYDEFAULT"`

```
Enviando TEST Message al canal 'team-channel-1' en workspace 'MYDEFAULT'
✅ Mensaje de TEST enviado correctamente
```

### `python noctools_alerts.py test --telegram "mensaje de prueba" "-1001234567890"`

```
Enviando TEST Message al grupo 'noc_alerts' en Telegram
✅ Mensaje de TEST enviado correctamente
```

### `alerts.log` — ejemplo de entradas generadas por el parámetro `log`

```
NOC-000001 | Nagios NR | Example Host [PROD] | example-service --> Se escala via slack con team-channel-1.
NOC-000002 | Nagios NR | Example Host 2 [PROD] | example-service-2 --> Se escala via slack con team-channel-2.
NOC-000003 | Nagios NR | Example Host 3 [PROD] | example-service-3 --> Se escala via slack con team-channel-3.
```

### Ejemplo de mensaje en Slack

**Mensaje principal (canal):**
> 🔴 Alerta example-service

**Hilo:**
> Estimados, buenas noches, los molesto porque vemos alertada la app **example-service** con el siguiente error.
>
> **Critical Alert Events:**
> - example-service query result is > 5.0 for 10 minutes on 'API Errors'
>
> **Links:**
> - 🎫 Ticket Jira (NOC-000001)
> - 📊 App Overview
> - ❌ Errors
> - 🚨 Issues

### Ejemplo de mensaje en Telegram

> **🔴 Alerta example-service**
>
> Estimados, buenas noches, los molesto porque vemos alertada la app **example-service** con el siguiente error.
>
> **Critical Alert Events:**
> - example-service query result is > 5.0 for 10 minutes on 'API Errors'
>
> **Links:**
> - 🎫 [Ticket Jira (NOC-000001)](https://jira.internal/browse/NOC-000001)
> - 📊 [App Overview](https://one.newrelic.com/...)
> - ❌ [Errors](https://one.newrelic.com/...)
> - 🚨 [Issues](https://one.newrelic.com/...)
> - 💬 [Ver en Slack](https://mi-workspace.slack.com/archives/CXXXXXXXXX/p1785514019664019)
