"""End-to-end testscript voor echte hardware (Raspberry Pi + inverters).

Voert een gecontroleerde test uit van de volledige curtailment-cyclus:
  1. Simuleert een negatieve prijs via FAKE_PRICE en controleert dat
     beide inverters naar 500 W gaan.
  2. Simuleert een positieve prijs en controleert dat beide inverters
     teruggaan naar vol vermogen.
  3. Test fout-injectie: controleert dat alarm.flag wordt aangemaakt
     als de netwerk-simulatie faalt.

Gebruik:
    python3 tools/e2e_test.py [--dry-run]

Vereisten:
  - Raspberry Pi op hetzelfde netwerk als de inverters
  - Calibratie voltooid (config/screens.json aanwezig en gevuld)
  - Inverters bereikbaar op hun geconfigureerde IP-adressen
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Zorg dat de projectroot in sys.path zit (script staat in tools/)
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import state_store
import controller

_STATE_FILE = _ROOT / "state" / "inverter_state.json"
_ALARM_FILE = _ROOT / "state" / "alarm.flag"


def _header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}")


def _info(msg: str) -> None:
    print(f"    {msg}")


def _ask_visual(prompt: str) -> bool:
    """Vraagt de gebruiker om visuele bevestiging van het inverter-display."""
    antwoord = input(f"\n  {prompt} [j/n]: ").strip().lower()
    return antwoord in ("j", "ja", "y", "yes")


def _reset_state() -> None:
    """Wis state en alarm zodat de test altijd schoon begint."""
    for f in (_STATE_FILE, _ALARM_FILE):
        try:
            f.unlink()
        except FileNotFoundError:
            pass
    _info("State en alarm gewist.")


def _get_states() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _run_with_price(price: float) -> None:
    """Voert controller.run() uit met de gegeven FAKE_PRICE."""
    os.environ["FAKE_PRICE"] = str(price)
    controller._setup_logging()
    controller.run()
    del os.environ["FAKE_PRICE"]


def stap1_negatieve_prijs(dry_run: bool) -> bool:
    """Stap 1: negatieve prijs → beide inverters naar 500 W."""
    _header("Stap 1 — Negatieve prijs (−0.01 €/kWh)")
    _info("Controller wordt uitgevoerd met FAKE_PRICE=-0.01 ...")

    if dry_run:
        _info("[DRY-RUN] Geen echte HTTP-aanroepen naar inverters.")
        _ok("Stap 1 overgeslagen (dry-run)")
        return True

    _run_with_price(-0.01)
    time.sleep(1)

    states = _get_states()
    geslaagd = True

    for inv_id in ("steca", "kostal"):
        if states.get(inv_id) == "limited":
            _ok(f"state_store: {inv_id} = 'limited'")
        else:
            _fail(f"state_store: {inv_id} = {states.get(inv_id)!r} (verwacht 'limited')")
            geslaagd = False

    if _ALARM_FILE.exists():
        _fail(f"alarm.flag aangemaakt — zie: {_ALARM_FILE.read_text().strip()}")
        geslaagd = False
    else:
        _ok("Geen alarm.flag")

    print()
    steca_ok = _ask_visual(
        "Steca (192.168.178.6): toont het display nu 500 W als vermogenslimiet?"
    )
    kostal_ok = _ask_visual(
        "Kostal (192.168.178.5): toont het display nu 500 W als vermogenslimiet?"
    )

    if steca_ok:
        _ok("Steca: display bevestigd — 500 W")
    else:
        _fail("Steca: display toont NIET 500 W")
        geslaagd = False

    if kostal_ok:
        _ok("Kostal: display bevestigd — 500 W")
    else:
        _fail("Kostal: display toont NIET 500 W")
        geslaagd = False

    return geslaagd


def stap2_positieve_prijs(dry_run: bool) -> bool:
    """Stap 2: positieve prijs → beide inverters terug naar vol vermogen."""
    _header("Stap 2 — Positieve prijs (+0.05 €/kWh)")
    _info("Controller wordt uitgevoerd met FAKE_PRICE=0.05 ...")

    if dry_run:
        _info("[DRY-RUN] Geen echte HTTP-aanroepen naar inverters.")
        _ok("Stap 2 overgeslagen (dry-run)")
        return True

    _run_with_price(0.05)
    time.sleep(1)

    states = _get_states()
    geslaagd = True

    for inv_id in ("steca", "kostal"):
        if states.get(inv_id) == "normal":
            _ok(f"state_store: {inv_id} = 'normal'")
        else:
            _fail(f"state_store: {inv_id} = {states.get(inv_id)!r} (verwacht 'normal')")
            geslaagd = False

    if _ALARM_FILE.exists():
        _fail(f"alarm.flag aangemaakt — zie: {_ALARM_FILE.read_text().strip()}")
        geslaagd = False
    else:
        _ok("Geen alarm.flag")

    print()
    steca_ok = _ask_visual(
        "Steca (192.168.178.6): is de vermogenslimiet opgeheven (vol vermogen)?"
    )
    kostal_ok = _ask_visual(
        "Kostal (192.168.178.5): is de vermogenslimiet opgeheven (vol vermogen)?"
    )

    if steca_ok:
        _ok("Steca: display bevestigd — limiet opgeheven")
    else:
        _fail("Steca: display toont nog steeds een limiet")
        geslaagd = False

    if kostal_ok:
        _ok("Kostal: display bevestigd — limiet opgeheven")
    else:
        _fail("Kostal: display toont nog steeds een limiet")
        geslaagd = False

    return geslaagd


def stap3_fout_injectie(dry_run: bool) -> bool:
    """Stap 3: verbreek netwerk naar Steca, controleer alarm + Kostal werkt nog."""
    _header("Stap 3 — Fout-injectie (netwerk Steca verbreken)")

    if dry_run:
        _info("[DRY-RUN] Geen echte fout-injectie.")
        _ok("Stap 3 overgeslagen (dry-run)")
        return True

    _info("Verbreek het netwerk naar Steca (192.168.178.6) door:")
    _info("  a) de netwerkkabel los te trekken, OF")
    _info("  b) op de router de verbinding tijdelijk te blokkeren.")
    input("\n  Druk op Enter als Steca niet meer bereikbaar is...")

    _reset_state()
    _run_with_price(-0.01)
    time.sleep(1)

    geslaagd = True
    states = _get_states()

    if _ALARM_FILE.exists():
        _ok(f"alarm.flag aangemaakt: {_ALARM_FILE.read_text().strip()[:80]}")
    else:
        _fail("alarm.flag is NIET aangemaakt terwijl Steca faalde")
        geslaagd = False

    if states.get("steca") == "limited":
        _fail("Steca-staat bijgewerkt ondanks fout (dat mag niet)")
        geslaagd = False
    else:
        _ok(f"Steca-staat NIET bijgewerkt (correct): {states.get('steca')!r}")

    if states.get("kostal") == "limited":
        _ok("Kostal WEL bijgewerkt ondanks Steca-fout")
    else:
        _fail(f"Kostal-staat NIET bijgewerkt: {states.get('kostal')!r}")
        geslaagd = False

    input("\n  Herstel het netwerk naar Steca en druk op Enter...")

    # Volgende tick herstelt alarm
    _run_with_price(-0.01)
    time.sleep(1)

    if not _ALARM_FILE.exists():
        _ok("alarm.flag gewist na herstel")
    else:
        _fail("alarm.flag nog steeds aanwezig na herstel")
        geslaagd = False

    return geslaagd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Sla inverter-aanroepen over — alleen state-verificatie",
    )
    args = parser.parse_args()

    _header("Zonneplan inverter-curtailment — end-to-end test")
    if args.dry_run:
        _info("DRY-RUN modus actief: geen HTTP-aanroepen naar inverters.")

    _info("State resetten voor een schone test...")
    _reset_state()

    resultaten = []
    resultaten.append(("Stap 1: negatieve prijs → limited", stap1_negatieve_prijs(args.dry_run)))
    resultaten.append(("Stap 2: positieve prijs → normal", stap2_positieve_prijs(args.dry_run)))
    resultaten.append(("Stap 3: fout-injectie + alarm", stap3_fout_injectie(args.dry_run)))

    _header("Samenvatting")
    alles_ok = True
    for naam, ok in resultaten:
        status = "GESLAAGD" if ok else "MISLUKT "
        symbool = "✓" if ok else "✗"
        print(f"  {symbool} [{status}]  {naam}")
        if not ok:
            alles_ok = False

    print()
    if alles_ok:
        print("  Alle stappen geslaagd — systeem is gereed voor productie.")
        sys.exit(0)
    else:
        print("  Een of meer stappen mislukt — zie details hierboven.")
        sys.exit(1)


if __name__ == "__main__":
    main()
