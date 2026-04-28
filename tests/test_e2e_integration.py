"""End-to-end integratietests — volledige control-flow via FAKE_PRICE.

Verifieert de volledige orchestratie van prijs → desired_state → adapter →
state_store, met gemockte adapters en een echte (tijdelijke) state_store.
Geen netwerk of inverter-hardware vereist.
"""

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Minimale configuratie die controller._load_config() teruggeeft
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


def _real_state_store(tmp_dir: Path):
    """Geeft een state_store-achtig object dat schrijft naar tmp_dir."""
    import state_store as ss
    state_file = tmp_dir / "inverter_state.json"
    alarm_file = tmp_dir / "alarm.flag"

    class _Store:
        def get_state(self, inv_id):
            return ss.get_state(inv_id, path=state_file)

        def set_state(self, inv_id, state):
            ss.set_state(inv_id, state, path=state_file)

        def write_alarm(self, reason):
            ss.write_alarm(reason, path=alarm_file)

        def clear_alarm(self):
            ss.clear_alarm(path=alarm_file)

        @property
        def alarm_exists(self):
            return alarm_file.exists()

        def read_all_states(self) -> dict:
            try:
                return json.loads(state_file.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                return {}

    return _Store()


class TestE2ENegatievePrijs(unittest.TestCase):
    """Negatieve prijs → beide inverters worden 'limited'."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.store = _real_state_store(self.tmp_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_negatieve_prijs_stelt_beide_in_op_limited(self):
        with patch.dict(os.environ, {"FAKE_PRICE": "-0.0023"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:

            import controller
            controller.run()

        states = self.store.read_all_states()
        self.assertEqual(states.get("steca"), "limited")
        self.assertEqual(states.get("kostal"), "limited")
        mock_steca.apply.assert_called_once_with(
            "limited", "192.168.178.6", _INVERTERS["steca"], _ACTIONS, _SCREENS
        )
        mock_kostal.apply.assert_called_once_with(
            "limited", "192.168.178.5", _INVERTERS["kostal"], _ACTIONS, _SCREENS
        )

    def test_negatieve_prijs_wist_alarm(self):
        self.store.write_alarm("vorige fout")
        self.assertTrue(self.store.alarm_exists)

        with patch.dict(os.environ, {"FAKE_PRICE": "-0.01"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter"), \
             patch("controller.kostal_adapter"):

            import controller
            controller.run()

        self.assertFalse(self.store.alarm_exists)


class TestE2EPositievePrijs(unittest.TestCase):
    """Positieve prijs → beide inverters gaan terug naar 'normal'."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.store = _real_state_store(self.tmp_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_positieve_prijs_stelt_beide_in_op_normal(self):
        # Begin in 'limited'-staat
        self.store.set_state("steca", "limited")
        self.store.set_state("kostal", "limited")

        with patch.dict(os.environ, {"FAKE_PRICE": "0.05"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:

            import controller
            controller.run()

        states = self.store.read_all_states()
        self.assertEqual(states.get("steca"), "normal")
        self.assertEqual(states.get("kostal"), "normal")
        mock_steca.apply.assert_called_once_with(
            "normal", "192.168.178.6", _INVERTERS["steca"], _ACTIONS, _SCREENS
        )
        mock_kostal.apply.assert_called_once_with(
            "normal", "192.168.178.5", _INVERTERS["kostal"], _ACTIONS, _SCREENS
        )

    def test_nulprijs_wordt_normal(self):
        self.store.set_state("steca", "limited")
        self.store.set_state("kostal", "limited")

        with patch.dict(os.environ, {"FAKE_PRICE": "0.0"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:

            import controller
            controller.run()

        states = self.store.read_all_states()
        self.assertEqual(states.get("steca"), "normal")
        self.assertEqual(states.get("kostal"), "normal")


class TestE2EIdempotentie(unittest.TestCase):
    """Geen onnodige adapter-aanroepen als de staat al correct is."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.store = _real_state_store(self.tmp_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_geen_adapter_aanroep_als_al_limited(self):
        self.store.set_state("steca", "limited")
        self.store.set_state("kostal", "limited")

        with patch.dict(os.environ, {"FAKE_PRICE": "-0.01"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:

            import controller
            controller.run()

        mock_steca.apply.assert_not_called()
        mock_kostal.apply.assert_not_called()

    def test_twee_opeenvolgende_ticks_negatief_geen_dubbele_aanroep(self):
        """Tweede cron-tick mag adapters niet opnieuw aanroepen."""
        with patch.dict(os.environ, {"FAKE_PRICE": "-0.01"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:

            import controller
            controller.run()  # eerste tick — zet op limited
            controller.run()  # tweede tick — al limited, overgeslagen

        # Elke adapter mag maar één keer zijn aangeroepen
        self.assertEqual(mock_steca.apply.call_count, 1)
        self.assertEqual(mock_kostal.apply.call_count, 1)


class TestE2EFoutInjectie(unittest.TestCase):
    """Fout bij één inverter mag de andere niet blokkeren; alarm wordt gezet."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.store = _real_state_store(self.tmp_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_alarm_bij_steca_fout_en_kostal_doorgaan(self):
        with patch.dict(os.environ, {"FAKE_PRICE": "-0.01"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter") as mock_kostal:

            mock_steca.apply.side_effect = RuntimeError("netwerk fout")
            import controller
            controller.run()

        # Alarm gezet
        self.assertTrue(self.store.alarm_exists)
        # Steca-staat NIET bijgewerkt (fout)
        states = self.store.read_all_states()
        self.assertNotEqual(states.get("steca"), "limited")
        # Kostal WEL bijgewerkt (door)
        self.assertEqual(states.get("kostal"), "limited")
        mock_kostal.apply.assert_called_once()

    def test_volgende_tick_herstelt_na_fout(self):
        """Als steca in tweede tick slaagt, wordt alarm gewist."""
        with patch.dict(os.environ, {"FAKE_PRICE": "-0.01"}), \
             patch("controller._load_config", return_value=(_INVERTERS, _ACTIONS, _SCREENS)), \
             patch("controller.state_store", self.store), \
             patch("controller.steca_adapter") as mock_steca, \
             patch("controller.kostal_adapter"):

            # Eerste tick: steca mislukt
            mock_steca.apply.side_effect = RuntimeError("tijdelijk")
            import controller
            controller.run()
            self.assertTrue(self.store.alarm_exists)

            # Tweede tick: steca slaagt
            mock_steca.apply.side_effect = None
            controller.run()

        self.assertFalse(self.store.alarm_exists)


if __name__ == "__main__":
    unittest.main()
