"""
Haalt de Zonneplan uurprijzen op voor de huidige dag en schrijft ze naar een logbestand.

Gebruik:
    python fetch_prices.py

Eerste keer: vraagt om e-mailadres en stuurt een inloglink.
Daarna: tokens worden hergebruikt vanuit ~/.zonneplan_tokens.json.
Log wordt bijgehouden in ~/zonneplan_prices.log.
"""

import json
import sys
import time
import logging
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TOKEN_FILE = Path.home() / ".zonneplan_tokens.json"
LOG_FILE = Path.home() / "zonneplan_prices.log"
BASE_URL = "https://app-api.zonneplan.nl"

try:
    TZ = ZoneInfo("Europe/Amsterdam")
except Exception:
    # Windows zonder tzdata-pakket: gebruik UTC+1 als vaste offset (geen zomertijd)
    # Installeer 'tzdata' via pip voor correcte zomertijdafhandeling.
    import datetime as _dt
    TZ = _dt.timezone(_dt.timedelta(hours=1))

HEADERS = {
    "content-type": "application/json;charset=utf-8",
    "x-app-version": "5.10.1",
    "x-app-environment": "production",
}

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configureer logging voor handmatig CLI-gebruik (`python fetch_prices.py`).

    Wordt expliciet door main() aangeroepen — niet op import-tijd, anders zou
    een importerende module (zoals controller.py) zijn eigen logging-setup
    overruled zien."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def load_tokens() -> dict | None:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def save_tokens(tokens: dict) -> None:
    TOKEN_FILE.write_text(json.dumps(tokens))


def auth_headers(access_token: str) -> dict:
    return {**HEADERS, "Authorization": f"Bearer {access_token}"}


def refresh_access_token(refresh_token: str) -> str:
    r = requests.post(
        f"{BASE_URL}/oauth/token",
        json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    tokens = r.json()
    save_tokens(tokens)
    log.debug("Access token vernieuwd.")
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Login flow (eenmalig)
# ---------------------------------------------------------------------------

def login_flow() -> dict:
    email = input("Voer je Zonneplan e-mailadres in: ").strip()

    r = requests.post(f"{BASE_URL}/auth/request", json={"email": email}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    uuid = r.json()["data"]["uuid"]
    print("Inloglink verstuurd — klik op de link in je e-mail en wacht...")

    otp = None
    for _ in range(60):
        time.sleep(5)
        r = requests.get(f"{BASE_URL}/auth/request/{uuid}", headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        if data.get("is_activated") and data.get("password"):
            otp = data["password"]
            break
        print("  Wachten op bevestiging...")
    else:
        sys.exit("Timeout: geen bevestiging ontvangen binnen 5 minuten.")

    r = requests.post(
        f"{BASE_URL}/oauth/token",
        json={"grant_type": "one_time_password", "email": email, "password": otp},
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    tokens = r.json()
    save_tokens(tokens)
    log.info("Ingelogd en tokens opgeslagen in %s", TOKEN_FILE)
    return tokens


# ---------------------------------------------------------------------------
# Connection UUID ophalen
# ---------------------------------------------------------------------------

def get_electricity_connection(access_token: str) -> str:
    r = requests.get(f"{BASE_URL}/user-accounts/me", headers=auth_headers(access_token), timeout=15)
    if r.status_code == 401:
        raise PermissionError("401")
    r.raise_for_status()
    for group in r.json()["data"]["address_groups"]:
        for conn in group["connections"]:
            if conn.get("market_segment") == "electricity":
                return conn["uuid"]
    raise RuntimeError("Geen elektriciteitsaansluiting gevonden in je account.")


# ---------------------------------------------------------------------------
# Prijzen ophalen
# ---------------------------------------------------------------------------

def fetch_prices(connection_uuid: str, access_token: str) -> list[dict]:
    r = requests.get(
        f"{BASE_URL}/connections/{connection_uuid}/summary",
        headers=auth_headers(access_token),
        timeout=15,
    )
    if r.status_code == 401:
        raise PermissionError("401")
    r.raise_for_status()
    return r.json()["data"]["price_per_hour"]


def filter_today(price_per_hour: list[dict]) -> list[dict]:
    today = date.today()
    result = []
    for entry in price_per_hour:
        dt = datetime.fromisoformat(entry["datetime"]).astimezone(TZ)
        if dt.date() == today:
            result.append({
                "hour": dt.strftime("%H:%M"),
                "price_eur": round(entry["electricity_price"] * 0.0000001, 6),
                "tariff_group": entry.get("tariff_group", ""),
            })
    return sorted(result, key=lambda x: x["hour"])


# ---------------------------------------------------------------------------
# Prijs voor huidig uur (gebruikt door controller.py)
# ---------------------------------------------------------------------------

def fetch_current_price() -> float:
    """Geeft de elektriciteits-uurprijs voor het huidige uur terug (€/kWh).

    Hergebruikt het token-mechanisme; gooit RuntimeError als er geen tokens
    zijn of geen prijs beschikbaar is voor het huidige uur.
    """
    tokens = load_tokens()
    if not tokens:
        raise RuntimeError("Geen tokens — voer eerst in via: python fetch_prices.py")

    access_token = tokens.get("access_token", "")
    try:
        connection_uuid = get_electricity_connection(access_token)
        raw = fetch_prices(connection_uuid, access_token)
    except PermissionError:
        log.info("Access token verlopen — vernieuwen...")
        access_token = refresh_access_token(tokens["refresh_token"])
        connection_uuid = get_electricity_connection(access_token)
        raw = fetch_prices(connection_uuid, access_token)

    now = datetime.now(TZ)
    for entry in raw:
        dt = datetime.fromisoformat(entry["datetime"]).astimezone(TZ)
        if dt.date() == now.date() and dt.hour == now.hour:
            return round(entry["electricity_price"] * 0.0000001, 6)

    raise RuntimeError(
        f"Geen prijs beschikbaar voor het huidige uur ({now.strftime('%H:%M')})."
    )


# ---------------------------------------------------------------------------
# Loggen
# ---------------------------------------------------------------------------

def log_prices(prices: list[dict]) -> None:
    if not prices:
        log.warning("Geen uurprijzen beschikbaar voor vandaag.")
        return

    today_str = date.today().isoformat()
    log.info("=== Uurprijzen voor %s (%d uur) ===", today_str, len(prices))
    for p in prices:
        marker = " ← NEGATIEF" if p["price_eur"] < 0 else ""
        log.info(
            "  %s  %+.4f EUR/kWh  [%s]%s",
            p["hour"],
            p["price_eur"],
            p["tariff_group"],
            marker,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _setup_logging()
    tokens = load_tokens()
    if not tokens:
        tokens = login_flow()

    access_token = tokens.get("access_token", "")

    try:
        connection_uuid = get_electricity_connection(access_token)
        price_per_hour = fetch_prices(connection_uuid, access_token)
    except PermissionError:
        log.info("Access token verlopen — vernieuwen...")
        access_token = refresh_access_token(tokens["refresh_token"])
        connection_uuid = get_electricity_connection(access_token)
        price_per_hour = fetch_prices(connection_uuid, access_token)

    prices_today = filter_today(price_per_hour)
    log_prices(prices_today)


if __name__ == "__main__":
    main()
