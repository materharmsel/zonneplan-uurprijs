"""Tests voor state_store — atomic JSON-state opslag per inverter."""

import json
import os
import tempfile
import unittest
from pathlib import Path


class TestGetState(unittest.TestCase):
    """get_state() leest de huidige staat voor een inverter."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = Path(self.tmp) / "inverter_state.json"

    def test_returns_none_when_file_missing(self):
        from state_store import get_state
        self.assertIsNone(get_state("steca", self.path))

    def test_returns_stored_value(self):
        from state_store import get_state
        self.path.write_text(json.dumps({"steca": "limited"}))
        self.assertEqual(get_state("steca", self.path), "limited")

    def test_returns_none_for_unknown_inverter(self):
        from state_store import get_state
        self.path.write_text(json.dumps({"steca": "limited"}))
        self.assertIsNone(get_state("kostal", self.path))

    def test_returns_none_on_corrupt_json(self):
        from state_store import get_state
        self.path.write_text("NIET GELDIG JSON")
        self.assertIsNone(get_state("steca", self.path))


class TestSetState(unittest.TestCase):
    """set_state() schrijft atomisch de nieuwe staat."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = Path(self.tmp) / "inverter_state.json"

    def test_creates_file_when_missing(self):
        from state_store import set_state
        set_state("steca", "limited", self.path)
        self.assertTrue(self.path.exists())

    def test_stored_value_is_readable(self):
        from state_store import set_state, get_state
        set_state("steca", "limited", self.path)
        self.assertEqual(get_state("steca", self.path), "limited")

    def test_overwrites_existing_value(self):
        from state_store import set_state, get_state
        set_state("steca", "limited", self.path)
        set_state("steca", "normal", self.path)
        self.assertEqual(get_state("steca", self.path), "normal")

    def test_preserves_other_inverters(self):
        from state_store import set_state, get_state
        set_state("kostal", "normal", self.path)
        set_state("steca", "limited", self.path)
        self.assertEqual(get_state("kostal", self.path), "normal")

    def test_write_is_atomic_no_tmp_left(self):
        """Na een succesvolle write mag er geen tmp-bestand achterblijven."""
        from state_store import set_state
        set_state("steca", "limited", self.path)
        tmp_files = list(Path(self.tmp).glob("*.tmp"))
        self.assertEqual(tmp_files, [])

    def test_file_contains_valid_json(self):
        from state_store import set_state
        set_state("steca", "limited", self.path)
        data = json.loads(self.path.read_text())
        self.assertIsInstance(data, dict)


class TestClearAlarm(unittest.TestCase):
    """clear_alarm() verwijdert alarm.flag als die bestaat."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.flag = Path(self.tmp) / "alarm.flag"

    def test_removes_existing_flag(self):
        from state_store import clear_alarm
        self.flag.write_text("fout")
        clear_alarm(self.flag)
        self.assertFalse(self.flag.exists())

    def test_does_not_raise_when_flag_missing(self):
        from state_store import clear_alarm
        clear_alarm(self.flag)  # mag geen exception gooien


class TestWriteAlarm(unittest.TestCase):
    """write_alarm() schrijft een alarm.flag met reden en timestamp."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.flag = Path(self.tmp) / "alarm.flag"

    def test_creates_alarm_flag(self):
        from state_store import write_alarm
        write_alarm("testfout", self.flag)
        self.assertTrue(self.flag.exists())

    def test_flag_contains_reason(self):
        from state_store import write_alarm
        write_alarm("negatieve prijs mislukt", self.flag)
        self.assertIn("negatieve prijs mislukt", self.flag.read_text())

    def test_flag_contains_timestamp(self):
        from state_store import write_alarm
        write_alarm("fout", self.flag)
        content = self.flag.read_text()
        # ISO 8601 timestamp begint altijd met een 4-cijferig jaar
        import re
        self.assertRegex(content, r"\d{4}-\d{2}-\d{2}")

    def test_overwrites_existing_flag(self):
        from state_store import write_alarm
        write_alarm("eerste fout", self.flag)
        write_alarm("tweede fout", self.flag)
        self.assertIn("tweede fout", self.flag.read_text())
        self.assertNotIn("eerste fout", self.flag.read_text())


if __name__ == "__main__":
    unittest.main()
