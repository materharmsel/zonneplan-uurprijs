"""Tests voor fetch_current_price() — haalt de uurprijs op voor het huidige uur."""

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Amsterdam")
except Exception:
    import datetime as _dt
    TZ = _dt.timezone(_dt.timedelta(hours=1))


def _entry(price_raw: int, offset_hours: int = 0) -> dict:
    """Bouw een API-entry voor huidig uur + offset_hours."""
    now = datetime.now(TZ)
    target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=offset_hours)
    return {"datetime": target.isoformat(), "electricity_price": price_raw}


class TestFetchCurrentPriceNoTokens(unittest.TestCase):
    """RuntimeError als er geen tokens zijn."""

    @patch("fetch_prices.load_tokens", return_value=None)
    def test_raises_when_no_tokens(self, _mock):
        from fetch_prices import fetch_current_price
        with self.assertRaises(RuntimeError):
            fetch_current_price()


class TestFetchCurrentPriceSuccess(unittest.TestCase):
    """Normale stroom: tokens aanwezig, prijs voor huidig uur beschikbaar."""

    def _setup(self, price_raw: int):
        """Patch alles zodat de API het opgegeven ruwe getal teruggeeft."""
        patcher_tokens = patch("fetch_prices.load_tokens", return_value={"access_token": "tok"})
        patcher_conn = patch("fetch_prices.get_electricity_connection", return_value="conn-uuid")
        patcher_fetch = patch(
            "fetch_prices.fetch_prices",
            return_value=[_entry(price_raw, 0), _entry(99999999, -1), _entry(99999999, 1)],
        )
        self._patches = [patcher_tokens, patcher_conn, patcher_fetch]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in getattr(self, "_patches", []):
            p.stop()

    def test_returns_correct_price_for_current_hour(self):
        """Geeft de prijs voor het huidige uur terug als float in EUR/kWh."""
        self._setup(price_raw=10_000_000)  # 10_000_000 × 0.0000001 = 1.0 EUR/kWh
        from fetch_prices import fetch_current_price
        result = fetch_current_price()
        self.assertAlmostEqual(result, 1.0, places=5)

    def test_returns_negative_price(self):
        """Negatieve prijzen worden correct teruggegeven."""
        self._setup(price_raw=-2_300)  # -2300 × 0.0000001 = -0.00023 EUR/kWh
        from fetch_prices import fetch_current_price
        result = fetch_current_price()
        self.assertLess(result, 0.0)

    def test_ignores_other_hours(self):
        """Slaat entries voor andere uren over."""
        self._setup(price_raw=5_000_000)
        from fetch_prices import fetch_current_price
        result = fetch_current_price()
        self.assertAlmostEqual(result, 0.5, places=5)


class TestFetchCurrentPriceTokenRefresh(unittest.TestCase):
    """Access-token verlopen → refresh + opnieuw proberen."""

    def test_refreshes_token_on_permission_error(self):
        raw_entry = [_entry(3_000_000, 0)]
        with patch("fetch_prices.load_tokens", return_value={"access_token": "old", "refresh_token": "ref"}), \
             patch("fetch_prices.refresh_access_token", return_value="new-tok") as mock_refresh, \
             patch("fetch_prices.get_electricity_connection", return_value="conn") as mock_conn, \
             patch("fetch_prices.fetch_prices", side_effect=[PermissionError("401"), raw_entry]) as mock_fp:
            # Eerste aanroep gooit PermissionError, tweede slaagt
            from fetch_prices import fetch_current_price
            result = fetch_current_price()
            mock_refresh.assert_called_once_with("ref")
            self.assertAlmostEqual(result, 0.3, places=5)


class TestFetchCurrentPriceNoEntryForCurrentHour(unittest.TestCase):
    """RuntimeError als er geen entry is voor het huidige uur."""

    def test_raises_when_no_entry_for_current_hour(self):
        with patch("fetch_prices.load_tokens", return_value={"access_token": "tok"}), \
             patch("fetch_prices.get_electricity_connection", return_value="conn"), \
             patch("fetch_prices.fetch_prices", return_value=[_entry(999, -5), _entry(999, 5)]):
            from fetch_prices import fetch_current_price
            with self.assertRaises(RuntimeError):
                fetch_current_price()


if __name__ == "__main__":
    unittest.main()
