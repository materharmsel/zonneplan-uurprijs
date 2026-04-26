"""Low-level HTTP-laag voor inverter-aansturing via knop-emulatie."""

import io
import time

import requests
from PIL import Image


def press(ip: str, button: str, duration: str = "short", delay_ms: int = 300) -> None:
    """Emuleert één knopdruk op de inverter (kort of lang).

    Stuurt de volledige event-sequentie:
    - kort: clicked → released
    - lang:  clicked → long → released
    """
    base = f"http://{ip}/buttons.html"

    def _get(event: str) -> None:
        r = requests.get(f"{base}?BUTTON={button}&EVENT={event}", timeout=5)
        r.raise_for_status()
        time.sleep(delay_ms / 1000)

    _get("clicked")
    if duration == "long":
        _get("long")
    _get("released")


def get_screen(ip: str) -> Image.Image:
    """Haalt het huidige LCD-scherm op als PIL Image (256×128 BMP)."""
    r = requests.get(f"http://{ip}/gen.screenshot.bmp", timeout=5)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content))
