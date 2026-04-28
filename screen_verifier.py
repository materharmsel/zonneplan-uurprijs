"""BMP-hash verificatie van inverter LCD-schermen tegen gecalibreerde hashes."""

import hashlib

from PIL import Image


def hash_image(image: Image.Image) -> str:
    """Berekent SHA-256 hash van de volledige afbeelding (pixel-bytes)."""
    return hashlib.sha256(image.tobytes()).hexdigest()


def verify(image: Image.Image, screen_id: str, screens: dict) -> bool:
    """Vergelijkt het scherm met de opgeslagen referentie-hash.

    Geeft True terug als screen_id bekend is én de hash overeenkomt.
    """
    if screen_id not in screens:
        return False
    return hash_image(image) == screens[screen_id]


def identify(image: Image.Image, screens: dict, prefix: str) -> str | None:
    """Geeft de screen_id terug als het scherm overeenkomt met een opgeslagen hash.

    Zoekt alleen in hashes met het opgegeven prefix (bijv. 'steca' of 'kostal').
    Geeft None terug als het scherm onbekend is.
    """
    h = hash_image(image)
    full_prefix = prefix + "."
    for key, stored_hash in screens.items():
        if key.startswith(full_prefix) and stored_hash == h:
            return key[len(full_prefix):]
    return None
