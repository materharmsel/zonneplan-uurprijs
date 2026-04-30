"""Tests voor steca_adapter en kostal_adapter.

Beide adapters delen dezelfde boundary-detectie-logica. Verschil zit in de
inverter-config (service_button_long, nominal_watts, step_size).
"""

import unittest
from unittest.mock import MagicMock, patch

STECA_CFG = {
    "id": "steca",
    "nominal_watts": 2500,
    "min_watts": 500,
    "step_size": 10,
    "button_delay_ms": 0,
    "value_step_delay_ms": 0,
    "screenshot_settle_ms": 0,
    "service_button_long": False,
}

KOSTAL_CFG = {
    "id": "kostal",
    "nominal_watts": 4200,
    "min_watts": 500,
    "step_size": 100,
    "button_delay_ms": 0,
    "value_step_delay_ms": 0,
    "screenshot_settle_ms": 0,
    "service_button_long": True,
}

ACTIONS = {}  # niet relevant voor unit-tests; menu_engine wordt gemockt
SCREENS = {}  # idem; screen_verifier wordt gemockt

IP_STECA = "192.168.178.6"
IP_KOSTAL = "192.168.178.5"


# ---------------------------------------------------------------------------
# Steca-adapter
# ---------------------------------------------------------------------------

class TestStecaBoundaryDetection(unittest.TestCase):
    """Boundary-detectie-pad: 0 of 1 knopdruk afhankelijk van huidige scherm."""

    @patch("steca_adapter.screen_verifier")
    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_limited_when_already_at_min_does_zero_presses(
        self, mock_engine, mock_client, mock_verifier
    ):
        """Als de inverter al op power_limit_value_min staat: geen knopdruk, alleen confirm."""
        mock_verifier.identify.return_value = "power_limit_value_min"
        from steca_adapter import apply

        apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        self.assertEqual(mock_client.press.call_count, 0)
        action_names = [c[0][0] for c in mock_engine.run_action.call_args_list]
        self.assertEqual(
            action_names,
            ["navigate_to_power_limit_edit", "confirm_power_limit_edit"],
        )

    @patch("steca_adapter.screen_verifier")
    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_limited_when_at_max_does_one_down_and_confirms(
        self, mock_engine, mock_client, mock_verifier
    ):
        """Op max-boundary: 1× DOWN-wrap → verify min → confirm."""
        # Eerste identify-call: op max. Tweede (na DOWN): op min.
        mock_verifier.identify.side_effect = [
            "power_limit_value_max",
            "power_limit_value_min",
        ]
        from steca_adapter import apply

        apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        self.assertEqual(mock_client.press.call_count, 1)
        button_arg = mock_client.press.call_args_list[0][0][1]
        self.assertEqual(button_arg, "DOWN")

    @patch("steca_adapter.screen_verifier")
    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_normal_when_at_min_does_one_up_and_confirms(
        self, mock_engine, mock_client, mock_verifier
    ):
        """Op min-boundary, doel normal: 1× UP-wrap → verify max → confirm."""
        mock_verifier.identify.side_effect = [
            "power_limit_value_min",
            "power_limit_value_max",
        ]
        from steca_adapter import apply

        apply("normal", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        self.assertEqual(mock_client.press.call_count, 1)
        button_arg = mock_client.press.call_args_list[0][0][1]
        self.assertEqual(button_arg, "UP")

    @patch("steca_adapter.screen_verifier")
    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_normal_when_already_at_max_does_zero_presses(
        self, mock_engine, mock_client, mock_verifier
    ):
        mock_verifier.identify.return_value = "power_limit_value_max"
        from steca_adapter import apply

        apply("normal", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        self.assertEqual(mock_client.press.call_count, 0)


class TestStecaUnknownPosition(unittest.TestCase):
    """Bij tussenwaarde mag er GEEN sweep gebeuren — alleen alarm."""

    @patch("steca_adapter.screen_verifier")
    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_unknown_screen_raises_unknown_position_error(
        self, mock_engine, mock_client, mock_verifier
    ):
        from steca_adapter import apply, UnknownPositionError

        mock_verifier.identify.return_value = None  # geen boundary-match

        with self.assertRaises(UnknownPositionError):
            apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)

        # Geen waarde-knoppen ingedrukt
        self.assertEqual(mock_client.press.call_count, 0)
        # confirm wordt NIET aangeroepen
        action_names = [c[0][0] for c in mock_engine.run_action.call_args_list]
        self.assertNotIn("confirm_power_limit_edit", action_names)


class TestStecaWrapVerification(unittest.TestCase):
    """Als de wrap-tap niet op het verwachte scherm landt, moet adapter falen."""

    @patch("steca_adapter.screen_verifier")
    @patch("steca_adapter.inverter_client")
    @patch("steca_adapter.menu_engine")
    def test_wrap_landing_mismatch_raises_runtime_error(
        self, mock_engine, mock_client, mock_verifier
    ):
        # Start op max, maar na DOWN landen we niet op min (firmware-issue).
        mock_verifier.identify.side_effect = [
            "power_limit_value_max",
            None,  # onbekend na wrap
        ]
        from steca_adapter import apply

        with self.assertRaises(RuntimeError):
            apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)


class TestStecaErrorPropagation(unittest.TestCase):
    """VerifyError van menu_engine.navigate wordt niet afgevangen."""

    @patch("steca_adapter.menu_engine")
    def test_verify_error_propagates(self, mock_engine):
        from steca_adapter import apply
        from menu_engine import VerifyError

        mock_engine.run_action.side_effect = VerifyError("scherm onbekend")

        with self.assertRaises(VerifyError):
            apply("limited", IP_STECA, STECA_CFG, ACTIONS, SCREENS)


# ---------------------------------------------------------------------------
# Kostal-adapter (identieke logica, andere config)
# ---------------------------------------------------------------------------

class TestKostalBoundaryDetection(unittest.TestCase):

    @patch("kostal_adapter.screen_verifier")
    @patch("kostal_adapter.inverter_client")
    @patch("kostal_adapter.menu_engine")
    def test_limited_at_max_does_one_down(
        self, mock_engine, mock_client, mock_verifier
    ):
        mock_verifier.identify.side_effect = [
            "power_limit_value_max",
            "power_limit_value_min",
        ]
        from kostal_adapter import apply

        apply("limited", IP_KOSTAL, KOSTAL_CFG, ACTIONS, SCREENS)

        self.assertEqual(mock_client.press.call_count, 1)
        self.assertEqual(mock_client.press.call_args_list[0][0][1], "DOWN")

    @patch("kostal_adapter.screen_verifier")
    @patch("kostal_adapter.inverter_client")
    @patch("kostal_adapter.menu_engine")
    def test_unknown_position_raises(self, mock_engine, mock_client, mock_verifier):
        from kostal_adapter import apply, UnknownPositionError

        mock_verifier.identify.return_value = None

        with self.assertRaises(UnknownPositionError):
            apply("limited", IP_KOSTAL, KOSTAL_CFG, ACTIONS, SCREENS)

    @patch("kostal_adapter.menu_engine")
    def test_verify_error_propagates(self, mock_engine):
        from kostal_adapter import apply
        from menu_engine import VerifyError

        mock_engine.run_action.side_effect = VerifyError("scherm onbekend")

        with self.assertRaises(VerifyError):
            apply("limited", IP_KOSTAL, KOSTAL_CFG, ACTIONS, SCREENS)


if __name__ == "__main__":
    unittest.main()
