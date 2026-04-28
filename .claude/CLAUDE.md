# Zonneplan-uurprijs — projectinstructies

## Wat is dit project

Tool die op een Raspberry Pi draait en twee thuis-inverters automatisch
begrenst tijdens uren met negatieve Zonneplan-stroomprijzen, om terugleveren
aan het net (en daardoor geld betalen) te voorkomen. Bij positieve prijzen
gaan de inverters automatisch terug naar vol vermogen.

Volledig ontwerp staat in:
`C:\Users\Maarten\.claude\plans\je-zit-in-plan-shimmering-rivest.md`

## Communicatie

De gebruiker spreekt Nederlands. Reageer in het Nederlands.

## Hardware

| Inverter | IP | Nominaal | Min. limit |
|---|---|---|---|
| StecaGrid 2500 | 192.168.178.6 | 2500 W | 500 W |
| Kostal Piko 4.2 MP | 192.168.178.5 | 4200 W | 500 W |

Beide inverters delen dezelfde OEM-webinterface (Kostal nam Steca over).

## Aansturings-API (kern van dit project)

```
GET http://<inverter-ip>/buttons.html?BUTTON=<naam>&EVENT=<event>
GET http://<inverter-ip>/gen.screenshot.bmp     # 256×128 LCD-screenshot
```

- BUTTON: `ESC` | `UP` | `DOWN` | `SET` | `BOTHMIDDLE`
- EVENT: `clicked` → `released` (kort) of `clicked` → `long` → `released`
- Geen authenticatie op LAN
- Verschil: bij Kostal moet SERVICE (BOTHMIDDLE) **lang** ingedrukt

## Harde constraints (niet schenden)

1. **Geen RS485, geen smart plug, geen AC-onderbreking** — alleen netwerk
2. **Geen andere instellingen wijzigen** — dus altijd verifiëren via
   BMP-hash dat we op het juiste menu-scherm staan vóór een SET-actie
3. **Failsafe = laat staan + alarm** — bij twijfel niets doen, alarmflag
   schrijven, log, volgende cron-tick probeert opnieuw

## Beslissingen

| Item | Waarde |
|---|---|
| Drempel curtailment | prijs < 0,00 €/kWh |
| Doel-vermogen bij negatief | 500 W (minimum beide inverters) |
| Doel-vermogen bij positief/nul | "geen limiet" / vol nominaal |
| Schedule | cron @hourly op :01 |
| Notificatie | alleen logbestanden |
| Verificatie | BMP-hash (geen OCR, geen Tesseract) |

## Calibratie verplicht voor implementatie

Voordat het curtailment-systeem werkt moeten alle menu-scherm-hashes worden
vastgelegd via `tools/calibrate.py`. Dit is een **interactieve sessie samen
met de gebruiker**: tool drukt knop volgens YAML, toont BMP, gebruiker
bevestigt visueel, hash gaat in `config/screens.json`.

## Bestaand basis-script

`fetch_prices.py` haalt Zonneplan-prijzen op via de onofficiele API.
Tokens in `~/.zonneplan_tokens.json`, log in `~/zonneplan_prices.log`.
Mag uitgebreid worden (extra functies), niet kapot maken.

## Installatie op Raspberry Pi OS

Op moderne Raspberry Pi OS (Debian 12+) vereist Python 3.11+ een virtuele omgeving
vanwege PEP 668. Dit is **nodig voor dit project**:

```bash
# Eenmalig: venv aanmaken in home-directory
python3 -m venv ~/zonneplan_env

# Voor elke sessie: venv activeren
source ~/zonneplan_env/bin/activate

# Dan pas werkt pip
pip install requests Pillow PyYAML
```

Voor **cron-jobs** en scripts moet het volle pad gebruikt worden:

```bash
/home/pi/zonneplan_env/bin/python3 /path/to/script.py
```

Dit wordt in README.md en crontab-instructies duidelijk gemaakt.

## Codestijl

- Python 3.10+ (gebruikt `dict | None` en `list[dict]`)
- Standaard library + `requests` + `Pillow` + `PyYAML`; geen zware deps
- Nederlandse log-berichten en commentaar mag, code-identifiers in Engels
- Module-docstrings kort en in het Nederlands
