"""Kostal-only curtailment-test: roept kostal_adapter direct aan, zonder prijslogica.

Veiligste test om te verifieren dat menunavigatie + DOWN/UP-knoppen op de Kostal
het juiste vermogenslimiet-resultaat geven. Geen prijscheck, geen state_store,
geen Steca. Vraagt na elke fase om visuele bevestiging vanaf het LCD.

Gebruik:
    python3 tools/test_kostal_curtail.py            # volledige cyclus: limited -> normal
    python3 tools/test_kostal_curtail.py --only limited
    python3 tools/test_kostal_curtail.py --only normal
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import kostal_adapter  # noqa: E402

_INVERTERS_YAML = _ROOT / "config" / "inverters.yaml"
_MENU_PATHS_YAML = _ROOT / "config" / "menu_paths.yaml"
_SCREENS_JSON = _ROOT / "config" / "screens.json"


def _header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _ask(prompt: str) -> bool:
    return input(f"\n  {prompt} [j/n]: ").strip().lower() in ("j", "ja", "y", "yes")


def _load() -> tuple[dict, dict, dict]:
    with open(_INVERTERS_YAML) as f:
        inverters = yaml.safe_load(f)["inverters"]
    with open(_MENU_PATHS_YAML) as f:
        menu_paths = yaml.safe_load(f)
    actions = menu_paths.get("actions", {})
    screens: dict = {}
    if _SCREENS_JSON.exists():
        with open(_SCREENS_JSON) as f:
            screens = json.load(f)
    return inverters, actions, screens


def _check_calibration(screens: dict) -> bool:
    """Controleert of er voldoende kostal-hashes zijn om de adapter te draaien."""
    kostal_keys = [k for k in screens if k.startswith("kostal.")]
    required = {
        "kostal.home",
        "kostal.instellingen",
        "kostal.service_item",
        "kostal.toetscombinatie_scherm",
        "kostal.service_menu",
        "kostal.vermogensbegrenzing_item",
        "kostal.power_limit_value_max",
        "kostal.power_limit_value_min",
    }
    aanwezig = set(kostal_keys)
    ontbrekend = required - aanwezig
    print(f"  Kostal-hashes in screens.json: {len(kostal_keys)}/{len(required)}")
    for key in sorted(required):
        marker = "✓" if key in aanwezig else "✗"
        print(f"    {marker} {key}")
    if ontbrekend:
        print(f"\n  WAARSCHUWING: ontbrekende hashes — menu_engine zal VerifyError geven.")
        print(f"  Voltooi eerst calibratie voor: {', '.join(sorted(ontbrekend))}")
        return False
    return True


def _run_phase(label: str, desired_state: str, inv_cfg: dict, actions: dict, screens: dict) -> bool:
    _header(f"Fase: {label} (desired_state={desired_state!r})")
    nominal = inv_cfg["nominal_watts"]
    minimum = inv_cfg["min_watts"]
    step = inv_cfg.get("step_size", 100)
    n_presses = (nominal - minimum) // step
    direction = "DOWN" if desired_state == "limited" else "UP"

    print(f"  Inverter: {inv_cfg['name']} ({inv_cfg['ip']})")
    print(f"  Plan: navigeer naar vermogenslimiet-edit, druk {n_presses}× {direction}, bevestig.")
    if not _ask("Doorgaan?"):
        print("  Overgeslagen.")
        return False

    try:
        kostal_adapter.apply(desired_state, inv_cfg["ip"], inv_cfg, actions, screens)
    except Exception as exc:
        print(f"\n  ✗ FOUT tijdens adapter: {type(exc).__name__}: {exc}")
        return False

    print("\n  Adapter klaar — geen exception.")
    if desired_state == "limited":
        verwacht = f"{minimum} W (vermogenslimiet actief)"
    else:
        verwacht = f"{nominal} W / geen limiet (vol vermogen)"
    return _ask(f"Toont het Kostal-display nu: {verwacht}?")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        choices=("limited", "normal"),
        help="Voer slechts één fase uit (anders: limited gevolgd door normal)",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=1500,
        help="Pauze tussen knopdrukken in ms (default 1500 — bewust traag voor tests)",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=1200,
        help="Pauze tussen knopdruk en screenshot-fetch in ms (default 1200)",
    )
    args = parser.parse_args()

    _header("Kostal-only curtailment-test")
    inverters, actions, screens = _load()

    if "kostal" not in inverters:
        print("  FOUT: 'kostal' staat niet in inverters.yaml.")
        sys.exit(1)
    inv_cfg = inverters["kostal"]
    inv_cfg.setdefault("id", "kostal")
    inv_cfg["button_delay_ms"] = args.delay_ms
    inv_cfg["screenshot_settle_ms"] = args.settle_ms
    print(f"\n  button_delay_ms voor deze test: {args.delay_ms} ms")
    print(f"  screenshot_settle_ms voor deze test: {args.settle_ms} ms")
    print(f"  api_style: {inv_cfg.get('api_style', 'new')}")

    print("\n  Calibratie-check:")
    if not _check_calibration(screens):
        if not _ask("Toch doorgaan? (alleen zinvol als je weet wat je doet)"):
            sys.exit(1)

    fases = []
    if args.only == "limited":
        fases = [("naar 500 W", "limited")]
    elif args.only == "normal":
        fases = [("terug naar nominaal", "normal")]
    else:
        fases = [
            ("naar 500 W", "limited"),
            ("terug naar nominaal", "normal"),
        ]

    resultaten = []
    for label, desired in fases:
        ok = _run_phase(label, desired, inv_cfg, actions, screens)
        resultaten.append((label, ok))

    _header("Samenvatting")
    alles_ok = True
    for label, ok in resultaten:
        symbool = "✓" if ok else "✗"
        status = "GESLAAGD" if ok else "MISLUKT"
        print(f"  {symbool} [{status}]  {label}")
        if not ok:
            alles_ok = False

    sys.exit(0 if alles_ok else 1)


if __name__ == "__main__":
    main()
