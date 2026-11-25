🌐 [Español](README_ES.md)

# NOC Alerts Tool

## Description

Automation tool for the NOC team. Queries critical New Relic alerts via Noctools, cross-references with Jira tickets, and generates formatted messages for escalation via Slack and Telegram. Includes escalation logging with service and channel details.

---

## Requirements

- Python 3.8+
- Google Chrome installed
- Access to Noctools
- Slack Bot Token configured (per organization or per workspace)
- Telegram Bot Token configured
- `pip install pip_system_certs` (required in environments with a corporate proxy that intercepts HTTPS)

> ⚠️ In corporate environments with a proxy that intercepts HTTPS traffic (e.g., corporate proxy, firewall), Slack API calls may fail with `SSL: CERTIFICATE_VERIFY_FAILED`. Install `pip_system_certs` so Python uses the Windows certificate store instead of its own.

---

## Project Files

| File | Description |
|---|---|
| `noctools_alerts.py` | Main script |
| `.env` | Credentials and configuration (do not upload to GitHub) |
| `canales.csv` | Service-to-Slack-channel and Telegram-group mapping (do not upload to GitHub) |
| `alerts.log` | Escalation log (do not upload to GitHub) |
| `chromedriver.exe` | Selenium driver (do not upload to GitHub) |

> ⚠️ `.env`, `canales.csv`, `alerts.log`, and `chromedriver.exe` are excluded from the repository via `.gitignore`.

---

## Installation

1. Clone the repository

```bash
git clone https://github.com/asampedro/noctools.git
cd noctools
```

2. Install dependencies

```bash
pip install requests python-dotenv selenium webdriver-manager pip_system_certs
```

3. (Optional) Download a ChromeDriver compatible with your Chrome version from https://googlechromelabs.github.io/chrome-for-testing/ and place `chromedriver.exe` in the project folder. If not found or the version does not match the installed Chrome, the script automatically downloads the compatible version via `webdriver-manager` and installs it in the project directory, overwriting the previous one.

4. Copy `.env.example` to `.env` and fill in the values

---

## Configuration

### `.env` — Credentials and configuration

All variables are divided into two groups: **required** (no defaults in the code) and **optional** (with built-in defaults).

#### Noctools session cookies

```
COOKIE_SESSIONID=...
COOKIE_CSRFTOKEN=...
COOKIE_CF_AUTHORIZATION=...
COOKIE_CF_APP_SESSION=...
COOKIE_JWT_SESSION=...
COOKIE_CF_BM=...
```

#### Slack Bot Tokens

Tokens are named dynamically: `SLACK_BOT_TOKEN_{NAME}` where `{NAME}` is the value of the `organizacion` or `workspace` column from the CSV (in uppercase). The name must be alphanumeric, with no spaces or special characters.

```
# Organization token (shared by all workspaces within the org)
SLACK_BOT_TOKEN_MYORG=xoxb-...

# Standalone workspace token (workspace outside an organization)
SLACK_BOT_TOKEN_MYWS=xoxb-...
```

> If the Slack app is installed at the organization level, a single token works for all workspaces within that org. Just define `SLACK_BOT_TOKEN_{ORG}` and fill the `organizacion` column in the CSV. If a workspace is outside the organization, define `SLACK_BOT_TOKEN_{WORKSPACE}` and leave the `organizacion` column empty in the CSV.

#### Telegram Bot Token

```
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
```

> The bot must be a member of the groups it sends messages to. Private groups have negative IDs (e.g., `-1001234567890`).

#### Internal URLs (REQUIRED)

These URLs have no defaults in the code and must be present in `.env`. If any are missing, the script stops on startup indicating which ones are missing.

```
URL_ALERTS_NO_ACK=https://noctools.internal/alerts/getAlerts/newrelic/0
URL_ALERTS_ACK=https://noctools.internal/alerts/getAlerts/newrelic/1
URL_NAGIOS_DASHBOARD=https://noctools.internal/nagios/dashboard
URL_NOC_DUTY=https://noctools.internal/nocduty/incidentes
URL_NOC_DUTY_INCIDENTES=https://noctools.internal/nocduty/incjson
URL_JIRA_BROWSE=https://jira.internal/browse
```

#### Optional parameters (with built-in defaults)

If not defined, the script uses the following default values:

| Variable | Default | Description |
|---|---|---|
| `SLACK_API` | `https://slack.com/api/chat.postMessage` | Slack API endpoint |
| `SLACK_SUBDOMAIN_{WORKSPACE}` | — | Slack subdomain for Telegram permalinks (one per workspace) |
| `TELEGRAM_API` | `https://api.telegram.org` | Telegram API endpoint |
| `USER_AGENT` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... Chrome/150.0.0.0 Safari/537.36` | User-Agent for HTTP requests |
| `ACCEPT_LANGUAGE` | `es-419,es;q=0.9,en;q=0.8` | Accept-Language header |
| `TICKETS_FILTER` | `RA_FA_A_TA_O_I` | Path filter for the Jira tickets endpoint |
| `TICKETS_LOOKBACK_DAYS` | `2` | Days to look back for tickets (NocDuty fallback) |
| `SELENIUM_TIMEOUT` | `180` | Selenium timeout in seconds (3 min) |
| `SELENIUM_POST_LOGIN_SLEEP` | `3` | Seconds to wait after login |
| `REQUESTS_TIMEOUT` | `15` | Timeout for Noctools requests (seconds) |
| `SLACK_TIMEOUT` | `10` | Timeout for Slack API requests (seconds) |
| `TELEGRAM_TIMEOUT` | `10` | Timeout for Telegram API requests (seconds) |
| `DEFAULT_WORKSPACE` | `MYDEFAULT` | Workspace fallback if the CSV does not provide one |
| `DEFAULT_ORGANIZATION` | — | Organization fallback if the CSV does not provide one |
| `TELEGRAM_START_HOUR` | `18` | Start hour for Telegram sending window |
| `TELEGRAM_END_HOUR` | `0` | End hour for Telegram sending window |
| `TELEGRAM_TIMEZONE` | `UTC` | Timezone for Telegram schedule check and dynamic greeting |

> The Telegram schedule supports midnight crossing (e.g., `18` to `0` = 18:00 to 00:00).

> Slack subdomains are named dynamically: `SLACK_SUBDOMAIN_{WORKSPACE}` where `{WORKSPACE}` is the value of the `workspace` column from the CSV (in uppercase). The subdomain is the part before `.slack.com` in the workspace URL. Example: `SLACK_SUBDOMAIN_MYWS=my-subdomain` → `https://my-subdomain.slack.com/...`. If not configured, the Telegram message is still sent but without the Slack link, and the script prints a warning to the console.

### `canales.csv` — Service-to-channel mapping

```
servicio,canal_nombre,canal_id,workspace,organizacion,telegram_group_id
example-service,team-channel-1,CXXXXXXXXX,MYDEFAULT,MYORG,@noc_alerts
fraud-example,ext-noc-fraud-support,CXXXXXXXXX,MYEXTERNALS,,
new-service,new-team-channel,CXXXXXXXXX,NEWWS,OTHERORG,
```

> The `workspace` and `organizacion` fields determine which bot token is used to send the Slack message. Organization takes precedence over workspace: if `organizacion` has a value, `SLACK_BOT_TOKEN_{ORGANIZACION}` is used. If empty, `SLACK_BOT_TOKEN_{WORKSPACE}` is used.

> If both fields are empty, the script uses the defaults (`DEFAULT_ORGANIZATION` and/or `DEFAULT_WORKSPACE`) and reports that the CSV is incomplete.

> The `telegram_group_id` field is optional. If empty, the script does not send to Telegram for that service. Private Telegram groups have negative IDs (e.g., `-1001234567890`).

> The file is read with `encoding="utf-8-sig"` to handle files with or without BOM (common on Windows).

---

## Parameters

### Alerts mode

| Parameter | Description | Compatible with |
|---|---|---|
| `showack` | Shows acknowledged alarms | `send` |
| `send` | Sends messages via Slack (always) and Telegram (if in schedule) | `showack`, `log`, `jira` |
| `jira` | Adds an escalation comment to the Jira ticket after Slack delivery | `send` |
| `log` | Logs escalations to alerts.log | `send` |

> ⚠️ The `log` parameter cannot be used together with `showack`.

> In `send` mode, Slack always sends without time restrictions. Telegram sends only if Slack delivery was successful (main message + thread), the service has `telegram_group_id` configured in the CSV, and the current time is within the `TELEGRAM_START_HOUR`-`TELEGRAM_END_HOUR` range.

> The `jira` parameter adds an automatic comment to the Jira ticket after successful Slack delivery. The comment text is `⚙ Se escala via Slack [& Telegram] a #channel — date time`.

> ⚠️ Note: the comment uses `⚙` instead of an emoji because some Jira Server databases (MySQL utf8 without mb4) cannot store 4-byte Unicode characters (emojis). Characters like ⚙ (3 bytes) work correctly. Emojis in `--comment` may fail with a 500 error depending on the Jira database configuration. It requires `JIRA_USER`, `JIRA_PASSWORD` and `URL_JIRA_API` configured in `.env`. If the Jira comment fails, it shows a warning but does not block Slack, Telegram or the log.

### Test mode

| Parameter | Description |
|---|---|
| `test` | Sends a test message to a Slack channel or Telegram group |

**Syntax:**

```bash
# Slack (default, no flag)
python noctools_alerts.py test "message" "channel_id" "workspace_or_organization"

# Slack (explicit flag)
python noctools_alerts.py test --slack "message" "channel_id" "workspace_or_organization"

# Telegram
python noctools_alerts.py test --telegram "message" "chat_id"
```

**Examples:**

```bash
python noctools_alerts.py test "test message" "CXXXXXXXXX" "MYORG"
python noctools_alerts.py test --slack "test message" "CXXXXXXXXX" "MYORG"
python noctools_alerts.py test --telegram "test message" "-1001234567890"
```

Test mode sends a simple message (no thread) to Slack or Telegram. It accepts any `channel_id` or `chat_id` regardless of whether it is in `canales.csv`. The message supports Slack mrkdwn format (`*bold*`, `@mentions`) or Telegram Markdown (`*bold*`, `@mentions`).

**CSV validation:**

- **Slack:** looks up `channel_id` + `workspace` together in the CSV
  - Found: `Enviando TEST Message al canal 'channel_name' en workspace 'MYDEFAULT'`
  - Not found: `El canal a testear en el workspace 'MYDEFAULT' con ID 'CXXXXXXXXX' no se encuentra en la base`
- **Telegram:** looks up `chat_id` in the CSV
  - Found: `Enviando TEST Message al grupo 'group_name' en Telegram`
  - Not found: `El grupo a testear con ID '-1001234567890' no se encuentra en la base`

In both cases the message is sent.

**Send result:**

- Success: `✅ Mensaje de TEST enviado correctamente`
- Failure: `❌ Error enviando mensaje: {error}` (Slack) or `❌ Error enviando mensaje a Telegram: {error}` (Telegram)

> Test mode does not query the internal Noctools URLs, so it does not require the mandatory URLs from `.env`.

---

## Jira ticket updates (`updjira`)

Standalone mode for Jira operations: read ticket info, list transitions, add comments, and apply transitions.

**Syntax:**

```bash
# Show ticket info (default)
python noctools_alerts.py updjira "NOC-12345"

# List available transitions (with ID and name)
python noctools_alerts.py updjira "NOC-12345" --transitionlist

# Add a comment
python noctools_alerts.py updjira "NOC-12345" --comment "comment text"

# Apply a transition (by name, case-insensitive)
python noctools_alerts.py updjira "NOC-12345" --transition "In Progress"

# Add comment + apply transition (comment goes first)
python noctools_alerts.py updjira "NOC-12345" --comment "context" --transition "In Progress"
```

**Requirements:**

- `JIRA_USER`, `JIRA_PASSWORD` and `URL_JIRA_API` must be configured in `.env`
- The ticket must have a valid format (e.g., `NOC-12345`)
- Transitions are applied by name (case-insensitive). If the name doesn't match any available transition, the script shows the available ones
- The `--transitionlist` output shows both ID and name for each transition

**Ticket info output (default):**

```
🎫 Ticket: NOC-317525
   Estado:      In Progress
   Resumen:     PSP API - High error rate
   Tipo:        Alerta Monitoreo
   Prioridad:   Normal
   Proyecto:    NOC
   Asignado a:  NOC Service
   Reporter:    Usuario servicio NOC
   Creado:      2026-11-20T16:07:46.000-0500
   💬 Últimos comentarios (2 total):
   ┌─ [2026-11-20 - Usuario servicio NOC]
   │  Se escaló a Slack desde NocDuty
   └──────────────────────────────────────────────
```

---

## Send validation (`send`)

Before sending a message to Slack, the script validates that the following are present:
- Service name
- Complete channel (name, id, workspace or organization)
- Jira ticket
- Links: App Overview, Errors, Issues
- Slack Bot Token

If anything is missing, it does not send to Slack or Telegram and details which fields are missing.

> ⚠️ If Critical Alert Events are empty, the message is still sent with the placeholder `⚠️ Sin eventos registrados. Validar en New Relic.` and a warning is shown in the console.

Slack delivery is considered successful only when both the main message and the thread are sent successfully. If either fails, Telegram is not sent.

---

## Jira ticket retrieval

The Jira ticket is obtained in two steps:

1. **Primary source:** the alert JSON includes the `"ticket"` field directly in each service. The script reads it from there.
2. **Fallback (NocDuty):** the script queries the NocDuty endpoint (`URL_NOC_DUTY_INCIDENTES`) **only if no critical service has the `"ticket"` field**, which indicates the JSON is failing. The NocDuty search is case-insensitive by service name.

### Fallback logic

The NocDuty fallback is not done per individual service, but evaluated globally:

| Scenario | Behavior |
|---|---|
| All services have ticket in JSON | JSON is working. NocDuty is not queried. Shows: `🎫 Tickets obtenidos del JSON de alertas.` |
| Some services have ticket, others don't | JSON is working. Those without a ticket simply haven't been created in Jira yet. NocDuty is not queried (it wouldn't have them either). Ticket shows as `Ticket de Jira no creado` |
| No service has ticket in JSON | JSON is failing. NocDuty is queried as fallback. Shows: `🎫 Consultando tickets Jira (fallback)...` |

**Fallback results (when NocDuty is queried):**

| Result | Behavior |
|---|---|
| NocDuty responds and finds tickets | Tickets are used. Shows: `ℹ️ Ticket no encontrado en alertas. Obtenido via NocDuty: {ticket}` |
| NocDuty does not respond | Shows: `⚠️ NocDuty no disponible. Falló la consulta del ticket de Jira.` Ticket shows as `Falló la consulta del ticket de Jira` |

---

### NocDuty filter codes

The `TICKETS_FILTER` parameter controls which ticket states are included in the fallback query. Each code represents a state in the ticket lifecycle:

| Code | State | Description |
|---|---|---|
| `R` | Creating | Ticket is being created |
| `I` | Create with fails | Something failed during ticket creation |
| `O` | Opened | Ticket is open |
| `A` | Acknowledged | Ticket has been acknowledged |
| `RA` | Running ACK | ACK is being processed |
| `FA` | ACK with fails | Something failed during ticket ACK |
| `TA` | ACK Triggered | ACK process has been initiated |
| `C` | Closed | Ticket is closed |
| `RC` | Closing | Ticket is being closed |
| `FC` | Closed with fails | Ticket is closed but errors occurred during closing |

> The default filter `RA_FA_A_TA_O_I` includes all tickets that are not closed and not in pure creation. Codes are concatenated with `_` as separator.

> `TICKETS_LOOKBACK_DAYS` controls how many days back to query tickets. Default `2`, since it is very unlikely for a ticket to remain open for more than 24 hours.

---

## Critical Alert Events deduplication

`extract_incident_description` deduplicates repeated descriptions in `long_plugin_output`. If the same description appears multiple times, it is shown once with a counter `(xN)`. This prevents messages with duplicate alerts from exceeding the Slack size limit.

---

## Telegram delivery (`send`)

In `send` mode, after sending to Slack, the script attempts to send to Telegram for each service **only if the Slack delivery was successful** (main message + thread):

| Condition | Behavior |
|---|---|
| Slack delivery failed | `⚠️ Telegram no enviado: el envío a Slack falló.` |
| `telegram_group_id` empty in CSV | `⚠️ Telegram: group_id no configurado en la base para este servicio. Mensaje no enviado.` |
| Outside schedule | `⚠️ Telegram fuera de horario (18:00-0:00 UTC). Mensaje no enviado.` |
| `TELEGRAM_BOT_TOKEN` not configured | `❌ Token de Telegram no disponible. Verificá TELEGRAM_BOT_TOKEN en .env` |
| Successful delivery | `✅ Enviado correctamente a Telegram {chat_id}` |

> The Telegram schedule supports midnight crossing. Valid examples: `18` to `0` (18:00-00:00), `22` to `2` (22:00-02:00).

### Slack permalink in Telegram

When Slack delivery is successful, the script constructs a permalink to the main Slack message and includes it as the last link in the Telegram message (`💬 [Ver en Slack](url)`). The permalink is built using the workspace subdomain (`SLACK_SUBDOMAIN_{WORKSPACE}`), the `channel_id`, and the message `ts`:

```
https://{subdomain}.slack.com/archives/{channel_id}/p{ts_without_dot}
```

If the workspace subdomain is not configured in `.env`, the Telegram message is still sent but without the Slack link, and the script prints a warning: `⚠️ No se pudo generar el link de Slack: subdominio no configurado para workspace '...'`

### Dynamic greeting

The message greeting (in Slack, Telegram, and console) varies based on the current time (using `TELEGRAM_TIMEZONE`):

| Time range | Greeting |
|---|---|
| 18:00 - 04:59 | `Estimados, buenas noches, los molesto...` |
| 05:00 - 11:59 | `Estimados, buenos dias, los molesto...` |
| 12:00 - 17:59 | `Estimados, buenas tardes, los molesto...` |

> The greeting is calculated once per execution using `get_greeting()` and respects `TELEGRAM_TIMEZONE`. The "buenas noches" range crosses midnight (18→05). The greeting is independent of the Telegram sending schedule.

---

## Conditional logging (`log`)

- If `send=True` and Slack delivery failed (main message or thread) → no log, shows error
- If the service is not in the CSV → no log, shows error
- If Jira ticket is missing → no log, shows error
- If `send=False` and `log=True` → logs normally if channel and ticket are present

> The log records Slack escalations. Telegram is not logged.

---

## Cookie renewal

The script checks if cookies are expired by verifying **two endpoints**: alerts (`URL_ALERTS_NO_ACK`) and NocDuty tickets (`build_tickets_url()`). If either returns login HTML or a redirect, it triggers Selenium to renew.

When renewing, Selenium opens Chrome automatically for the user to log in to Noctools. Cookies are updated automatically in `.env`, including `CF_AppSession`.

The script looks for `chromedriver.exe` locally first. If not found, or if the local version is incompatible with the installed Chrome version, it automatically downloads the compatible version via `webdriver-manager` and installs it in the project directory, overwriting the previous one. The user does not need to update `chromedriver.exe` manually when Chrome updates.

---

## Usage

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
│  Organización: MYORG
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

If Slack fails (Telegram is not sent):

```
📤 Enviando a Slack #team-channel-1 [MYDEFAULT/MIORG]...
❌ Error al enviar mensaje a Slack #team-channel-1 [MYDEFAULT/MIORG], "fallo el envío del mensaje principal"
⚠️  Telegram no enviado: el envío a Slack falló.
```

If Telegram has no group_id configured:

```
📤 Enviando a Slack #team-channel-1 [MYDEFAULT/MIORG]...
✅ Enviado correctamente a Slack #team-channel-1 [MYDEFAULT/MIORG]
📤 Enviando a Telegram ...
⚠️  Telegram: group_id no configurado en la base para este servicio. Mensaje no enviado.
```

If Telegram is outside schedule:

```
📤 Enviando a Slack #team-channel-1 [MYDEFAULT/MIORG]...
✅ Enviado correctamente a Slack #team-channel-1 [MYDEFAULT/MIORG]
📤 Enviando a Telegram @noc_alerts...
⚠️  Telegram fuera de horario (18:00-0:00 UTC). Mensaje no enviado.
```

If the Slack subdomain is not configured (Telegram message is sent without the link):

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

### `python noctools_alerts.py test --slack "test message" "CXXXXXXXXX" "MYDEFAULT"`

```
Enviando TEST Message al canal 'team-channel-1' en workspace 'MYDEFAULT'
✅ Mensaje de TEST enviado correctamente
```

### `python noctools_alerts.py test --telegram "test message" "-1001234567890"`

```
Enviando TEST Message al grupo 'noc_alerts' en Telegram
✅ Mensaje de TEST enviado correctamente
```

### `alerts.log` — example entries generated by the `log` parameter

```
NOC-000001 | Nagios NR | Example Host [PROD] | example-service --> Se escala via slack con team-channel-1.
NOC-000002 | Nagios NR | Example Host 2 [PROD] | example-service-2 --> Se escala via slack con team-channel-2.
NOC-000003 | Nagios NR | Example Host 3 [PROD] | example-service-3 --> Se escala via slack con team-channel-3.
```

### Example Slack message

**Main message (channel):**
> 🔴 Alerta example-service

**Thread:**
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

### Example Telegram message

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
