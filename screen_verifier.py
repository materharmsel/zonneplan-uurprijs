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
