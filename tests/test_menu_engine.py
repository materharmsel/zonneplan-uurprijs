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

STECA_CFG_WITH_ID = {
    "id": "steca",
    "button_delay_ms": 0,
    "service_button_long": False,
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
    "with_settle": {
        "steps": [
            {"button": "SET"},
            {"settle_ms": 500},
            {"button": "DOWN"},
        ]
    },
    "with_expect": {
        "steps": [
            {"button": "SET", "expect": "home", "max_retries": 2},
        ]
    },
    "nav_with_resume": {
        "locate_resume": True,
        "steps": [
            {"button": "ESC", "repeat": 5},
            {"button": "SET", "expect": "instellingen", "max_retries": 2},
            {"button": "DOWN", "expect": "service_item", "max_retries": 2},
        ]
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


class TestSettleMs(unittest.TestCase):
    """settle_ms-stap wacht zonder knoppen in te drukken."""

    @patch("menu_engine.time")
    @patch("menu_engine.inverter_client")
    def test_settle_calls_sleep(self, mock_client, mock_time):
        from menu_engine import run_action
        run_action("with_settle", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})
        mock_time.sleep.assert_called_once_with(0.5)

    @patch("menu_engine.time")
    @patch("menu_engine.inverter_client")
    def test_settle_does_not_press_buttons(self, mock_client, mock_time):
        from menu_engine import run_action
        run_action("with_settle", "192.168.178.6", STECA_CFG, ACTIONS_SIMPLE, {})
        buttons = [c[0][1] for c in mock_client.press.call_args_list]
        self.assertEqual(buttons, ["SET", "DOWN"])


class TestExpectField(unittest.TestCase):
    """expect-veld op button-stap identificeert scherm en herprobeert indien nodig."""

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_expect_succeeds_on_first_check(self, mock_client, mock_verifier):
        """Geen extra persen als identify direct het verwachte scherm geeft."""
        from menu_engine import run_action
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.identify.return_value = "home"
        screens = {"steca.home": "abc"}

        run_action("with_expect", "192.168.178.6", STECA_CFG_WITH_ID, ACTIONS_SIMPLE, screens)

        set_presses = [c for c in mock_client.press.call_args_list if c[0][1] == "SET"]
        self.assertEqual(len(set_presses), 1)

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_expect_retries_on_wrong_screen(self, mock_client, mock_verifier):
        """Bij verkeerd scherm wordt de knop opnieuw ingedrukt."""
        from menu_engine import run_action
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.identify.side_effect = [None, "home"]
        screens = {"steca.home": "abc"}

        run_action("with_expect", "192.168.178.6", STECA_CFG_WITH_ID, ACTIONS_SIMPLE, screens)

        set_presses = [c for c in mock_client.press.call_args_list if c[0][1] == "SET"]
        self.assertEqual(len(set_presses), 2)

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_expect_raises_after_max_retries(self, mock_client, mock_verifier):
        """VerifyError na uitgeputte retries; ESC×5 recovery uitgevoerd."""
        from menu_engine import run_action, VerifyError
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.identify.return_value = None
        screens = {"steca.home": "abc"}

        with self.assertRaises(VerifyError):
            run_action("with_expect", "192.168.178.6", STECA_CFG_WITH_ID, ACTIONS_SIMPLE, screens)

        esc_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "ESC"]
        self.assertEqual(len(esc_calls), 5)

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_expect_skipped_when_screens_empty(self, mock_client, mock_verifier):
        """Als screens leeg is, wordt expect niet gecontroleerd."""
        from menu_engine import run_action
        run_action("with_expect", "192.168.178.6", STECA_CFG_WITH_ID, ACTIONS_SIMPLE, {})
        mock_verifier.identify.assert_not_called()


class TestLocateResume(unittest.TestCase):
    """locate_resume slaat stappen over als het huidige scherm al bekend is."""

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_resumes_from_known_screen(self, mock_client, mock_verifier):
        """Als we al op 'instellingen' staan, wordt ESC×5 overgeslagen."""
        from menu_engine import run_action
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.identify.side_effect = [
            "instellingen",  # locate_resume: huidige positie
            "service_item",  # expect-check voor DOWN-stap
        ]
        screens = {"steca.instellingen": "abc", "steca.service_item": "def"}

        run_action("nav_with_resume", "192.168.178.6", STECA_CFG_WITH_ID, ACTIONS_SIMPLE, screens)

        esc_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "ESC"]
        self.assertEqual(len(esc_calls), 0)

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_starts_from_beginning_when_screen_unknown(self, mock_client, mock_verifier):
        """Bij onbekend scherm (None) start de navigatie gewoon van voren af aan."""
        from menu_engine import run_action
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.identify.side_effect = [
            None,          # locate_resume: onbekende positie → start van begin
            "instellingen",  # expect-check na SET
            "service_item",  # expect-check na DOWN
        ]
        screens = {"steca.instellingen": "abc", "steca.service_item": "def"}

        run_action("nav_with_resume", "192.168.178.6", STECA_CFG_WITH_ID, ACTIONS_SIMPLE, screens)

        esc_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "ESC"]
        self.assertEqual(len(esc_calls), 5)

    @patch("menu_engine.screen_verifier")
    @patch("menu_engine.inverter_client")
    def test_locate_resume_skipped_when_screens_empty(self, mock_client, mock_verifier):
        """Als screens leeg is, wordt locate_resume niet uitgevoerd."""
        from menu_engine import run_action
        mock_client.get_screen.return_value = _make_image()
        mock_verifier.identify.return_value = "instellingen"

        run_action("nav_with_resume", "192.168.178.6", STECA_CFG_WITH_ID, ACTIONS_SIMPLE, {})

        mock_verifier.identify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
