"""Tests voor controller.py — orchestratie van curtailment per inverter.

Alle I/O (config-laden, adapters, state_store) wordt gemockt zodat
de tests zonder netwerk of bestandssysteem kunnen draaien.
"""

import os
import unittest
from unittest.mock import MagicMock, call, patch

# Minimale inverter-configuratie voor gebruik in tests
_INVERTERS = {
    "steca": {
        "name": "StecaGrid 2500",
        "ip": "192.168.178.6",
        "nominal_watts": 2500,
        "min_watts": 500,
        "step_size": 100,
        "button_delay_ms": 0,
        "service_button_long": False,
    },
    "kostal": {
        "name": "Kostal Piko 4.2 MP",
        "ip": "192.168.178.5",
        "nominal_watts": 4200,
        "min_watts": 500,
        "step_size": 100,
        "button_delay_ms": 0,
        "service_button_long": True,
    },
}
_ACTIONS: dict = {}
_SCREENS: dict = {}


def _patch_load_config(test_case):
    """Patch _load_config zodat het de test-inverters teruggeeft."""
    return patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS))


# ---------------------------------------------------------------------------
# _desired_state
# ---------------------------------------------------------------------------

class TestDesiredState(unittest.TestCase):
    """_desired_state() bepaalt de gewenste staat op basis van de prijs."""

    def test_negative_price_returns_limited(self):
        from controller import _desired_state
        self.assertEqual(_desired_state(-0.001), "limited")

    def test_zero_price_returns_normal(self):
        from controller import _desired_state
        self.assertEqual(_desired_state(0.0), "normal")

    def test_positive_price_returns_normal(self):
        from controller import _desired_state
        self.assertEqual(_desired_state(0.05), "normal")


# ---------------------------------------------------------------------------
# run() — idempotentie
# ---------------------------------------------------------------------------

class TestRunIdempotent(unittest.TestCase):
    """Inverter wordt overgeslagen als hij al in de gewenste staat is."""

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=-0.01)
    def test_skips_when_already_limited(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "limited"
        with _patch_load_config(self), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:
            import controller
            controller.run()
            mock_steca.apply.assert_not_called()
            mock_kostal.apply.assert_not_called()

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=0.05)
    def test_skips_when_already_normal(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "normal"
        with _patch_load_config(self), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:
            import controller
            controller.run()
            mock_steca.apply.assert_not_called()
            mock_kostal.apply.assert_not_called()


# ---------------------------------------------------------------------------
# run() — toepassen van nieuwe staat
# ---------------------------------------------------------------------------

class TestRunAppliesState(unittest.TestCase):
    """run() roept adapter.apply() aan als de staat moet wisselen."""

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=-0.01)
    def test_applies_limited_to_both_inverters(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "normal"
        with _patch_load_config(self), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:
            import controller
            controller.run()
            mock_steca.apply.assert_called_once_with(
                "limited", "192.168.178.6", _INVERTERS["steca"], _ACTIONS, _SCREENS
            )
            mock_kostal.apply.assert_called_once_with(
                "limited", "192.168.178.5", _INVERTERS["kostal"], _ACTIONS, _SCREENS
            )

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=0.05)
    def test_applies_normal_to_both_inverters(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "limited"
        with _patch_load_config(self), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:
            import controller
            controller.run()
            mock_steca.apply.assert_called_once_with(
                "normal", "192.168.178.6", _INVERTERS["steca"], _ACTIONS, _SCREENS
            )
            mock_kostal.apply.assert_called_once_with(
                "normal", "192.168.178.5", _INVERTERS["kostal"], _ACTIONS, _SCREENS
            )


# ---------------------------------------------------------------------------
# run() — state bijwerken na succes
# ---------------------------------------------------------------------------

class TestRunUpdatesStateOnSuccess(unittest.TestCase):
    """Bij succes: set_state() wordt aangeroepen en alarm gewist."""

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=-0.01)
    def test_sets_state_for_both_inverters(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "normal"
        with _patch_load_config(self), \
             patch("controller.steca_adapter"), \
             patch("controller.kostal_adapter"):
            import controller
            controller.run()
            set_calls = [c[0][0] for c in mock_store.set_state.call_args_list]
            self.assertIn("steca", set_calls)
            self.assertIn("kostal", set_calls)
            for c in mock_store.set_state.call_args_list:
                self.assertEqual(c[0][1], "limited")

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=-0.01)
    def test_clears_alarm_on_success(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "normal"
        with _patch_load_config(self), \
             patch("controller.steca_adapter"), \
             patch("controller.kostal_adapter"):
            import controller
            controller.run()
            self.assertTrue(mock_store.clear_alarm.called)


# ---------------------------------------------------------------------------
# run() — failsafe bij adapterfout
# ---------------------------------------------------------------------------

class TestRunFailsafe(unittest.TestCase):
    """Bij adapterfout: alarm schrijven, state NIET bijwerken, andere inverter doorgaan."""

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=-0.01)
    def test_writes_alarm_when_adapter_raises(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "normal"
        with _patch_load_config(self), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter"):
            mock_steca.apply.side_effect = RuntimeError("netwerk fout")
            import controller
            controller.run()
            self.assertTrue(mock_store.write_alarm.called)
            alarm_msg = mock_store.write_alarm.call_args[0][0]
            self.assertIn("steca", alarm_msg)

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=-0.01)
    def test_does_not_update_state_when_adapter_raises(self, _mock_price, mock_store):
        mock_store.get_state.return_value = "normal"
        with _patch_load_config(self), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter"):
            mock_steca.apply.side_effect = RuntimeError("netwerk fout")
            import controller
            controller.run()
            set_calls = [c[0][0] for c in mock_store.set_state.call_args_list]
            self.assertNotIn("steca", set_calls)

    @patch("controller.state_store")
    @patch("controller._get_current_price", return_value=-0.01)
    def test_continues_with_other_inverter_on_error(self, _mock_price, mock_store):
        """Als steca mislukt, probeert de controller kostal nog steeds."""
        mock_store.get_state.return_value = "normal"
        with _patch_load_config(self), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:
            mock_steca.apply.side_effect = RuntimeError("steca fout")
            import controller
            controller.run()
            mock_kostal.apply.assert_called_once()


# ---------------------------------------------------------------------------
# _get_current_price() — FAKE_PRICE env-var
# ---------------------------------------------------------------------------

class TestGetCurrentPriceFakeEnv(unittest.TestCase):
    """FAKE_PRICE env-var bypast de echte API-aanroep."""

    def test_returns_fake_price_when_env_set(self):
        with patch.dict(os.environ, {"FAKE_PRICE": "-0.0023"}), \
             patch("controller.price_fetcher") as mock_fetcher:
            from controller import _get_current_price
            result = _get_current_price()
            self.assertAlmostEqual(result, -0.0023, places=5)
            mock_fetcher.fetch_current_price.assert_not_called()

    def test_calls_api_when_no_fake_env(self):
        env_without_fake = {k: v for k, v in os.environ.items() if k != "FAKE_PRICE"}
        with patch.dict(os.environ, env_without_fake, clear=True), \
             patch("controller.price_fetcher") as mock_fetcher:
            mock_fetcher.fetch_current_price.return_value = 0.05
            from controller import _get_current_price
            result = _get_current_price()
            mock_fetcher.fetch_current_price.assert_called_once()
            self.assertAlmostEqual(result, 0.05, places=5)


if __name__ == "__main__":
    unittest.main()
