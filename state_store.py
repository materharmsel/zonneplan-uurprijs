"""Atomische JSON-state opslag en alarm-beheer voor inverter-curtailment."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DIR = Path(__file__).parent
_DEFAULT_STATE = _DIR / "state" / "inverter_state.json"
_DEFAULT_ALARM = _DIR / "state" / "alarm.flag"


def get_state(inverter_id: str, path: Path = _DEFAULT_STATE) -> str | None:
    """Geeft de opgeslagen staat voor inverter_id, of None als onbekend/onleesbaar."""
    try:
        data = json.loads(path.read_text())
        return data.get(inverter_id)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def set_state(inverter_id: str, state: str, path: Path = _DEFAULT_STATE) -> None:
    """Schrijft state voor inverter_id atomisch naar het JSON-bestand."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data[inverter_id] = state
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def write_alarm(reason: str, path: Path = _DEFAULT_ALARM) -> None:
    """Schrijft een alarm.flag met timestamp en reden."""
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    path.write_text(f"{timestamp} — {reason}\n")


def clear_alarm(path: Path = _DEFAULT_ALARM) -> None:
    """Verwijdert alarm.flag; doet niets als die niet bestaat."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass
