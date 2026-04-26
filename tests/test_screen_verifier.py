"""Tests voor screen_verifier — BMP-hash verificatie."""

import hashlib
import io
import unittest

from PIL import Image


def _make_image(color: int = 0) -> Image.Image:
    """Hulpfunctie: maak een 256×128 monochroom testafbeelding."""
    return Image.new("1", (256, 128), color=color)


def _hash_of(image: Image.Image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


class TestHashImage(unittest.TestCase):
    """Tests voor hash_image()."""

    def test_returns_string(self):
        from screen_verifier import hash_image
        result = hash_image(_make_image())
        self.assertIsInstance(result, str)

    def test_same_image_same_hash(self):
        """Dezelfde afbeelding geeft altijd dezelfde hash."""
        from screen_verifier import hash_image
        img = _make_image(0)
        self.assertEqual(hash_image(img), hash_image(img))

    def test_different_images_different_hash(self):
        """Twee verschillende afbeeldingen geven verschillende hashes."""
        from screen_verifier import hash_image
        self.assertNotEqual(hash_image(_make_image(0)), hash_image(_make_image(1)))

    def test_hash_is_sha256_hex(self):
        """Hash is een 64-karakter hex-string (SHA-256)."""
        from screen_verifier import hash_image
        result = hash_image(_make_image())
        self.assertEqual(len(result), 64)
        int(result, 16)  # gooit ValueError als het geen geldige hex is


class TestVerify(unittest.TestCase):
    """Tests voor verify()."""

    def test_returns_true_when_hash_matches(self):
        """verify() geeft True als het scherm overeenkomt met de opgeslagen hash."""
        from screen_verifier import verify, hash_image
        img = _make_image(0)
        screens = {"home": hash_image(img)}
        self.assertTrue(verify(img, "home", screens))

    def test_returns_false_when_screen_id_unknown(self):
        """verify() geeft False als screen_id niet in screens staat."""
        from screen_verifier import verify
        self.assertFalse(verify(_make_image(), "onbekend", {}))

    def test_returns_false_when_hash_differs(self):
        """verify() geeft False als de hash niet overeenkomt."""
        from screen_verifier import verify
        img_a = _make_image(0)
        img_b = _make_image(1)
        screens = {"home": "aabbccdd" * 8}  # foute hash, 64 chars
        self.assertFalse(verify(img_b, "home", screens))

    def test_screens_dict_unchanged_after_verify(self):
        """verify() wijzigt het screens-woordenboek niet."""
        from screen_verifier import verify, hash_image
        img = _make_image()
        screens = {"home": hash_image(img)}
        original = dict(screens)
        verify(img, "home", screens)
        self.assertEqual(screens, original)


if __name__ == "__main__":
    unittest.main()
