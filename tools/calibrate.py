"""Interactieve calibratie-tool: navigeer naar elk sleutelscherm en sla de BMP-hash op."""

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))
import inverter_client

_PROJECT_ROOT = Path(__file__).parent.parent
SCREENS_JSON = _PROJECT_ROOT / "config" / "screens.json"
MENU_PATHS_YAML = _PROJECT_ROOT / "config" / "menu_paths.yaml"
INVERTERS_YAML = _PROJECT_ROOT / "config" / "inverters.yaml"


def compute_hash(image: Image.Image) -> str:
    """Berekent SHA-256 hash van de pixeldata van het scherm."""
    return hashlib.sha256(image.tobytes()).hexdigest()


def press_sequence(ip: str, buttons: list[dict], service_long: bool = False) -> None:
    """Druk een reeks knoppen in op het opgegeven IP."""
    for btn in buttons:
        button = btn["button"]
        repeat = btn.get("repeat", 1)
        duration_key = btn.get("duration", "short")

        if duration_key == "service":
            duration = "long" if service_long else "short"
        else:
            duration = duration_key

        for _ in range(repeat):
            inverter_client.press(ip, button, duration=duration, delay_ms=300)


def save_screens(screens: dict, path: Path = SCREENS_JSON) -> None:
    """Schrijf screens atomisch naar JSON."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(screens, f, indent=2)
    tmp.replace(path)
    print(f"  screens.json bijgewerkt ({len(screens)} hashes opgeslagen).")


def _show_image(image: Image.Image) -> None:
    """Sla screenshot op als tijdelijk bestand en open in de standaard viewer."""
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as f:
        tmppath = f.name
    image.save(tmppath, format="BMP")

    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(tmppath)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.run(["open", tmppath], check=False)
        else:
            subprocess.run(["xdg-open", tmppath], check=False)
    except Exception:
        pass

    print(f"  Screenshot: {tmppath}")


def _load_config() -> tuple[dict, dict, dict]:
    """Laad inverters.yaml, menu_paths.yaml en bestaande screens.json."""
    with open(INVERTERS_YAML) as f:
        inverters = yaml.safe_load(f)["inverters"]
    with open(MENU_PATHS_YAML) as f:
        menu_paths = yaml.safe_load(f)
    screens: dict = {}
    if SCREENS_JSON.exists():
        with open(SCREENS_JSON) as f:
            screens = json.load(f)
    return inverters, menu_paths, screens


def _calibrate_inverter(
    inv_name: str,
    inv_cfg: dict,
    calibration_steps: list[dict],
    screens: dict,
) -> dict:
    """Voer de calibratie-sessie uit voor één inverter. Geeft bijgewerkte screens terug."""
    ip = inv_cfg["ip"]
    service_long: bool = inv_cfg.get("service_button_long", False)

    print(f"\n{'=' * 60}")
    print(f"Calibratie: {inv_cfg['name']} ({ip})")
    print(f"{'=' * 60}")
    print("\nNavigeer naar het hoofdscherm (ESC × 5)...")
    for _ in range(5):
        inverter_client.press(ip, "ESC", duration="short", delay_ms=300)

    for step in calibration_steps:
        screen_id: str = step["id"]
        key = f"{inv_name}.{screen_id}"
        description: str = step["description"]
        buttons: list[dict] = step.get("buttons", [])
        prompt: str = step.get("prompt", f"Is dit het scherm '{description}'?")

        print(f"\n--- Scherm: {description} ({key}) ---")

        # Eerste stap is 'home'; die knoppen zijn al ingedrukt voor de loop.
        # Vanaf de tweede stap drukken we de opgegeven knoppen.
        if screen_id != "home" and buttons:
            print("  Knoppen indrukken...")
            press_sequence(ip, buttons, service_long=service_long)

        print("  Screenshot ophalen...")
        try:
            image = inverter_client.get_screen(ip)
        except Exception as exc:
            print(f"  FOUT bij ophalen screenshot: {exc}")
            print("  Dit scherm overslaan.")
            continue

        _show_image(image)

        while True:
            answer = input(f"  {prompt}\n  [j]a bevestigen / [n]ee overslaan / [h]erprobeer: ").strip().lower()
            if answer == "j":
                h = compute_hash(image)
                screens[key] = h
                print(f"  Hash opgeslagen: {h[:16]}…")
                save_screens(screens)
                break
            elif answer == "h":
                print("  Scherm opnieuw ophalen...")
                try:
                    image = inverter_client.get_screen(ip)
                    _show_image(image)
                except Exception as exc:
                    print(f"  FOUT: {exc}")
            else:
                print("  Overgeslagen — geen hash opgeslagen voor dit scherm.")
                break

    return screens


def main() -> None:
    print("=== Inverter Calibratie-tool ===")
    print("Dit programma navigeert de inverters door hun menu en slaat")
    print("BMP-hashes op voor verificatie tijdens curtailment.\n")

    inverters, menu_paths, screens = _load_config()
    calibration_steps: list[dict] = menu_paths.get("calibration_sequence", [])

    if not calibration_steps:
        print("FOUT: geen calibration_sequence gevonden in menu_paths.yaml")
        sys.exit(1)

    print(f"{len(calibration_steps)} schermen te calibreren per inverter.")
    print(f"Inverters: {', '.join(inverters.keys())}\n")
    print("Volgorde: Steca eerst, dan Kostal (zoals in inverters.yaml).")

    for inv_name, inv_cfg in inverters.items():
        input(f"\nDruk op Enter om calibratie voor {inv_cfg['name']} ({inv_cfg['ip']}) te starten...")
        screens = _calibrate_inverter(inv_name, inv_cfg, calibration_steps, screens)

    print("\n=== Calibratie afgerond ===")
    print(f"Totaal opgeslagen hashes: {len(screens)}")
    for key, h in screens.items():
        print(f"  {key}: {h[:16]}…")


if __name__ == "__main__":
    main()
