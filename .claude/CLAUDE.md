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

## Geleerde lessen over de inverter-webserver (BELANGRIJK)

Deze OEM-firmware is heel gevoelig voor concurrent HTTP-requests. Een paar
harde regels die we de hárde manier hebben geleerd:

### 1. Géén browser-tab open op `http://<inverter-ip>` tijdens scripts

De web-UI heeft auto-refresh op `gen.screenshot.bmp`. Die background-polling
**verstoort de menu-state** wanneer een script tegelijkertijd knoppen drukt:
sommige knopdrukken worden genegeerd, sommige sturen het scherm terug naar
home, gedrag is willekeurig. Symptomen: "soms werkt SET, soms niet" zonder
duidelijk patroon. Dit is bij ons drie keer voorgekomen vóór we het
identificeerden.

**Voor productie (cron):** documenteren dat de web-UI niet open mag staan
tijdens een cron-tick, óf de controller moet retry-met-recovery hebben.

### 2. Géén screenshot direct na een knopdruk

`get_screen()` (GET naar `gen.screenshot.bmp`) **direct** na een `press()`
veroorzaakt hetzelfde gedrag als hierboven — de menu-state reset. Tussen
elke `press()` en `get_screen()` moet een settle-pauze van minimaal ~800ms
zitten (`screenshot_settle_ms` in `inverters.yaml`). `menu_engine.py` doet
dit automatisch op alle drie plekken waar het screenshots ophaalt
(`_press_and_locate`, `verify`-stap, `_find_resume_index`).

**Implicatie voor calibrate.py manual mode:** géén auto-screenshot na een
knopdruk. Gebruiker typt expliciet Enter (of `s`) om een screenshot op te
vragen wanneer het scherm stabiel is.

### 3. Inverter raakt klem na veel requests achter elkaar

Na ~10 minuten intensief testen kan de webserver in een rare state komen
(vermoedelijk socket-pool TIME_WAIT). Symptoom: knoppen die eerst werkten
doen het ineens niet meer. Oplossing: 2 minuten wachten of de inverter
power-cyclen. Niet "fixen" met code-aanpassingen — eerst diagnose.

### 4. step_size klopt niet zoals oorspronkelijk aangenomen

Tijdens de eerste test bleek dat de step_size op de Steca **10 W per druk**
is, niet 100 W. `step_size` staat nu op 10 in `inverters.yaml` voor de Steca
(te verifiëren voor Kostal). Deze waarde wordt overigens niet meer gebruikt
voor het aantal sweeps (zie punt 5), maar is bewaard voor referentie.

### 5. Vermogenslimiet wrap-around → boundary-detectie i.p.v. sweep

Een Steca-DOWN op 500 W wrapt naar 2500 W (en omgekeerd UP op 2500 → 500).
Dat betekent: **een naïeve "200× DOWN" sweep is niet veilig.** Vanaf een
willekeurige tussenwaarde (bijv. 1000 W) eindigt zo'n sweep door de
mod-2000 wrap niet op 500 W maar op de oorspronkelijke waarde — onveilig
en stilzwijgend fout.

Daarom werkt de adapter nu met **boundary-hash-detectie**:

1. Navigeer naar het edit-scherm
2. Screenshot + identify → vergelijk met `power_limit_value_min` en
   `power_limit_value_max` hashes
3. Als al op de doel-boundary: 0 knopdrukken, alleen confirm
4. Als op de andere boundary: 1× DOWN/UP wrap, verifieer doel-hash, confirm
5. Als op een tussenwaarde: **GEEN sweep** — `UnknownPositionError` →
   `alarm.flag` via controller. Vereist handmatige interventie (inverter
   handmatig naar 500 W of nominaal zetten en dan herstart).

Dit vervangt de oude "n_presses = (nominal-min)/step_size" sweep volledig.
Tijdsimpact per cyclus is nu ~3-5 seconden (navigatie + 1 tap + verify),
i.p.v. 60+ seconden bij sweep.

Calibratie vereist hierdoor 2 extra schermen per inverter:
`power_limit_value_max` en `power_limit_value_min` (zie
`menu_paths.yaml` → `calibration_sequence`).

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
