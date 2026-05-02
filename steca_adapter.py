"""Adapter voor de StecaGrid 2500 — stelt vermogenslimiet in via menunavigatie.

Gebruikt boundary-detectie via BMP-hash: na navigatie naar het edit-scherm
wordt gecontroleerd of de inverter exact op 500 W of nominaal staat. Vanwege
de wrap-around-eigenschap van de Steca volstaat dan 0 of 1 knopdruk om de
gewenste waarde te bereiken. Bij een tussenwaarde wordt geen sweep gedaan
(onveilig bij wrap) — er gaat een alarm naar de controller.
"""

import logging
import time

import inverter_client
import menu_engine
import screen_verifier

log = logging.getLogger(__name__)


class UnknownPositionError(RuntimeError):
    """Vermogenslimiet staat op een tussenwaarde — sweep is niet veilig bij wrap."""


def _identify_value_screen(ip: str, inverter_cfg: dict, screens: dict) -> str | None:
    """Haal screenshot op (na settle) en identificeer t.o.v. boundary-hashes."""
    settle_ms = inverter_cfg.get("screenshot_settle_ms", 800)
    inv_id = inverter_cfg.get("id", "")
    time.sleep(settle_ms / 1000)
    image = inverter_client.get_screen(ip)
    return screen_verifier.identify(image, screens, inv_id)


def apply(
    desired_state: str,
    ip: str,
    inverter_cfg: dict,
    actions: dict,
    screens: dict,
) -> None:
    """Past desired_state ('limited' of 'normal') toe op de inverter.

    Roept menu_engine aan voor navigatie en gebruikt boundary-hash-detectie
    om met minimale knopdrukken (0 of 1) de juiste waarde te bereiken.
    VerifyError of UnknownPositionError wordt niet afgevangen — controller handelt af.
    """
    value_step_delay_ms = inverter_cfg.get("value_step_delay_ms", 100)
    api_style = inverter_cfg.get("api_style", "new")

    target = "power_limit_value_min" if desired_state == "limited" else "power_limit_value_max"
    other = "power_limit_value_max" if desired_state == "limited" else "power_limit_value_min"
    # Wrap-richting is OMGEKEERD aan de "logische" richting:
    # - Vanaf MAX wrapt UP naar MIN (DOWN doet daar gewoon -10W)
    # - Vanaf MIN wrapt DOWN naar MAX (UP doet daar gewoon +10W)
    direction = "UP" if desired_state == "limited" else "DOWN"

    menu_engine.run_action("navigate_to_power_limit_edit", ip, inverter_cfg, actions, screens)

    current = _identify_value_screen(ip, inverter_cfg, screens)
    log.info("%s: edit-scherm-positie=%r, doel=%r", ip, current, target)

    if current == target:
        log.info("%s: al op doel-waarde — alleen bevestigen", ip)
    elif current == other:
        log.info("%s: op andere boundary — 1× %s om te wrappen", ip, direction)
        inverter_client.press(ip, direction, duration="short", delay_ms=value_step_delay_ms, api_style=api_style)
        verified = _identify_value_screen(ip, inverter_cfg, screens)
        if verified != target:
            raise RuntimeError(
                f"Wrap mislukt op {ip}: na 1× {direction} verwacht {target!r}, "
                f"gekregen {verified!r}"
            )
        log.info("%s: wrap geslaagd → %r", ip, target)
    else:
        # Geen sweep — bij wrap-firmware geeft dat onvoorspelbare uitkomst.
        log.warning(
            "%s: vermogenslimiet op onbekende tussenwaarde (scherm=%r). "
            "Geen sweep uitgevoerd — handmatig naar 500 of nominaal zetten en herproberen.",
            ip, current,
        )
        raise UnknownPositionError(
            f"Onbekende waarde-positie op {ip}: scherm={current!r}. "
            f"Sweep zou onveilig zijn vanwege wrap-around. Handmatig ingrijpen vereist."
        )

    menu_engine.run_action("confirm_power_limit_edit", ip, inverter_cfg, actions, screens)
