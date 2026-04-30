"""BMP-hash verificatie van inverter LCD-schermen tegen gecalibreerde hashes.

Een screen_id mag één hash (str) of meerdere hashes (lijst) hebben. Meerdere
hashes zijn nodig voor schermen met een knipperende cursor: SHA-256 over de
hele bitmap verandert dan tussen frames, dus calibrate.py legt meerdere
varianten vast en identify/verify accepteert iedere match.
"""

import hashlib

from PIL import Image


def hash_image(image: Image.Image) -> str:
    """Berekent SHA-256 hash van de volledige afbeelding (pixel-bytes)."""
    return hashlib.sha256(image.tobytes()).hexdigest()


def _matches(stored, current_hash: str) -> bool:
    """True als de huidige hash overeenkomt met de opgeslagen waarde (str of list)."""
    if isinstance(stored, list):
        return current_hash in stored
    return stored == current_hash


def verify(image: Image.Image, screen_id: str, screens: dict) -> bool:
    """Vergelijkt het scherm met de opgeslagen referentie-hash(es).

    Geeft True terug als screen_id bekend is én de hash overeenkomt met
    één van de opgeslagen varianten.
    """
    if screen_id not in screens:
        return False
    return _matches(screens[screen_id], hash_image(image))


def identify(image: Image.Image, screens: dict, prefix: str) -> str | None:
    """Geeft de screen_id terug als het scherm overeenkomt met een opgeslagen hash.

    Zoekt alleen in hashes met het opgegeven prefix (bijv. 'steca' of 'kostal').
    Geeft None terug als het scherm onbekend is.
    """
    h = hash_image(image)
    full_prefix = prefix + "."
    for key, stored in screens.items():
        if key.startswith(full_prefix) and _matches(stored, h):
            return key[len(full_prefix):]
    return None
