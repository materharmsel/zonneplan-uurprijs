"""Tests voor calibrate.py helper-functies (niet-interactieve onderdelen)."""

import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from PIL import Image

# calibrate.py zit in tools/; voeg projectroot toe zodat de import werkt
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import calibrate


def _make_image(color: int = 0) -> Image.Image:
    """Hulpfunctie: maak een 256×128 monochroom PIL Image."""
    return Image.new("1", (256, 128), color=color)


class TestComputeHash(unittest.TestCase):
    """Tests voor compute_hash()."""

    def test_same_image_same_hash(self):
        """Dezelfde pixelinhoud geeft altijd dezelfde hash."""
        img = _make_image(0)
        self.assertEqual(calibrate.compute_hash(img), calibrate.compute_hash(img))

    def test_different_images_different_hash(self):
        """Beelden met andere pixels geven een andere hash."""
        img_black = _make_image(0)
        img_white = _make_image(1)
        self.assertNotEqual(
            calibrate.compute_hash(img_black),
            calibrate.compute_hash(img_white),
        )

    def test_hash_is_sha256_hex(self):
        """Hash is een geldige hex-string van 64 tekens (SHA-256)."""
        h = calibrate.compute_hash(_make_image(0))
        self.assertEqual(len(h), 64)
        int(h, 16)  # gooit ValueError als het geen hex is

    def test_hash_matches_manual_calculation(self):
        """Hash stemt overeen met een handmatig berekende SHA-256."""
        img = _make_image(0)
        expected = hashlib.sha256(img.tobytes()).hexdigest()
        self.assertEqual(calibrate.compute_hash(img), expected)


class TestPressSequence(unittest.TestCase):
    """Tests voor press_sequence()."""

    @patch("calibrate.inverter_client")
    def test_single_button_no_repeat(self, mock_client):
        """Één knop zonder repeat → precies één press()-aanroep."""
        calibrate.press_sequence("1.2.3.4", [{"button": "ESC"}])
        mock_client.press.assert_called_once_with(
            "1.2.3.4", "ESC", duration="short", delay_ms=300
        )

    @patch("calibrate.inverter_client")
    def test_repeat_generates_multiple_calls(self, mock_client):
        """repeat: 3 → drie press()-aanroepen."""
        calibrate.press_sequence("1.2.3.4", [{"button": "DOWN", "repeat": 3}])
        self.assertEqual(mock_client.press.call_count, 3)
        for c in mock_client.press.call_args_list:
            self.assertEqual(c[0][1], "DOWN")

    @patch("calibrate.inverter_client")
    def test_service_duration_short_when_not_long(self, mock_client):
        """duration='service' + service_long=False → duration='short'."""
        calibrate.press_sequence(
            "1.2.3.4",
            [{"button": "BOTHMIDDLE", "duration": "service"}],
            service_long=False,
        )
        mock_client.press.assert_called_once_with(
            "1.2.3.4", "BOTHMIDDLE", duration="short", delay_ms=300
        )

    @patch("calibrate.inverter_client")
    def test_service_duration_long_when_kostal(self, mock_client):
        """duration='service' + service_long=True → duration='long'."""
        calibrate.press_sequence(
            "1.2.3.4",
            [{"button": "BOTHMIDDLE", "duration": "service"}],
            service_long=True,
        )
        mock_client.press.assert_called_once_with(
            "1.2.3.4", "BOTHMIDDLE", duration="long", delay_ms=300
        )

    @patch("calibrate.inverter_client")
    def test_multiple_buttons_in_order(self, mock_client):
        """Meerdere knoppen worden in volgorde aangestuurd."""
        calibrate.press_sequence(
            "1.2.3.4",
            [{"button": "SET"}, {"button": "UP"}],
        )
        calls = mock_client.press.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0][1], "SET")
        self.assertEqual(calls[1][0][1], "UP")


class TestSaveScreens(unittest.TestCase):
    """Tests voor save_screens()."""

    def test_writes_valid_json(self):
        """save_screens() schrijft geldig JSON naar het opgegeven pad."""
        data = {"steca.home": "abc123", "kostal.home": "def456"}
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "screens.json"
            calibrate.save_screens(data, target)
            with open(target) as f:
                loaded = json.load(f)
        self.assertEqual(loaded, data)

    def test_atomic_write_replaces_existing(self):
        """save_screens() overschrijft een bestaand screens.json correct."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "screens.json"
            target.write_text('{"old": "value"}')
            calibrate.save_screens({"new": "value"}, target)
            with open(target) as f:
                loaded = json.load(f)
        self.assertEqual(loaded, {"new": "value"})

    def test_no_tmp_file_left_behind(self):
        """Na save_screens() blijft er geen .tmp-bestand achter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "screens.json"
            calibrate.save_screens({}, target)
            tmp = target.with_suffix(".tmp")
            self.assertFalse(tmp.exists())


if __name__ == "__main__":
    unittest.main()
