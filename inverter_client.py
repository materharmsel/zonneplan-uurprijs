"""Low-level HTTP-laag voor inverter-aansturing via knop-emulatie."""

import io
import time

import requests
from PIL import Image


def press(ip: str, button: str, duration: str = "short", delay_ms: int = 300) -> None:
    """Emuleert één knopdruk op de inverter (kort of lang).

    Het webinterface accepteert query-parameters:
    - button: ESC, UP, DOWN, SET, BOTHMIDDLE (SERVICE), ESCUP
    - duration: "short" of "long" (alleen relevant voor SET → LONGSET)
    """
    button_value = button
    if button == "SET" and duration == "long":
        button_value = "LONGSET"

    url = f"http://{ip}/page.main.html?BUTTON_PRESSED={button_value}"
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    time.sleep(delay_ms / 1000)


def get_screen(ip: str) -> Image.Image:
    """Haalt het huidige LCD-scherm op als PIL Image (256×128 BMP)."""
    r = requests.get(f"http://{ip}/gen.screenshot.bmp", timeout=5)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content))
