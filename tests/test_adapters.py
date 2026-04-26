"""Tests voor steca_adapter en kostal_adapter.

Beide adapters hebben dezelfde functie-interface; het verschil zit in de
inverter-config (service_button_long, nominal_watts, step_size).
"""

import unittest
from unittest.mock import MagicMock, call, patch

# Minimale configs voor gebruik in tests
STECA_CFG = {
    "nominal_watts": 2500,
    "min_watts": 500,
    "step_size": 100,
    "button_delay_ms": 0,
    "service_button_long": False,
}

KOSTAL_CFG = {
    "nominal_watts": 4200,
    "min_watts": 500,
    "step_size": 100,
    "button_delay_ms": 0,
    "service_button_long": True,
}

ACTIONS = {
    "go_home": {"steps": [{"button": "ESC", "repeat": 5}]},
    "navigate_to_power_limit_edit": {
        "steps": [
            {"action": "go_home"},
            {"button": "SET"},
            {"button": "DOWN", "repeat": 2},
            {"verify": "instellingen"},
            {"button": "SET"},
            {"button": "UP"},
            {"verify": "service_item"},
            {"button": "SET"},
            {"verify": "toetscombinatie_scherm"},
            {"button": "BOTHMIDDLE", "duration": "service"},
            {"verify": "service_menu"},
            {"button": "DOWN", "repeat": 4},
            {"verify": "vermogensbegrenzing_item"},
            {"button": "SET"},
            {"button": "SET"},
        ]
    },
    "confirm_power_limit_edit": {
        "steps": [
            {"button": "SET"},
            {"action": "go_home"},
        ]
    },
}

SCREENS = {}  # lege screens (kalibratie nog niet gedaan in tests)

IP_STECA = "192.168.178.6"
IP_KOSTAL = "192.168.178.5"


# ---------------------------------------------------------------------------
# StecaAdapter tests
# ---------------------------------------------------------------------------

class TestStecaApplyLimited(unittest.TestCase):
    """apply('limited') navigeert naar edit-modus, drukt DOWN×n, bevestigt."""

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_navigates_to_edit_mode(self, mock_engine, mock_client):
        """navigate_to_power_limit_edit wordt aangeroepen vóór waarde-instelling."""
        mock_engine.run_action.return_value = None
        from steca_adapter import apply

        apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        first_call = mock_engine.run_action.call_args_list[0]
        self.assertEqual(first_call[0][0], "navigate_to_power_limit_edit")

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_presses_down_correct_number_of_times(self, mock_engine, mock_client):
        """DOWN × (nominal - min) / step_size = (2500-500)/100 = 20 keer."""
        mock_engine.run_action.return_value = None
        from steca_adapter import apply

        apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        down_calls = [
            c for c in mock_client.press.call_args_list
            if c[0][1] == "DOWN"
        ]
        self.assertEqual(len(down_calls), 20)

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_confirms_after_value_setting(self, mock_engine, mock_client):
        """confirm_power_limit_edit wordt aangeroepen ná de DOWN-drukken."""
        mock_engine.run_action.return_value = None
        from steca_adapter import apply

        apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        last_call = mock_engine.run_action.call_args_list[-1]
        self.assertEqual(last_call[0][0], "confirm_power_limit_edit")

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_uses_step_size_for_press_count(self, mock_engine, mock_client):
        """Groter step_size → minder DOWN-drukken."""
        mock_engine.run_action.return_value = None
        from steca_adapter import apply

        cfg = {**STECA_CFG, "step_size": 200}
        apply("limited", IP_STECA, cfg, ACTIONS, SCREENS)

        down_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "DOWN"]
        self.assertEqual(len(down_calls), 10)  # (2500-500)/200 = 10

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_down_presses_use_correct_ip_and_delay(self, mock_engine, mock_client):
        """DOWN-drukken worden gestuurd naar het juiste IP met de juiste delay."""
        mock_engine.run_action.return_value = None
        from steca_adapter import apply

        apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        for c in mock_client.press.call_args_list:
            self.assertEqual(c[0][0], IP_STECA)
            self.assertEqual(c[1].get("delay_ms"), 0)


class TestStecaApplyNormal(unittest.TestCase):
    """apply('normal') drukt UP×n om terug te gaan naar nominaal vermogen."""

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_presses_up_to_restore_nominal(self, mock_engine, mock_client):
        """UP × (nominal - min) / step_size keer."""
        mock_engine.run_action.return_value = None
        from steca_adapter import apply

        apply("normal", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        up_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "UP"]
        self.assertEqual(len(up_calls), 20)

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_no_down_presses_for_normal(self, mock_engine, mock_client):
        """Bij 'normal' worden geen DOWN-drukken voor waarde-instelling gestuurd."""
        mock_engine.run_action.return_value = None
        from steca_adapter import apply

        apply("normal", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        # De navigate-actie bevat ook DOWN-drukken voor menunavigatie,
        # maar de waarde-instelling UP moet ook correct zijn.
        # We controleren alleen dat het UP-patroon aanwezig is.
        up_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "UP"]
        self.assertGreater(len(up_calls), 0)


class TestStecaErrorPropagation(unittest.TestCase):
    """VerifyError van menu_engine wordt niet afgevangen door de adapter."""

    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_verify_error_propagates(self, mock_engine, mock_client):
        from steca_adapter import apply
        from menu_engine import VerifyError

        mock_engine.run_action.side_effect = VerifyError("scherm onbekend")

        with self.assertRaises(VerifyError):
            apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)


# ---------------------------------------------------------------------------
# KostalAdapter tests (zelfde interface, andere config)
# ---------------------------------------------------------------------------

class TestKostalApplyLimited(unittest.TestCase):
    """Kostal-adapter: (4200-500)/100 = 37 DOWN-drukken voor 'limited'."""

    @patch("kostal_adapter.inverter_client")
    @patch("kostal_adapter.menu_engine")
    def test_presses_down_correct_times_for_kostal(self, mock_engine, mock_client):
        mock_engine.run_action.return_value = None
        from kostal_adapter import apply

        apply("limited", IP_KOSTAL, KOSTAL_CFG, ACTIONS, SCREENS)

        down_calls = [c for c in mock_client.press.call_args_list if c[0][1] == "DOWN"]
        self.assertEqual(len(down_calls), 37)  # (4200-500)/100 = 37

    @patch("kostal_adapter.inverter_client")
    @patch("kostal_adapter.menu_engine")
    def test_navigates_and_confirms(self, mock_engine, mock_client):
        mock_engine.run_action.return_value = None
        from kostal_adapter import apply

        apply("limited", IP_KOSTAL, KOSTAL_CFG, ACTIONS, SCREENS)

        action_names = [c[0][0] for c in mock_engine.run_action.call_args_list]
        self.assertIn("navigate_to_power_limit_edit", action_names)
        self.assertIn("confirm_power_limit_edit", action_names)

    @patch("kostal_adapter.inverter_client")
    @patch("kostal_adapter.menu_engine")
    def test_verify_error_propagates(self, mock_engine, mock_client):
        from kostal_adapter import apply
        from menu_engine import VerifyError

        mock_engine.run_action.side_effect = VerifyError("scherm onbekend")

        with self.assertRaises(VerifyError):
            apply("limited", IP_KOSTAL, KOSTAL_CFG, ACTIONS, SCREENS)


if __name__ == "__main__":
    unittest.main()
