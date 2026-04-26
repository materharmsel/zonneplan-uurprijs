"""YAML-pad-uitvoerder voor inverter-menunavigatie met verify en auto-recovery."""

import inverter_client
import screen_verifier


class VerifyError(Exception):
    """Scherm-hash komt niet overeen — huidige menulocatie onbekend."""


def run_action(
    action_name: str,
    ip: str,
    inverter_cfg: dict,
    actions: dict,
    screens: dict,
    *,
    _depth: int = 0,
) -> None:
    """Voert een actie uit zoals gedefinieerd in menu_paths.yaml (actions-sectie).

    Stap-typen:
    - button: <naam> [repeat: N] [duration: short|long|service]
    - verify: <screen_id>  — hash-check; bij mismatch: ESC×5 + VerifyError
    - action: <naam>       — recursieve sub-actie
    """
    if _depth > 10:
        raise RecursionError("menu_engine: maximale nesting-diepte overschreden")

    delay_ms = inverter_cfg.get("button_delay_ms", 300)
    service_long = inverter_cfg.get("service_button_long", False)

    for step in actions[action_name]["steps"]:
        if "action" in step:
            run_action(step["action"], ip, inverter_cfg, actions, screens, _depth=_depth + 1)

        elif "button" in step:
            button = step["button"]
            repeat = step.get("repeat", 1)
            raw_duration = step.get("duration", "short")
            if raw_duration == "service":
                duration = "long" if service_long else "short"
            else:
                duration = raw_duration
            for _ in range(repeat):
                inverter_client.press(ip, button, duration=duration, delay_ms=delay_ms)

        elif "verify" in step:
            screen_id = step["verify"]
            image = inverter_client.get_screen(ip)
            if not screen_verifier.verify(image, screen_id, screens):
                for _ in range(5):
                    inverter_client.press(ip, "ESC", delay_ms=delay_ms)
                raise VerifyError(
                    f"Scherm '{screen_id}' niet herkend op {ip} — recovery uitgevoerd (ESC×5)"
                )
