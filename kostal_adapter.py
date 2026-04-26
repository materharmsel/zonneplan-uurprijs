"""Adapter voor de Kostal Piko 4.2 MP — stelt vermogenslimiet in via menunavigatie."""

import inverter_client
import menu_engine


def apply(
    desired_state: str,
    ip: str,
    inverter_cfg: dict,
    actions: dict,
    screens: dict,
) -> None:
    """Past desired_state ('limited' of 'normal') toe op de inverter.

    Identiek aan steca_adapter; het Kostal-specifieke gedrag (lange SERVICE-druk)
    wordt afgehandeld door menu_engine via inverter_cfg['service_button_long'].
    VerifyError van menu_engine wordt niet afgevangen — de controller handelt die af.
    """
    delay_ms = inverter_cfg.get("button_delay_ms", 300)
    nominal = inverter_cfg["nominal_watts"]
    minimum = inverter_cfg["min_watts"]
    step_size = inverter_cfg.get("step_size", 100)

    if desired_state == "limited":
        direction = "DOWN"
        n_presses = (nominal - minimum) // step_size
    else:
        direction = "UP"
        n_presses = (nominal - minimum) // step_size

    menu_engine.run_action("navigate_to_power_limit_edit", ip, inverter_cfg, actions, screens)

    for _ in range(n_presses):
        inverter_client.press(ip, direction, duration="short", delay_ms=delay_ms)

    menu_engine.run_action("confirm_power_limit_edit", ip, inverter_cfg, actions, screens)
