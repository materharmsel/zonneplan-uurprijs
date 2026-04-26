"""Tests voor menu_engine — YAML-pad-uitvoerder met verify en auto-recovery."""

import io
import unittest
from unittest.mock import MagicMock, call, patch

from PIL import Image


def _make_image(color: int = 0) -> Image.Image:
    return Image.new("1", (256, 128), color=color)


# Minimale inverter-config (Steca, geen lange SERVICE)
STECA_CFG = {
    "button_delay_ms": 0,
    "service_button_long": False,
}

# Kostal-config (SERVICE lang indrukken)
KOSTAL_CFG = {
    "button_delay_ms": 0,
    "service_button_long": True,
}

# Minimale actions-dict (alleen go_home, en een test-actie)
ACTIONS_GO_HOME = {
    "go_home": {
        "steps": [{"button": "ESC", "repeat": 5}]
    }
}

ACTIONS_SIMPLE = {
    "go_home": {
        "steps": [{"button": "ESC", "repeat": 5}]
    },
    "one_set": {
        "steps": [{"button": "SET"}]
    },
    "down_three": {
        "steps": [{"button": "DOWN", "repeat": 3}]
    },
    "with_verify": {
        "steps": [
            {"button": "SET"},
            {"verify": "home"},
            {"button": "DOWN"},
        ]
    },
    "with_subaction": {
        "steps": [
            {"action": "go_home"},
            {"button": "SET"},
        ]
    },
    "service_press": {
        "steps": [{"button": "BOTHMIDDLE", "duration": "service"}]
    },
}


class TestGoHome(unittest.TestCase):
    """go_home drukt ESC exact 5 keer."""

    @patch("menu_engine.inverter_client")
    def test_go_home_presses_esc_five_times(self, mock_client):
        from menu_engine import run_action
        run_action("go_home", "192.168.178.6", STECA_CFG, ACTIONS_GO_HOME, {})
        self.assertEqual(mock_client.press.call_count, 5)
        for c in mock_client.press.call_args_list:
            self.assertEqual(c[0][1], "ESC")

    @patch("menu_engine.inverter_client")
    def test_go_home_uses_short_duration(self, mock_client):
        from menu_engine import run_action
        run_action("go_home", "192.168.178.6", STECA_CFG, ACTIONS_GO_HOME, {})
        for c in mock_client.press.call_args_list:
            self.assertEqual(c[1].get("duration", "short"), "short")


class TestRepeat(unittest.TestCase):
    """repeat: N drukt de knop precies N keer."""

    @patch("menu_engine.inverter_client")
    def test_repeat_three_calls_press_three_times(self, mock_client):
        from menu_engine import run_action
        run_action("down_three", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})
        self.assertEqual(mock_client.press.call_count, 3)
        for c in mock_client.press.call_args_list:
            self.assertEqual(c[0][1], "DOWN")

    @patch("menu_engine.inverter_client")
    def test_no_repeat_defaults_to_one(self, mock_client):
        from menu_engine import run_action
        run_action("one_set", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})
        self.assertEqual(mock_client.press.call_count, 1)


class TestServiceDuration(unittest.TestCase):
    """duration: service vertaalt naar short (Steca) of long (Kostal)."""

    @patch("menu_engine.inverter_client")
    def test_service_is_short_for_steca(self, mock_client):
        from menu_engine import run_action
        run_action("service_press", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})
        _, kwargs = mock_client.press.call_args
        self.assertEqual(kwargs.get("duration", "short"), "short")

    @patch("menu_engine.inverter_client")
    def test_service_is_long_for_kostal(self, mock_client):
        from menu_engine import run_action
        run_action("service_press", "192.168.178.5", KOSTAL_CFG, ACTIONS_SIMPLE, {})
        _, kwargs = mock_client.press.call_args
        self.assertEqual(kwargs.get("duration"), "long")


class TestVerifyStep(unittest.TestCase):
    """verify-stap: calls get_screen + screen_verifier.verify."""

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_verify_passes_when_hash_matches(self, mock_client, mock_verifier):
        """Geen exception bij overeenkomende hash; volgende stap wordt uitgevoerd."""
        from menu_engine import run_action
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.verify.return_value = True

        run_action("with_verify", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {"home": "abc"})

        mock_client.get_screen.assert_called_once()
        mock_verifier.verify.assert_called_once()
        # SET + DOWN moeten allebei uitgevoerd zijn
        buttons = [c[0][1] for c in mock_client.press.call_args_list]
        self.assertIn("SET", buttons)
        self.assertIn("DOWN", buttons)

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_verify_fail_raises_verify_error(self, mock_client, mock_verifier):
        """VerifyError wordt gegooid bij hash-mismatch."""
        from menu_engine import run_action, VerifyError
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.verify.return_value = False

        with self.assertRaises(VerifyError):
            run_action("with_verify", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_verify_fail_triggers_esc_recovery(self, mock_client, mock_verifier):
        """Bij hash-mismatch worden eerst 5× ESC gestuurd (recovery)."""
        from menu_engine import run_action, VerifyError
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.verify.return_value = False

        with self.assertRaises(VerifyError):
            run_action("with_verify", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})

        esc_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "ESC"]
        self.assertEqual(len(esc_calls), 5)

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_verify_fail_stops_further_steps(self, mock_client, mock_verifier):
        """Na een verify-fout worden geen verdere stappen uitgevoerd."""
        from menu_engine import run_action, VerifyError
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.verify.return_value = False

        with self.assertRaises(VerifyError):
            run_action("with_verify", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})

        # SET is voor de verify uitgevoerd, DOWN daarna NIET
        buttons = [c[0][1] for c in mock_client.press.call_args_list]
        self.assertNotIn("DOWN", buttons)


class TestSubAction(unittest.TestCase):
    """action: <naam> voert een geneste actie uit."""

    @patch("menu_engine.inverter_client")
    def test_sub_action_executes_go_home_then_set(self, mock_client):
        from menu_engine import run_action
        run_action("with_subaction", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})
        buttons = [c[0][1] for c in mock_client.press.call_args_list]
        # ESC×5 (go_home) gevolgd door SET
        self.assertEqual(buttons[:5], ["ESC"] * 5)
        self.assertEqual(buttons[5], "SET")


class TestDelayPropagation(unittest.TestCase):
    """button_delay_ms uit inverter_cfg wordt doorgegeven aan press()."""

    @patch("menu_engine.inverter_client")
    def test_delay_passed_to_press(self, mock_client):
        from menu_engine import run_action
        cfg = {"button_delay_ms": 250, "service_button_long": False}
        run_action("one_set", "192.168.178.6", cfg, ACTIONS_SIMPLE, {})
        _, kwargs = mock_client.press.call_args
        self.assertEqual(kwargs.get("delay_ms"), 250)


if __name__ == "__main__":
    unittest.main()
