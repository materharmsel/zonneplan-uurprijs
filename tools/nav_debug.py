"""Handmatig navigeer-tool om de juiste menustructuur van de inverter te ontdekken."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import inverter_client

DEFAULT_IP = "192.168.178.6"
ip = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IP
# Default: nieuwe API (Steca). Voor Kostal: tweede argument 'legacy'.
api_style = sys.argv[2] if len(sys.argv) > 2 else "new"

print(f"\nVerbonden met {ip}  [api_style={api_style}]")
print("Druk knoppen in en vertel wat je op het inverter-display ziet.")
print()
print("Beschikbare knoppen:")
print("  ESC, UP, DOWN, SET, BOTHMIDDLE")
print("  Voeg 'l' toe voor lang indrukken, bijv: BOTHMIDDLE l")
print("  Type 'q' om te stoppen")
print()

while True:
    try:
        cmd = input("Knop> ").strip()
    except (KeyboardInterrupt, EOFError):
        break

    if not cmd:
        continue
    if cmd.lower() == "q":
        break

    parts = cmd.upper().split()
    button = parts[0]
    duration = "long" if len(parts) > 1 and parts[1] == "L" else "short"

    valid = {"ESC", "UP", "DOWN", "SET", "BOTHMIDDLE"}
    if button not in valid:
        print(f"  Onbekende knop '{button}'. Kies uit: {', '.join(valid)}")
        continue

    try:
        inverter_client.press(ip, button, duration=duration, delay_ms=400, api_style=api_style)
        print(f"  → {button} ({duration}) ingedrukt.")
        print(f"  Wat zie je nu op het display?")
    except Exception as exc:
        print(f"  FOUT: {exc}")
