#!/usr/bin/env python3
"""
Noctools Alert Fetcher & Slack Message Generator
Hace GET al endpoint de Noctools, parsea las alarmas CRITICAL,
cruza con tickets de Jira y genera mensajes formateados para escalar por Slack
y Telegram. Incluye registro de escalamientos con detalle de servicio y canal.

Funcionalidades principales:
  - Consulta de alertas críticas (con o sin acknowledged)
  - Ticket de Jira desde el JSON de alertas (fuente principal) con fallback
    condicional a NocDuty solo si el JSON está fallando
  - Resolución dinámica de bot tokens de Slack por organización o workspace
    (la organización pondera sobre el workspace, con defaults configurables)
  - Subdominios dinámicos de Slack para permalinks en mensajes de Telegram
  - Deduplicación de Critical Alert Events con contador (xN)
  - Saludo dinámico según hora (buenas noches/días/tardes)
  - Envío a Telegram condicional al éxito de Slack, con restricción horaria
  - ChromeDriver auto-actualizable (descarga versión compatible si la local
    es incompatible con Chrome instalado)
  - Renovación automática de cookies vía Selenium (verifica ambos endpoints)
  - Modo test para enviar mensajes de prueba a Slack o Telegram
  - Registro de escalamientos en alerts.log (parámetro log)

Setup:
  1. Copiá el archivo .env.example a .env y completá con tus credenciales
  2. Instalá dependencias:
     pip install requests python-dotenv selenium webdriver-manager pip_system_certs
  3. Corré: python noctools_alerts.py
     Para ver también los acknowledged: python noctools_alerts.py showack
     Para enviar mensajes: python noctools_alerts.py send log
     Para testear Slack: python noctools_alerts.py test --slack "msg" "channel_id" "workspace"
     Para testear Telegram: python noctools_alerts.py test --telegram "msg" "chat_id"
"""

import requests
import os
import sys
import re
import csv
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# --- Configuración ---
ENV_FILE     = os.path.join(os.path.dirname(__file__), ".env")
CANALES_FILE = os.path.join(os.path.dirname(__file__), "canales.csv")
LOG_FILE     = os.path.join(os.path.dirname(__file__), "alerts.log")

# URLs internas (obligatorias en .env — sin defaults en el código)
URL_ALERTS_NO_ACK       = os.getenv("URL_ALERTS_NO_ACK")
URL_ALERTS_ACK          = os.getenv("URL_ALERTS_ACK")
SLACK_API               = os.getenv("SLACK_API", "https://slack.com/api/chat.postMessage")
URL_NAGIOS_DASHBOARD    = os.getenv("URL_NAGIOS_DASHBOARD")
URL_NOC_DUTY            = os.getenv("URL_NOC_DUTY")
URL_JIRA_BROWSE         = os.getenv("URL_JIRA_BROWSE")
URL_NOC_DUTY_INCIDENTES = os.getenv("URL_NOC_DUTY_INCIDENTES")

# URLs de NewRelic para extracción de links (configurables via .env)
NR_APP_LINK_PATTERN    = os.getenv("NR_APP_LINK_PATTERN",    r'href="(https://[^"]+/nr1-core/apm/overview/[^"]+)"')
NR_ERRORS_LINK_PATTERN  = os.getenv("NR_ERRORS_LINK_PATTERN",  r'href="(https://[^"]+/nr1-core/errors-inbox/[^"]+)"')
NR_ISSUES_LINK_PATTERN  = os.getenv("NR_ISSUES_LINK_PATTERN",  r'href="(https://[^"]+/nr1-core/alerts/filtered-feed/[^"]+)"')

# Headers HTTP (configurables via .env)
USER_AGENT      = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
ACCEPT_LANGUAGE = os.getenv("ACCEPT_LANGUAGE", "es-419,es;q=0.9,en;q=0.8")

# Parámetros de tickets Jira (configurables via .env)
TICKETS_FILTER        = os.getenv("TICKETS_FILTER", "RA_FA_A_TA_O_I")
TICKETS_LOOKBACK_DAYS = int(os.getenv("TICKETS_LOOKBACK_DAYS", "2"))

# Parámetros de Selenium (configurables via .env)
SELENIUM_TIMEOUT         = int(os.getenv("SELENIUM_TIMEOUT", "180"))
SELENIUM_POST_LOGIN_SLEEP = int(os.getenv("SELENIUM_POST_LOGIN_SLEEP", "3"))

# Parámetros de timeouts HTTP (configurables via .env)
REQUESTS_TIMEOUT = int(os.getenv("REQUESTS_TIMEOUT", "15"))
SLACK_TIMEOUT    = int(os.getenv("SLACK_TIMEOUT", "10"))

# Fallbacks de workspace y organización (configurables via .env)
DEFAULT_WORKSPACE   = os.getenv("DEFAULT_WORKSPACE", "MYDEFAULT")
DEFAULT_ORGANIZATION = os.getenv("DEFAULT_ORGANIZATION", "")

# Telegram (configurables via .env)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API       = os.getenv("TELEGRAM_API", "https://api.telegram.org")
TELEGRAM_START_HOUR = int(os.getenv("TELEGRAM_START_HOUR", "18"))
TELEGRAM_END_HOUR   = int(os.getenv("TELEGRAM_END_HOUR", "0"))
TELEGRAM_TIMEZONE   = os.getenv("TELEGRAM_TIMEZONE", "UTC")
TELEGRAM_TIMEOUT    = int(os.getenv("TELEGRAM_TIMEOUT", "10"))

HEADERS_ALERTS = {
    "accept": "*/*",
    "accept-language": ACCEPT_LANGUAGE,
    "referer": URL_NAGIOS_DASHBOARD,
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": USER_AGENT,
}

HEADERS_TICKETS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": ACCEPT_LANGUAGE,
    "referer": URL_NOC_DUTY,
    "x-requested-with": "XMLHttpRequest",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": USER_AGENT,
}

# URLs que deben estar si o si en .env (sin defaults en el codigo)
REQUIRED_URLS = {
    "URL_ALERTS_NO_ACK":       URL_ALERTS_NO_ACK,
    "URL_ALERTS_ACK":          URL_ALERTS_ACK,
    "URL_NAGIOS_DASHBOARD":    URL_NAGIOS_DASHBOARD,
    "URL_NOC_DUTY":            URL_NOC_DUTY,
    "URL_NOC_DUTY_INCIDENTES": URL_NOC_DUTY_INCIDENTES,
    "URL_JIRA_BROWSE":         URL_JIRA_BROWSE,
}


def validate_env():
    """Valida que las URLs internas obligatorias y los defaults estén configurados en .env."""
    missing = [name for name, value in REQUIRED_URLS.items() if not value]
    if missing:
        print("❌ Faltan variables obligatorias en .env:")
        for name in missing:
            print(f"   - {name}")
        print("   Copiá .env.example a .env y completá los valores.")
        return False
    if not DEFAULT_WORKSPACE and not DEFAULT_ORGANIZATION:
        print("❌ Debe estar configurado al menos DEFAULT_WORKSPACE o DEFAULT_ORGANIZATION en .env.")
        return False
    return True


def get_cookies():
    return {
        "sessionid":        os.getenv("COOKIE_SESSIONID"),
        "csrftoken":        os.getenv("COOKIE_CSRFTOKEN"),
        "CF_Authorization": os.getenv("COOKIE_CF_AUTHORIZATION"),
        "CF_AppSession":    os.getenv("COOKIE_CF_APP_SESSION"),
        "jwt_session":      os.getenv("COOKIE_JWT_SESSION"),
        "__cf_bm":          os.getenv("COOKIE_CF_BM"),
    }


def update_env_cookies(cookies_dict):
    mapping = {
        "sessionid":        "COOKIE_SESSIONID",
        "csrftoken":        "COOKIE_CSRFTOKEN",
        "CF_Authorization": "COOKIE_CF_AUTHORIZATION",
        "CF_AppSession":    "COOKIE_CF_APP_SESSION",
        "jwt_session":      "COOKIE_JWT_SESSION",
        "__cf_bm":          "COOKIE_CF_BM",
    }
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            lines = f.readlines()
    else:
        lines = []

    new_values = {mapping[k]: v for k, v in cookies_dict.items() if k in mapping and v}
    updated_keys = set()
    new_lines = []
    for line in lines:
        key = line.split("=")[0].strip()
        if key in new_values:
            new_lines.append(f"{key}={new_values[key]}\n")
            updated_keys.add(key)
        else:
            new_lines.append(line)

    for key, value in new_values.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w") as f:
        f.writelines(new_lines)

    load_dotenv(override=True)
    print("✅ Cookies actualizadas en .env")


def refresh_cookies_via_browser():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

    print("🌐 Abriendo Chrome para renovar sesión...")
    print("   Iniciá sesión en Noctools y esperá a que cargue el dashboard.")

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")

    driver_path = os.path.join(os.path.dirname(__file__), "chromedriver.exe")
    try:
        if os.path.exists(driver_path):
            driver = webdriver.Chrome(
                service=Service(executable_path=driver_path),
                options=options
            )
        else:
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
    except Exception as e:
        print(f"⚠️  ChromeDriver local incompatible: {e}")
        print("   Descargando versión compatible automáticamente...")
        import shutil
        new_driver_path = ChromeDriverManager().install()
        try:
            if os.path.exists(driver_path):
                os.remove(driver_path)
            shutil.copy2(new_driver_path, driver_path)
            print(f"   ✅ ChromeDriver actualizado en {driver_path}")
            use_path = driver_path
        except OSError:
            print(f"   ℹ️  No se pudo guardar en {driver_path}, usando versión descargada temporalmente.")
            use_path = new_driver_path
        driver = webdriver.Chrome(
            service=Service(executable_path=use_path),
            options=options
        )

    try:
        driver.get(URL_NAGIOS_DASHBOARD)
        print(f"   Esperando que cargues el dashboard (máx. {SELENIUM_TIMEOUT // 60} minutos)...")
        WebDriverWait(driver, SELENIUM_TIMEOUT).until(
            EC.url_contains(URL_NAGIOS_DASHBOARD)
        )
        import time
        time.sleep(SELENIUM_POST_LOGIN_SLEEP)
        selenium_cookies = driver.get_cookies()
        cookies_dict = {c["name"]: c["value"] for c in selenium_cookies}
        print("   ✅ Cookies capturadas correctamente.")
        update_env_cookies(cookies_dict)
        return cookies_dict
    finally:
        driver.quit()


def _resolve_token(candidates, context_label):
    """Intenta resolver un token de una lista de candidatos [(env_key, label)].
    Devuelve (token, label_usado) o (None, None)."""
    for env_key, label in candidates:
        token = os.getenv(env_key)
        if token:
            return token, label
    return None, None


def get_slack_token(workspace, organizacion):
    """Resuelve el bot token de Slack según workspace y organización del CSV.

    Orden de prioridad (la organización pondera sobre workspace):

    Caso 1 (ambos vacíos):     DEFAULT_ORGANIZATION → DEFAULT_WORKSPACE → error
    Caso 2 (ws vacío, org OK): org → DEFAULT_ORGANIZATION → DEFAULT_WORKSPACE → error
    Caso 3 (ws OK, org vacía): workspace → DEFAULT_WORKSPACE → DEFAULT_ORGANIZATION → error
    Caso 4 (ambos OK):         org → workspace → DEFAULT_ORGANIZATION → DEFAULT_WORKSPACE → error

    Flujo normal (silencioso):
      - Caso 3 paso 1: workspace del CSV
      - Caso 4 paso 1: org del CSV
    Todo lo demás: informa qué pasó.
    """
    ws = workspace.strip() if workspace else ""
    org = organizacion.strip() if organizacion else ""

    # Determinar caso y armar lista de candidatos
    if not ws and not org:
        # Caso 1: ambos vacíos
        candidates = [
            (f"SLACK_BOT_TOKEN_{DEFAULT_ORGANIZATION.upper()}", f"DEFAULT_ORGANIZATION ({DEFAULT_ORGANIZATION})"),
            (f"SLACK_BOT_TOKEN_{DEFAULT_WORKSPACE.upper()}",    f"DEFAULT_WORKSPACE ({DEFAULT_WORKSPACE})"),
        ]
        is_normal = False

    elif not ws and org:
        # Caso 2: ws vacío, org OK — org es flujo normal pero falta workspace
        candidates = [
            (f"SLACK_BOT_TOKEN_{org.upper()}",                  f"organización '{org}'"),
            (f"SLACK_BOT_TOKEN_{DEFAULT_ORGANIZATION.upper()}", f"DEFAULT_ORGANIZATION ({DEFAULT_ORGANIZATION})"),
            (f"SLACK_BOT_TOKEN_{DEFAULT_WORKSPACE.upper()}",    f"DEFAULT_WORKSPACE ({DEFAULT_WORKSPACE})"),
        ]
        is_normal = False  # siempre informa porque falta workspace en CSV

    elif ws and not org:
        # Caso 3: ws OK, org vacía — workspace es flujo normal
        candidates = [
            (f"SLACK_BOT_TOKEN_{ws.upper()}",                   f"workspace '{ws}'"),
            (f"SLACK_BOT_TOKEN_{DEFAULT_WORKSPACE.upper()}",    f"DEFAULT_WORKSPACE ({DEFAULT_WORKSPACE})"),
            (f"SLACK_BOT_TOKEN_{DEFAULT_ORGANIZATION.upper()}", f"DEFAULT_ORGANIZATION ({DEFAULT_ORGANIZATION})"),
        ]
        is_normal = True

    else:
        # Caso 4: ambos OK — org es flujo normal
        candidates = [
            (f"SLACK_BOT_TOKEN_{org.upper()}",                  f"organización '{org}'"),
            (f"SLACK_BOT_TOKEN_{ws.upper()}",                   f"workspace '{ws}'"),
            (f"SLACK_BOT_TOKEN_{DEFAULT_ORGANIZATION.upper()}", f"DEFAULT_ORGANIZATION ({DEFAULT_ORGANIZATION})"),
            (f"SLACK_BOT_TOKEN_{DEFAULT_WORKSPACE.upper()}",    f"DEFAULT_WORKSPACE ({DEFAULT_WORKSPACE})"),
        ]
        is_normal = True

    token, used_label = _resolve_token(candidates, f"{ws or '(vacío)'}/{org or '(vacío)'}")

    if not token:
        print(f"❌ No se encontró token para workspace '{ws or '(vacío)'}' organización '{org or '(vacío)'}'.")
        print(f"   Se intentó: {', '.join(c[1] for c in candidates)}")
        return None

    if is_normal and used_label == candidates[0][1]:
        # Flujo normal, primer candidato — silencioso
        return token

    # Informar qué pasó
    if is_normal and used_label != candidates[0][1]:
        print(f"⚠️  Token de {candidates[0][1]} no encontrado. Usando token de {used_label}.")
    else:
        if not ws and not org:
            print(f"⚠️  Workspace y organización vacíos en CSV. Usando token de {used_label}.")
        elif not ws and org:
            print(f"⚠️  Falta workspace en CSV. Usando token de {used_label}.")
        elif ws and not org and used_label != candidates[0][1]:
            print(f"⚠️  Token de {candidates[0][1]} no encontrado. Usando token de {used_label}.")
        else:
            print(f"⚠️  Usando token de {used_label}.")

    return token


def get_slack_subdomain(workspace):
    """Resuelve el subdominio de Slack para permalinks en Telegram.
    Construye el nombre de variable dinámicamente: SLACK_SUBDOMAIN_{WORKSPACE}.
    Usa DEFAULT_WORKSPACE como fallback si workspace está vacío."""
    ws = workspace.strip() if workspace else ""
    if not ws:
        ws = DEFAULT_WORKSPACE
    return os.getenv(f"SLACK_SUBDOMAIN_{ws.upper()}")


def build_slack_permalink(workspace, channel_id, ts):
    """Construye el permalink del mensaje principal de Slack.
    Devuelve la URL o None si el subdominio no está configurado."""
    subdomain = get_slack_subdomain(workspace)
    if not subdomain:
        print(f"⚠️  No se pudo generar el link de Slack: subdominio no configurado para workspace '{workspace or DEFAULT_WORKSPACE}'.")
        return None
    return f"https://{subdomain}.slack.com/archives/{channel_id}/p{ts.replace('.', '')}"


def send_slack_message(channel_id, text, token):
    """Envía un mensaje a Slack con bot token y devuelve el timestamp para el hilo."""
    if not token:
        print("❌ Token de Slack no disponible.")
        return None
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        }
    ]
    r = requests.post(
        SLACK_API,
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel_id, "text": text, "blocks": blocks},
        timeout=SLACK_TIMEOUT
    )
    data = r.json()
    if data.get("ok"):
        return data.get("ts")
    else:
        print(f"❌ Error enviando mensaje: {data.get('error')}")
        return None


def build_thread_blocks(name, description, jira_ticket, jira_url, nr_link, errors_link, issues_link, greeting=""):
    """Construye los bloques del hilo con formato profesional para NOC."""
    blocks = []

    desc_text = f"*Critical Alert Events:*\n{description}" if description else "*Critical Alert Events:*\nNo disponible"
    greeting_part = f"{greeting}, " if greeting else ""
    intro = f"Estimados, {greeting_part}los molesto porque vemos alertada la app *{name}* con el siguiente error:\n\n{desc_text}"
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": intro}
    })

    links = []
    if jira_url:
        links.append(f"• <{jira_url}|🎫 Ticket Jira ({jira_ticket})>")
    if nr_link:
        links.append(f"• <{nr_link}|📊 App Overview>")
    if errors_link:
        links.append(f"• <{errors_link}|❌ Errors>")
    if issues_link:
        links.append(f"• <{issues_link}|🚨 Issues>")

    if links:
        links_text = "*Links:*\n" + "\n".join(links)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": links_text}
        })

    return blocks


def send_slack_thread(channel_id, thread_ts, name, description, jira_ticket, jira_url, nr_link, errors_link, issues_link, token, greeting=""):
    """Envía un mensaje en el hilo con bloques formateados."""
    blocks = build_thread_blocks(name, description, jira_ticket, jira_url, nr_link, errors_link, issues_link, greeting)
    fallback = f"{name} está generando alertas en producción."
    r = requests.post(
        SLACK_API,
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel_id, "thread_ts": thread_ts, "text": fallback, "blocks": blocks},
        timeout=SLACK_TIMEOUT
    )
    return r.json().get("ok", False)


# --- TELEGRAM ---

def is_telegram_in_schedule():
    """Verifica si la hora actual está dentro del rango configurado para Telegram.
    Soporta cruces de medianoche (ej: 18 a 0, o 18 a 2)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(TELEGRAM_TIMEZONE)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()
    hour = now.hour
    start = TELEGRAM_START_HOUR
    end = TELEGRAM_END_HOUR

    if start == end:
        return True  # Mismo número = todo el día
    if start < end:
        return start <= hour < end
    # Cruce de medianoche: start > end (ej: 18 a 0, o 22 a 2)
    return hour >= start or hour < end


def get_greeting():
    """Devuelve el saludo según la hora actual (usando TELEGRAM_TIMEZONE).
    18-05 → 'buenas noches'
    05-12 → 'buenos dias'
    12-18 → 'buenas tardes'"""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(TELEGRAM_TIMEZONE)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now()
    hour = now.hour

    if hour >= 18 or hour < 5:
        return "buenas noches"
    if hour < 12:
        return "buenos dias"
    return "buenas tardes"


def send_telegram_message(chat_id, text):
    """Envía un mensaje a Telegram con el bot token y Markdown.
    Devuelve True si fue exitoso, False si falló."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ Token de Telegram no disponible. Verificá TELEGRAM_BOT_TOKEN en .env")
        return False
    url = f"{TELEGRAM_API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        r = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
        data = r.json()
        if data.get("ok"):
            return True
        else:
            print(f"❌ Error enviando mensaje a Telegram: {data.get('description', 'error desconocido')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Error enviando mensaje a Telegram: {e}")
        return False


def build_telegram_message(name, description, jira_ticket, jira_url, nr_link, errors_link, issues_link, slack_link=None, greeting=""):
    """Construye el mensaje combinado de Telegram con formato Markdown."""
    lines = [f"*🔴 Alerta {name}*", ""]
    greeting_part = f"{greeting}, " if greeting else ""
    lines.append(f"Estimados, {greeting_part}los molesto porque vemos alertada la app *{name}* con el siguiente error:")
    lines.append("")
    if description:
        lines.append("*Critical Alert Events:*")
        lines.append(description)
    else:
        lines.append("*Critical Alert Events:*")
        lines.append("No disponible")
    lines.append("")
    lines.append("*Links:*")
    if jira_url:
        lines.append(f"• 🎫 [Ticket Jira ({jira_ticket})]({jira_url})")
    if nr_link:
        lines.append(f"• 📊 [App Overview]({nr_link})")
    if errors_link:
        lines.append(f"• ❌ [Errors]({errors_link})")
    if issues_link:
        lines.append(f"• 🚨 [Issues]({issues_link})")
    if slack_link:
        lines.append(f"• 💬 [Ver en Slack]({slack_link})")
    return "\n".join(lines)


def send_telegram_alert(name, description, jira_ticket, jira_url, nr_link, errors_link, issues_link, telegram_group_id, slack_link=None, greeting=""):
    """Envía un mensaje de alerta a Telegram si está en horario y tiene group_id."""
    if not telegram_group_id:
        print("⚠️  Telegram: group_id no configurado en la base para este servicio. Mensaje no enviado.")
        return False
    if not is_telegram_in_schedule():
        print(f"⚠️  Telegram fuera de horario ({TELEGRAM_START_HOUR}:00-{TELEGRAM_END_HOUR}:00 {TELEGRAM_TIMEZONE}). Mensaje no enviado.")
        return False
    message = build_telegram_message(name, description, jira_ticket, jira_url, nr_link, errors_link, issues_link, slack_link, greeting)
    return send_telegram_message(telegram_group_id, message)


# --- CANAL MAP ---

def load_channel_map():
    """Carga el CSV de canales y devuelve un dict {servicio: {nombre, id, workspace, organizacion, telegram_group_id}}."""
    channel_map = {}
    if not os.path.exists(CANALES_FILE):
        return channel_map
    with open(CANALES_FILE, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            channel_map[row["servicio"].lower()] = {
                "nombre":             row["canal_nombre"],
                "id":                 row["canal_id"],
                "workspace":          row.get("workspace", ""),
                "organizacion":       row.get("organizacion", ""),
                "telegram_group_id":  row.get("telegram_group_id", ""),
            }
    return channel_map


def find_channel_by_id_workspace(channel_map, channel_id, workspace, organizacion=""):
    """Busca un canal en el CSV por channel_id + workspace o channel_id + organizacion.
    Si organizacion está definida, busca también por organización."""
    for svc, info in channel_map.items():
        if info["id"] != channel_id:
            continue
        if organizacion and info.get("organizacion", "").lower() == organizacion.lower():
            return info["nombre"]
        if info.get("workspace", "").lower() == (workspace or "").lower():
            return info["nombre"]
    return None


def find_telegram_by_chat_id(channel_map, chat_id):
    """Busca un grupo de Telegram en el CSV por chat_id."""
    for svc, info in channel_map.items():
        if info.get("telegram_group_id", "") == chat_id:
            return info["nombre"]
    return None


# --- FETCH / PARSE ---

def fetch_json(url, headers=None, cookies=None):
    if headers is None:
        headers = HEADERS_ALERTS
    if cookies is None:
        cookies = get_cookies()
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=REQUESTS_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.JSONDecodeError:
        return None
    except requests.exceptions.RequestException as e:
        print(f"\u274c Error al conectar: {e}")
        return None


def cookies_expired(cookies):
    """Verifica si las cookies están vencidas chequeando ambos endpoints:
    alertas y tickets. Si cualquiera devuelve login HTML, dispara renovación."""
    for url, headers in [(URL_ALERTS_NO_ACK, HEADERS_ALERTS), (build_tickets_url(), HEADERS_TICKETS)]:
        try:
            r = requests.get(url, headers=headers, cookies=cookies,
                             timeout=REQUESTS_TIMEOUT, allow_redirects=False)
            if r.status_code in (301, 302) or "text/html" in r.headers.get("content-type", ""):
                return True
            r.json()
        except Exception:
            return True
    return False


def build_tickets_url():
    today = datetime.now()
    start = today - timedelta(days=TICKETS_LOOKBACK_DAYS)
    ts = int(today.timestamp() * 1000)
    return f"{URL_NOC_DUTY_INCIDENTES}/{TICKETS_FILTER}/{start.strftime('%Y-%m-%d')}/{today.strftime('%Y-%m-%d')}?_={ts}"


def extract_newrelic_app_link(plugin_output):
    match = re.search(NR_APP_LINK_PATTERN, plugin_output)
    return match.group(1) if match else None


def extract_newrelic_errors_link(plugin_output):
    match = re.search(NR_ERRORS_LINK_PATTERN, plugin_output)
    return match.group(1) if match else None


def extract_newrelic_issues_link(plugin_output):
    match = re.search(NR_ISSUES_LINK_PATTERN, plugin_output)
    return match.group(1) if match else None


def extract_incident_description(long_plugin_output):
    """Extrae las descripciones del incidente del long_plugin_output.
    Deduplica descripciones repetidas mostrando un contador (xN)."""
    if not long_plugin_output:
        return None
    matches = re.findall(r'"([^"]+)"', long_plugin_output)
    if not matches:
        return None
    # Deduplicar preservando el orden
    unique = []
    counts = {}
    for m in matches:
        if m not in counts:
            unique.append(m)
            counts[m] = 1
        else:
            counts[m] += 1
    lines = []
    for m in unique:
        if counts[m] > 1:
            lines.append(f"• {m} (x{counts[m]})")
        else:
            lines.append(f"• {m}")
    return "\n".join(lines) if len(lines) > 1 else lines[0]


def build_ticket_map(tickets_data):
    ticket_map = {}
    for row in tickets_data.get("data", []):
        if len(row) >= 6 and row[2] and row[5]:
            ticket_map[row[2].lower()] = row[5]
    return ticket_map


def parse_alerts(data):
    services = data.get("services", [])
    return [s for s in services if s.get("state") == 2]


# --- LOG ROUTINE (removable) ---
def write_log(ticket, host, service, channel_nombre):
    """Escribe una entrada en alerts.log para cada servicio escalado."""
    entry = f"{ticket} | Nagios NR | {host} | {service} --> Se escala via slack con {channel_nombre}.\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"📝 Logueado: {entry.strip()}")
# --- FIN LOG ROUTINE ---


# --- TEST MODE ---

def run_test_mode(args):
    """Modo TEST: envía un mensaje de prueba a un canal de Slack o Telegram.

    Uso:
      python noctools_alerts.py test --slack "mensaje" "channel_id" "workspace_o_organizacion"
      python noctools_alerts.py test --telegram "mensaje" "chat_id"
      python noctools_alerts.py test "mensaje" "channel_id" "workspace_o_organizacion"  (default: --slack)
    """
    # Detectar flag de plataforma
    platform = "slack"  # default
    filtered_args = []
    for arg in args:
        if arg == "--slack":
            platform = "slack"
        elif arg == "--telegram":
            platform = "telegram"
        else:
            filtered_args.append(arg)

    if platform == "slack":
        # args: test "mensaje" "channel_id" "workspace_o_organizacion"
        if len(filtered_args) < 4:
            print('Uso: python noctools_alerts.py test --slack "mensaje" "channel_id" "workspace_o_organizacion"')
            print('      python noctools_alerts.py test "mensaje" "channel_id" "workspace_o_organizacion"  (default)')
            return

        message    = filtered_args[1]
        channel_id = filtered_args[2]
        ws_or_org  = filtered_args[3]

        channel_map = load_channel_map()
        # Buscar por workspace o por organizacion
        channel_nombre = find_channel_by_id_workspace(channel_map, channel_id, ws_or_org)

        if channel_nombre:
            print(f"Enviando TEST Message al canal '{channel_nombre}' en '{ws_or_org}'")
        else:
            print(f"El canal a testear con ID '{channel_id}' no se encuentra en la base para '{ws_or_org}'")

        # Resolver token: el parámetro puede ser workspace o organizacion.
        # Si está vacío, probar DEFAULT_ORGANIZATION → DEFAULT_WORKSPACE.
        if ws_or_org:
            # Primero intentar como organización, luego como workspace
            token = os.getenv(f"SLACK_BOT_TOKEN_{ws_or_org.upper()}")
            if token:
                pass  # encontrado
            else:
                # Probar como si fuera un workspace con org vacía
                token = get_slack_token(ws_or_org, "")
                if not token:
                    return
        else:
            # Parámetro vacío: probar DEFAULT_ORGANIZATION → DEFAULT_WORKSPACE
            token = os.getenv(f"SLACK_BOT_TOKEN_{DEFAULT_ORGANIZATION.upper()}") if DEFAULT_ORGANIZATION else None
            if token:
                print(f"⚠️  Parámetro vacío. Usando token de DEFAULT_ORGANIZATION ({DEFAULT_ORGANIZATION}).")
            else:
                token = os.getenv(f"SLACK_BOT_TOKEN_{DEFAULT_WORKSPACE.upper()}")
                if token:
                    print(f"⚠️  Parámetro vacío. Usando token de DEFAULT_WORKSPACE ({DEFAULT_WORKSPACE}).")
                else:
                    print("❌ No se encontró token. Definí DEFAULT_ORGANIZATION o DEFAULT_WORKSPACE en .env.")
                    return

        ts = send_slack_message(channel_id, message, token)
        if ts:
            print("✅ Mensaje de TEST enviado correctamente")

    elif platform == "telegram":
        # args: test --telegram "mensaje" "chat_id"
        if len(filtered_args) < 3:
            print('Uso: python noctools_alerts.py test --telegram "mensaje" "chat_id"')
            return

        message = filtered_args[1]
        chat_id = filtered_args[2]

        channel_map = load_channel_map()
        channel_nombre = find_telegram_by_chat_id(channel_map, chat_id)

        if channel_nombre:
            print(f"Enviando TEST Message al grupo '{channel_nombre}' en Telegram")
        else:
            print(f"El grupo a testear con ID '{chat_id}' no se encuentra en la base")

        ts = send_telegram_message(chat_id, message)
        if ts:
            print("✅ Mensaje de TEST enviado correctamente")


# --- ALERTAS ---

def generate_slack_messages(services, ticket_map, channel_map, send=False, show_ack=False, log=False,
                            fallback_failed=False):
    if not services:
        print("✅ No hay alarmas CRITICAL sin acknowledged." if not show_ack else "✅ No hay alarmas CRITICAL activas.")
        return

    modo = "TODAS (incl. acknowledged)" if show_ack else "SIN ACKNOWLEDGED"
    print(f"\n{'='*60}")
    print(f"  ALARMAS CRITICAL — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"  Modo: {modo}")
    print(f"  Total: {len(services)}")
    print(f"{'='*60}\n")

    # Saludo segun horario (una vez por ejecucion)
    greeting = get_greeting()

    for svc in services:
        name          = svc.get("display_name") or svc.get("description")
        plugin_output = svc.get("plugin_output", "")
        nr_link       = extract_newrelic_app_link(plugin_output)
        errors_link   = extract_newrelic_errors_link(plugin_output)
        issues_link   = extract_newrelic_issues_link(plugin_output)
        description   = extract_incident_description(svc.get("long_plugin_output", ""))
        acknowledged  = svc.get("acknowledged", 0)
        do_not_call   = svc.get("do_not_call", False)
        nebula        = svc.get("nebula_info", {})
        group_email   = nebula.get("group_email", "")
        criticality   = nebula.get("criticality", "—")
        svc_description = svc.get("description", "")
        appname        = svc.get("custom_variables", {}).get("APPNAME", "").strip('"').lower()

        # Ticket de Jira: fuente principal es el campo "ticket" del JSON de alertas.
        # Fallback a NocDuty solo si el JSON está fallando (ningún servicio tiene ticket).
        # Si el JSON funciona pero un servicio no tiene ticket, significa que aún no fue creado en Jira.
        ticket = svc.get("ticket")
        jira_url = None
        if ticket:
            jira_url = f"{URL_JIRA_BROWSE}/{ticket}"
        else:
            nocduty_ticket = ticket_map.get(appname) or ticket_map.get(svc_description.lower()) or ticket_map.get(name.lower())
            if nocduty_ticket:
                ticket = nocduty_ticket
                jira_url = f"{URL_JIRA_BROWSE}/{ticket}"
                print(f"   ℹ️  Ticket no encontrado en alertas. Obtenido via NocDuty: {ticket}")
            elif fallback_failed:
                ticket = "Falló la consulta del ticket de Jira"
            else:
                ticket = "Ticket de Jira no creado"

        channel       = channel_map.get(appname) or channel_map.get(svc_description.lower()) or channel_map.get(name.lower())
        en_database   = "✅ Sí" if channel else "❌ No"

        print(f"┌─ Servicio: {name}")
        print(f"│  Host:        {svc.get('host_alias') or svc.get('host_name')}")
        print(f"│  Criticidad:  {criticality}")
        print(f"│  Acknowledged:{' ✅ Sí' if acknowledged else ' ❌ No'}")
        print(f"│  Do not call: {' 🔕 Sí' if do_not_call else ' 📞 No'}")
        if group_email:
            print(f"│  Equipo:      {group_email}")
        print(f"│  Ticket Jira: {ticket}")
        print(f"│  En Database: {en_database}")
        if channel:
            ws_display = channel.get("workspace", "") or "(vacío)"
            org_display = channel.get("organizacion", "") or "(vacío)"
            print(f"│  Workspace:   {ws_display}")
            print(f"│  Organización: {org_display}")
            tg_id = channel.get("telegram_group_id", "")
            if tg_id:
                print(f"│  Telegram:    {tg_id}")
            else:
                print(f"│  Telegram:    ❌ No configurado")
        print(f"└{'─'*58}")
        print()

        print("📋 MENSAJE PRINCIPAL (pegar en el canal):")
        print(f"*🔴 Alerta {name}*")
        print()

        print("💬 HILO (pegar como reply al mensaje anterior):")
        print(f"Estimados, {greeting}, los molesto porque vemos alertada la app *{name}* con el siguiente error:")
        print()
        if description:
            print("*Critical Alert Events:*")
            print(description)
        print()
        print("*Links:*")
        if jira_url:
            print(f"• 🎫 Ticket Jira ({ticket}): {jira_url}")
        if nr_link:
            print(f"• 📊 App Overview: {nr_link}")
        if errors_link:
            print(f"• ❌ Errors: {errors_link}")
        if issues_link:
            print(f"• 🚨 Issues: {issues_link}")

        if send:
            send_success = False
            if not channel:
                print(f'❌ Error al enviar mensaje a {name}, "servicio no encontrado en Database"')
            else:
                workspace = channel.get("workspace", "")
                organizacion = channel.get("organizacion", "")
                channel_nombre = channel.get("nombre", "desconocido")
                channel_id = channel.get("id")
                telegram_group_id = channel.get("telegram_group_id", "")

                ws_display = workspace or "(vacío)"
                org_display = organizacion or "(vacío)"
                tag = f"[{ws_display}/{org_display}]"

                # Validar datos requeridos antes de enviar
                missing = []
                if not name:
                    missing.append("nombre de servicio")
                if not channel_nombre:
                    missing.append("channel_nombre")
                if not channel_id:
                    missing.append("channel_id")
                if not workspace and not organizacion:
                    missing.append("workspace u organización")
                if not jira_url:
                    missing.append("Ticket Jira")
                if not description:
                    missing.append("Critical Alert Events")
                if not nr_link:
                    missing.append("App Overview link")
                if not errors_link:
                    missing.append("Errors link")
                if not issues_link:
                    missing.append("Issues link")

                token = get_slack_token(workspace, organizacion)
                if not token:
                    missing.append("Slack Bot Token")

                if missing:
                    print(f'❌ Error al enviar mensaje a #{channel_nombre} {tag}, "Falta: {", ".join(missing)}"')
                else:
                    # --- Enviar a Slack ---
                    print(f"📤 Enviando a Slack #{channel_nombre} {tag}...")
                    ts = send_slack_message(channel_id, f"*🔴 Alerta {name}*", token)
                    if ts:
                        ok = send_slack_thread(channel_id, ts, name, description, ticket, jira_url, nr_link, errors_link, issues_link, token, greeting)
                        if ok:
                            send_success = True
                            print(f"✅ Enviado correctamente a Slack #{channel_nombre} {tag}")
                        else:
                            print(f'❌ Error al enviar mensaje a Slack #{channel_nombre} {tag}, "fallo el envío del hilo"')
                    else:
                        print(f'❌ Error al enviar mensaje a Slack #{channel_nombre} {tag}, "fallo el envío del mensaje principal"')

                    # --- Enviar a Telegram (solo si Slack fue exitoso) ---
                    if send_success:
                        # Construir permalink del mensaje de Slack
                        slack_link = build_slack_permalink(workspace, channel_id, ts)
                        print(f"📤 Enviando a Telegram {telegram_group_id}...")
                        tg_ok = send_telegram_alert(name, description, ticket, jira_url,
                                                    nr_link, errors_link, issues_link,
                                                    telegram_group_id, slack_link, greeting)
                        if tg_ok:
                            print(f"✅ Enviado correctamente a Telegram {telegram_group_id}")
                    else:
                        print(f"⚠️  Telegram no enviado: el envío a Slack falló.")

        print()
        if log:
            if send and not send_success:
                print("⚠️ Error al realizar log, fallo el envio de mensaje.")
            elif not channel:
                print(f"⚠️ Error al realizar log, el servicio '{name}' no se encuentra en Database.")
            elif not jira_url:
                print("⚠️ Error al realizar log, falta: Ticket Jira.")
            else:
                host = svc.get("host_alias") or svc.get("host_name")
                write_log(ticket, host, appname or svc_description or name, channel["nombre"])
        else:
            print("📝 Modo log inactivo")

        print("-" * 60)
        print()


def main():
    if not validate_env():
        sys.exit(1)

    args = [arg.lower() for arg in sys.argv[1:]]

    # --- Modo TEST ---
    if "test" in args:
        run_test_mode(sys.argv[1:])
        return

    # --- Modo normal ---
    show_ack = "showack" in args
    send     = "send" in args
    log      = "log" in args and not show_ack

    if "log" in args and show_ack:
        print("⚠️  El parámetro 'log' no puede usarse junto con 'showack'. No se loguearán entradas.")

    if log:
        print("📝 Modo log activo")
    else:
        print("📝 Modo log inactivo")
    print("🔍 Consultando Noctools...")
    cookies = get_cookies()

    if cookies_expired(cookies):
        print("⚠️  Las cookies expiraron. Renovando sesión...")
        refresh_cookies_via_browser()
        cookies = get_cookies()

    url = URL_ALERTS_ACK if show_ack else URL_ALERTS_NO_ACK
    alerts_data = fetch_json(url, headers=HEADERS_ALERTS, cookies=cookies)
    if not alerts_data:
        print("❌ No se pudo obtener las alertas.")
        return

    if not alerts_data.get("status", {}).get("NewRelic"):
        print("⚠️  NewRelic aparece como inactivo en el status.")

    channel_map = load_channel_map()
    critical_services = parse_alerts(alerts_data)

    # Ticket de Jira: la fuente principal es el campo "ticket" del JSON de alertas.
    # El fallback a NocDuty se hace SOLO si ningún servicio crítico tiene el campo "ticket",
    # lo que indica que el JSON está fallando. Si algunos tienen y otros no, los que no
    # tienen simplemente aún no fueron creados en Jira (NocDuty tampoco los tendrá).
    ticket_map = {}
    fallback_failed = False
    if critical_services and not any(svc.get("ticket") for svc in critical_services):
        print("🎫 Consultando tickets Jira (fallback)...")
        tickets_data = fetch_json(build_tickets_url(), headers=HEADERS_TICKETS, cookies=cookies)
        if tickets_data:
            ticket_map = build_ticket_map(tickets_data)
        else:
            print("   ⚠️  NocDuty no disponible. Falló la consulta del ticket de Jira.")
            fallback_failed = True
    elif critical_services:
        print("🎫 Tickets obtenidos del JSON de alertas.")

    generate_slack_messages(critical_services, ticket_map, channel_map, send=send, show_ack=show_ack, log=log,
                            fallback_failed=fallback_failed)


if __name__ == "__main__":
    main()
