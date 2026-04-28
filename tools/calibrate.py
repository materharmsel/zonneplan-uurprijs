"""Interactieve calibratie-tool: navigeer naar elk sleutelscherm en sla de BMP-hash op."""

import hashlib
import json
import sys
import time
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
        duration = "long" if (duration_key == "service" and service_long) else (
            duration_key if duration_key != "service" else "short"
        )
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
    """Toont het LCD-scherm als blokgrafiek in de terminal (werkt via SSH)."""
    # Schaal 256×128 → 64×32 pixels, weergeef als 64×16 rijen half-bloktekens
    target_w, target_h = 64, 32
    gray = image.convert("L").resize((target_w, target_h), Image.NEAREST)

    print()
    print("  ┌" + "─" * target_w + "┐")
    for y in range(0, target_h, 2):
        row = ""
        for x in range(target_w):
            top = gray.getpixel((x, y)) > 128
            bot = gray.getpixel((x, y + 1)) > 128
            if top and bot:
                row += "█"
            elif top:
                row += "▀"
            elif bot:
                row += "▄"
            else:
                row += " "
        print(f"  │{row}│")
    print("  └" + "─" * target_w + "┘")
    print()


def _go_home(ip: str) -> None:
    """Reset de inverter naar het hoofdscherm via ESC×5 met settle-pauze."""
    for _ in range(5):
        inverter_client.press(ip, "ESC", duration="short", delay_ms=300)
    time.sleep(0.6)


def _navigate_to_step(
    ip: str,
    target_id: str,
    calibration_steps: list[dict],
    service_long: bool,
) -> None:
    """Navigeer vanaf home naar het opgegeven scherm door alle voorgaande stappen te spelen."""
    _go_home(ip)
    for step in calibration_steps:
        if step["id"] == target_id:
            break
        if step["id"] != "home" and step.get("buttons"):
            press_sequence(ip, step["buttons"], service_long=service_long)
    # Druk dan de knoppen van het doelscherm zelf in
    for step in calibration_steps:
        if step["id"] == target_id and target_id != "home" and step.get("buttons"):
            press_sequence(ip, step["buttons"], service_long=service_long)
            break


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
    _go_home(ip)

    for step in calibration_steps:
        screen_id: str = step["id"]
        key = f"{inv_name}.{screen_id}"
        description: str = step["description"]
        buttons: list[dict] = step.get("buttons", [])
        prompt: str = step.get("prompt", f"Is dit het scherm '{description}'?")

        print(f"\n--- Scherm: {description} ({key}) ---")

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
            answer = input(
                f"  {prompt}\n  [j]a bevestigen / [n]ee overslaan / [h]erprobeer: "
            ).strip().lower()

            if answer == "j":
                h = compute_hash(image)
                screens[key] = h
                print(f"  Hash opgeslagen: {h[:16]}…")
                save_screens(screens)
                break

            elif answer == "h":
                print("  Terug naar home en opnieuw navigeren naar dit scherm...")
                try:
                    _navigate_to_step(ip, screen_id, calibration_steps, service_long)
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
