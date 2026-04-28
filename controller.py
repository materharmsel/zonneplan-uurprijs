"""Controller voor inverter-curtailment — hoofdmodule voor cron-uitvoering.

Werking per cron-tick (@hourly :01):
  1. Haal huidige elektriciteits-uurprijs op (of gebruik FAKE_PRICE voor tests).
  2. Bepaal gewenste staat: 'limited' bij prijs < 0, anders 'normal'.
  3. Pas per inverter de staat toe als die afwijkt van de huidige.
  4. Bij fout: schrijf alarm.flag en ga door naar de volgende inverter.
"""

import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import yaml

import fetch_prices as price_fetcher
import kostal_adapter
import steca_adapter
import state_store

_DIR = Path(__file__).parent
_INVERTERS_YAML = _DIR / "config" / "inverters.yaml"
_MENU_YAML = _DIR / "config" / "menu_paths.yaml"
_SCREENS_JSON = _DIR / "config" / "screens.json"
_LOG_FILE = _DIR / "logs" / "controller.log"

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[handler, logging.StreamHandler(sys.stdout)],
    )


def _load_config() -> tuple[dict, dict, dict]:
    inverters_raw = yaml.safe_load(_INVERTERS_YAML.read_text())["inverters"]
    inverters = {inv_id: {"id": inv_id, **cfg} for inv_id, cfg in inverters_raw.items()}
    actions = yaml.safe_load(_MENU_YAML.read_text())["actions"]
    screens = json.loads(_SCREENS_JSON.read_text()) if _SCREENS_JSON.exists() else {}
    return inverters, actions, screens


def _get_current_price() -> float:
    fake = os.environ.get("FAKE_PRICE")
    if fake is not None:
        price = float(fake)
        log.info("FAKE_PRICE override: %.6f EUR/kWh", price)
        return price
    price = price_fetcher.fetch_current_price()
    log.info("Huidige prijs: %.6f EUR/kWh", price)
    return price


def _desired_state(price: float) -> str:
    return "limited" if price < 0.0 else "normal"


def run() -> None:
    """Bepaal gewenste staat en pas die toe op alle inverters."""
    price = _get_current_price()
    desired = _desired_state(price)
    log.info("Gewenste staat: %s (prijs=%.6f EUR/kWh)", desired, price)

    inverters, actions, screens = _load_config()

    # Opzoeken op aanroeptijd zodat unit-test patches werken.
    adapter_map = {
        "steca": steca_adapter,
        "kostal": kostal_adapter,
    }

    had_error = False
    for inverter_id, inverter_cfg in inverters.items():
        current = state_store.get_state(inverter_id)
        if current == desired:
            log.info("%s: al in staat '%s' — overgeslagen", inverter_id, desired)
            continue

        log.info("%s: overgang %s → %s", inverter_id, current, desired)
        try:
            adapter = adapter_map[inverter_id]
            adapter.apply(desired, inverter_cfg["ip"], inverter_cfg, actions, screens)
            state_store.set_state(inverter_id, desired)
            log.info("%s: staat bijgewerkt naar '%s'", inverter_id, desired)
        except Exception as exc:
            had_error = True
            msg = f"{inverter_id}: fout bij toepassen '{desired}': {exc}"
            log.error(msg)
            state_store.write_alarm(msg)

    if not had_error:
        state_store.clear_alarm()


if __name__ == "__main__":
    _setup_logging()
    run()
