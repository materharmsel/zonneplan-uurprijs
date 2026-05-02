"""Tests voor inverter_client — low-level HTTP-laag (twee URL-stijlen)."""

import io
import unittest
from unittest.mock import patch, MagicMock

from PIL import Image


class TestPressNew(unittest.TestCase):
    """Tests voor de 'new' API-stijl (Steca: page.main.html)."""

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_short_press_single_get(self, mock_sleep, mock_get):
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.6", "ESC", duration="short", api_style="new")

        self.assertEqual(mock_get.call_count, 1)
        url = mock_get.call_args_list[0][0][0]
        self.assertIn("192.168.178.6", url)
        self.assertIn("/page.main.html", url)
        self.assertIn("BUTTON_PRESSED=ESC", url)

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_long_set_becomes_longset(self, mock_sleep, mock_get):
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.6", "SET", duration="long", api_style="new")

        url = mock_get.call_args_list[0][0][0]
        self.assertIn("BUTTON_PRESSED=LONGSET", url)


class TestPressLegacy(unittest.TestCase):
    """Tests voor de 'legacy' API-stijl (Kostal Piko: buttons.html)."""

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_short_press_sends_clicked_then_released(self, mock_sleep, mock_get):
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.5", "ESC", duration="short", api_style="legacy")

        calls = mock_get.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertIn("/buttons.html", calls[0][0][0])
        self.assertIn("BUTTON=ESC", calls[0][0][0])
        self.assertIn("EVENT=clicked", calls[0][0][0])
        self.assertIn("EVENT=released", calls[1][0][0])

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_long_press_sends_clicked_long_released(self, mock_sleep, mock_get):
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.5", "BOTHMIDDLE", duration="long", api_style="legacy")

        calls = mock_get.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertIn("EVENT=clicked", calls[0][0][0])
        self.assertIn("EVENT=long", calls[1][0][0])
        self.assertIn("EVENT=released", calls[2][0][0])

    @patch("inverter_client.requests.get")
    @patch("inverter_client.time.sleep")
    def test_legacy_sleeps_between_events(self, mock_sleep, mock_get):
        from inverter_client import press

        mock_get.return_value.raise_for_status = MagicMock()
        press("192.168.178.5", "SET", duration="short", delay_ms=200, api_style="legacy")

        self.assertEqual(mock_sleep.call_count, 2)
        for c in mock_sleep.call_args_list:
            self.assertAlmostEqual(c[0][0], 0.2)


class TestPressUnknownStyle(unittest.TestCase):

    def test_unknown_api_style_raises(self):
        from inverter_client import press

        with self.assertRaises(ValueError):
            press("192.168.178.6", "ESC", api_style="bogus")


class TestGetScreen(unittest.TestCase):

    @patch("inverter_client.requests.get")
    def test_get_screen_returns_pil_image(self, mock_get):
        from inverter_client import get_screen

        img = Image.new("1", (256, 128), color=0)
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        mock_get.return_value.content = buf.getvalue()
        mock_get.return_value.raise_for_status = MagicMock()

        result = get_screen("192.168.178.6")

        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (256, 128))

    @patch("inverter_client.requests.get")
    def test_get_screen_calls_correct_url(self, mock_get):
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
        from inverter_client import get_screen
        import requests as req

        mock_get.return_value.raise_for_status.side_effect = req.HTTPError("404")

        with self.assertRaises(req.HTTPError):
            get_screen("192.168.178.6")


if __name__ == "__main__":
    unittest.main()
