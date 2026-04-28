# Zonneplan uurprijs — inverter-curtailment

Draait op een Raspberry Pi en begrenst twee thuis-inverters automatisch
tijdens uren met negatieve Zonneplan-stroomprijzen. Bij positieve prijzen
gaan de inverters automatisch terug naar vol vermogen.

## Hardware

| Inverter           | IP              | Nominaal | Min. limiet |
|--------------------|-----------------|----------|-------------|
| StecaGrid 2500     | 192.168.178.6   | 2500 W   | 500 W       |
| Kostal Piko 4.2 MP | 192.168.178.5   | 4200 W   | 500 W       |

Aansturing via de ingebouwde webinterface (knop-emulatie). Geen RS485,
geen smart plug, geen AC-onderbreking.

---

## Installatie

### 1. Vereisten

Python 3.10 of hoger vereist.

Op Raspberry Pi OS (Debian 12+) moet je een virtuele omgeving gebruiken vanwege
PEP 668:

```bash
# Eenmalig: virtuele omgeving aanmaken
python3 -m venv ~/zonneplan_env

# Activeer de venv
source ~/zonneplan_env/bin/activate

# Installeer dependencies
pip install requests Pillow PyYAML
```

Controleer achteraf:

```bash
python3 -c "import requests, PIL, yaml; print('OK')"
```

### 2. Repository klonen

```bash
cd ~
git clone https://github.com/materharmsel/zonneplan-uurprijs zonneplan-uurprijs
cd zonneplan-uurprijs
```

### 3. Eerste aanmelding bij Zonneplan

Zorg dat de venv is geactiveerd:

```bash
source ~/zonneplan_env/bin/activate
python3 fetch_prices.py
```

Volg de instructies: vul je e-mailadres in en klik op de link in de e-mail.
Tokens worden opgeslagen in `~/.zonneplan_tokens.json`.

### 4. Calibratie (eenmalig, samen uitvoeren)

Zorg dat de venv is geactiveerd, en voer de calibratietool uit terwijl beide
inverters bereikbaar zijn:

```bash
source ~/zonneplan_env/bin/activate
python3 tools/calibrate.py
```

Het script navigeert stap voor stap door de menu's. Bevestig elk scherm
visueel en druk op Enter. De referentie-hashes worden opgeslagen in
`config/screens.json`. Voer dit uit voor **beide** inverters (Steca eerst,
daarna Kostal).

---

## Cron instellen

Open de crontab:

```bash
crontab -e
```

Voeg toe (verander `/home/pi` naar jouw werkelijke home-map):

```
1 * * * * /home/pi/zonneplan_env/bin/python3 /home/pi/zonneplan-uurprijs/controller.py >> /home/pi/zonneplan-uurprijs/logs/cron.log 2>&1
```

De controller wordt elke minuut 1 van elk uur uitgevoerd (`@hourly :01`).

**Let op:** gebruik het volle pad naar de Python in de virtuele omgeving
(`~/zonneplan_env/bin/python3`), niet gewoon `python3`.

---

## Log-rotatie

Kopieer de logrotate-configuratie:

```bash
sudo cp deploy/logrotate.conf /etc/logrotate.d/zonneplan-uurprijs
```

Of voeg handmatig toe aan `/etc/logrotate.d/zonneplan-uurprijs`:

```
/home/pi/zonneplan-uurprijs/logs/*.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
    copytruncate
}
```

---

## Bestanden en mappen

```
zonneplan-uurprijs/
├── controller.py          # Hoofdmodule — cron-entry
├── fetch_prices.py        # Zonneplan-prijzen ophalen
├── inverter_client.py     # HTTP-laag (knop-emulatie)
├── menu_engine.py         # YAML-gebaseerde menu-navigator
├── screen_verifier.py     # BMP-hash verificatie
├── state_store.py         # Atomic JSON state + alarm
├── steca_adapter.py       # Steca-specifieke adapter
├── kostal_adapter.py      # Kostal-specifieke adapter
├── config/
│   ├── inverters.yaml     # IPs, nominaal, stapgrootte
│   ├── menu_paths.yaml    # Declaratieve menu-paden
│   └── screens.json       # Referentie-hashes (na calibratie)
├── deploy/
│   └── logrotate.conf     # Logrotate-configuratie
├── logs/                  # Draaiende logs (rotating)
├── state/
│   ├── inverter_state.json  # Huidige staat per inverter
│   └── alarm.flag           # Aanwezig bij fout (zie Troubleshooting)
└── tools/
    ├── calibrate.py       # Calibratie-tool (eenmalig)
    └── e2e_test.py        # End-to-end testscript
```

---

## Werking per uur

```
cron :01
  → prijs ophalen (of FAKE_PRICE env-var)
  → desired = 'limited' als prijs < 0, anders 'normal'
  → per inverter:
      als al in desired-staat: overslaan
      anders: menu navigeren, waarde instellen, hash verifiëren
      bij succes: state opslaan, alarm wissen
      bij fout:   alarm.flag schrijven, andere inverter doorgaan
```

Drempelwaarde: `prijs < 0,00 €/kWh` (prijs == 0 = normal).
Begrenzing: 500 W (minimum beide inverters).

---

## Troubleshooting

### alarm.flag aanwezig

```bash
cat state/alarm.flag
```

Het bestand bevat een timestamp en de reden van de fout. Mogelijke oorzaken:

- **Netwerk niet bereikbaar** — ping de inverter-IPs (`ping 192.168.178.6`).
- **Hash-mismatch** — de firmware heeft een ander menu-scherm dan verwacht.
  Voer calibratie opnieuw uit: `python3 tools/calibrate.py`.
- **Inverter staat in onverwacht submenu** — de controller stuurt altijd
  eerst `ESC×5` om terug naar home te gaan. Als dit herhaaldelijk mislukt,
  controleer dan de inverter fysiek.

Het alarm wordt automatisch gewist bij de eerstvolgende succesvolle run.

### Stand handmatig resetten

```bash
# Verwijder alarm en forceer herschrijving bij volgende tick
rm -f state/alarm.flag
# Verwijder ook state zodat controller beide inverters opnieuw bezoekt
rm -f state/inverter_state.json
```

### Logs bekijken

```bash
tail -f logs/controller.log
```

### Testrun met gesimuleerde negatieve prijs

```bash
source ~/zonneplan_env/bin/activate
FAKE_PRICE=-0.01 python3 controller.py
```

### Volledige end-to-end test

```bash
source ~/zonneplan_env/bin/activate
python3 tools/e2e_test.py
```

---

## Tests draaien

```bash
source ~/zonneplan_env/bin/activate
python3 -m pytest tests/ -v
```

---

## Aanpassen

- **Drempelwaarde** — pas `_desired_state()` aan in `controller.py`.
- **Doelvermogen** — pas `min_watts` aan in `config/inverters.yaml`.
- **Stapgrootte** — pas `step_size` aan in `config/inverters.yaml`; kalibreer
  opnieuw als de waarde niet overeenkomt met de werkelijkheid.
- **Knop-vertraging** — pas `button_delay_ms` aan in `config/inverters.yaml`.
