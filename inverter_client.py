"""Low-level HTTP-laag voor inverter-aansturing via knop-emulatie.

Twee URL-stijlen worden ondersteund (zie config/inverters.yaml → api_style):

- "new"    — Steca-firmware: GET /page.main.html?BUTTON_PRESSED=<knop>
             (bij lang indrukken van SET: BUTTON_PRESSED=LONGSET; voor andere
             knoppen is er geen aparte lange variant).
- "legacy" — Kostal Piko-firmware: GET /buttons.html?BUTTON=<knop>&EVENT=<event>
             met event-sequence clicked → released (kort) of clicked → long →
             released (lang). Een losse 'clicked' zonder 'released' laat de
             knop ingedrukt en kan de menu-state-machine doorhalen.
"""

import io
import time

import requests
from PIL import Image


def _press_new(ip: str, button: str, duration: str, delay_ms: int) -> None:
    button_value = button
    if button == "SET" and duration == "long":
        button_value = "LONGSET"
    url = f"http://{ip}/page.main.html?BUTTON_PRESSED={button_value}"
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    time.sleep(delay_ms / 1000)


def _press_legacy(ip: str, button: str, duration: str, delay_ms: int) -> None:
    base = f"http://{ip}/buttons.html"

    def _get(event: str) -> None:
        r = requests.get(f"{base}?BUTTON={button}&EVENT={event}", timeout=5)
        r.raise_for_status()
        time.sleep(delay_ms / 1000)

    _get("clicked")
    if duration == "long":
        _get("long")
    _get("released")


def press(
    ip: str,
    button: str,
    duration: str = "short",
    delay_ms: int = 300,
    api_style: str = "new",
) -> None:
    """Emuleert één knopdruk op de inverter (kort of lang).

    button: ESC | UP | DOWN | SET | BOTHMIDDLE
    duration: "short" of "long"
    api_style: "new" (Steca) of "legacy" (Kostal Piko)
    """
    if api_style == "legacy":
        _press_legacy(ip, button, duration, delay_ms)
    elif api_style == "new":
        _press_new(ip, button, duration, delay_ms)
    else:
        raise ValueError(f"Onbekende api_style: {api_style!r}")


def get_screen(ip: str) -> Image.Image:
    """Haalt het huidige LCD-scherm op als PIL Image (256×128 BMP)."""
    r = requests.get(f"http://{ip}/gen.screenshot.bmp", timeout=5)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content))
