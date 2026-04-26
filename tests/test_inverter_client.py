"""Tests voor inverter_client — low-level HTTP-laag."""

import io
import unittest
from unittest.mock import patch, call, MagicMock

from PIL import Image


class TestPress(unittest.TestCase):
    """Tests voor de press()-functie."""

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_short_press_sends_clicked_then_released(self, mock_sleep, mock_get):
        """Korte druk stuurt: clicked, dan released."""
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.6", "ESC", duration="short")

        calls = mock_get.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertIn("EVENT=clicked", calls[0][0][0])
        self.assertIn("BUTTON=ESC", calls[0][0][0])
        self.assertIn("EVENT=released", calls[1][0][0])
        self.assertIn("BUTTON=ESC", calls[1][0][0])

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_long_press_sends_clicked_long_released(self, mock_sleep, mock_get):
        """Lange druk stuurt: clicked, long, dan released."""
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.6", "BOTHMIDDLE", duration="long")

        calls = mock_get.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertIn("EVENT=clicked", calls[0][0][0])
        self.assertIn("EVENT=long", calls[1][0][0])
        self.assertIn("EVENT=released", calls[2][0][0])

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_press_uses_correct_ip_and_path(self, mock_sleep, mock_get):
        """URL bevat het opgegeven IP-adres."""
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.5", "UP", duration="short")

        for c in mock_get.call_args_list:
            url = c[0][0]
            self.assertIn("192.168.178.5", url)
            self.assertIn("/buttons.html", url)

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_press_sleeps_between_events(self, mock_sleep, mock_get):
        """Er wordt gewacht tussen events (delay_ms)."""
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.6", "SET", duration="short", delay_ms=200)

        # 2 HTTP calls → 2 sleeps van 0.2 s
        self.assertEqual(mock_sleep.call_count, 2)
        for c in mock_sleep.call_args_list:
            self.assertAlmostEqual(c[0][0], 0.2)

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_press_default_duration_is_short(self, mock_sleep, mock_get):
        """Standaard duration is 'short' (2 HTTP-calls)."""
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.6", "DOWN")

        self.assertEqual(mock_get.call_count, 2)


class TestGetScreen(unittest.TestCase):
    """Tests voor de get_screen()-functie."""

    @patch("inverter_client.requests.get")
    def test_get_screen_returns_pil_image(self, mock_get):
        """get_screen() retourneert een PIL Image."""
        from inverter_client import get_screen

        # Maak een minimaal geldig BMP-bestand in-memory
        img = Image.new("1", (256, 128), color=0)
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        bmp_bytes = buf.getvalue()

        mock_get.return_value.content = bmp_bytes
        mock_get.return_value.raise_for_status = MagicMock()

        result = get_screen("192.168.178.6")

        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (256, 128))

    @patch("inverter_client.requests.get")
    def test_get_screen_calls_correct_url(self, mock_get):
        """get_screen() roept /gen.screenshot.bmp aan op het opgegeven IP."""
        from inverter_client import get_screen

        img = Image.new("1", (256, 128))
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        mock_get.return_value.content = buf.getvalue()
        mock_get.return_value.raise_for_status = MagicMock()

        get_screen("192.168.178.5")

        url = mock_get.call_args[0][0]
        self.assertIn("192.168.178.5", url)
        self.assertIn("/gen.screenshot.bmp", url)

    @patch("inverter_client.requests.get")
    def test_get_screen_raises_on_http_error(self, mock_get):
        """get_screen() gooit een exception bij een HTTP-fout."""
        from inverter_client import get_screen
        import requests as req

        mock_get.return_value.raise_for_status.side_effect = req.HTTPError("404")

        with self.assertRaises(req.HTTPError):
            get_screen("192.168.178.6")


if __name__ == "__main__":
    unittest.main()
