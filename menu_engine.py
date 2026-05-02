"""YAML-pad-uitvoerder voor inverter-menunavigatie met expect, settle en locate-resume."""

import time

import inverter_client
import screen_verifier


class VerifyError(Exception):
    """Scherm-hash komt niet overeen — huidige menulocatie onbekend."""


def _press_and_locate(
    ip: str,
    button: str,
    duration: str,
    expected_id: str,
    max_retries: int,
    delay_ms: int,
    inverter_cfg: dict,
    screens: dict,
) -> None:
    """Verifieert na een knopdruk of het verwachte scherm bereikt is; herprobeert zo niet."""
    prefix = inverter_cfg.get("id", "")
    settle_ms = inverter_cfg.get("screenshot_settle_ms", 800)
    api_style = inverter_cfg.get("api_style", "new")
    for attempt in range(max_retries + 1):
        time.sleep(settle_ms / 1000)
        image = inverter_client.get_screen(ip)
        current = screen_verifier.identify(image, screens, prefix)
        if current == expected_id:
            return
        if attempt < max_retries:
            inverter_client.press(ip, button, duration=duration, delay_ms=delay_ms, api_style=api_style)
    for _ in range(5):
        inverter_client.press(ip, "ESC", delay_ms=delay_ms, api_style=api_style)
    raise VerifyError(
        f"Kon scherm '{expected_id}' niet bereiken op {ip} na {max_retries + 1} pogingen"
    )


def _find_resume_index(ip: str, inverter_cfg: dict, steps: list, screens: dict) -> int:
    """Identificeert het huidige scherm en geeft de hervatindex in steps terug."""
    prefix = inverter_cfg.get("id", "")
    settle_ms = inverter_cfg.get("screenshot_settle_ms", 800)
    time.sleep(settle_ms / 1000)
    image = inverter_client.get_screen(ip)
    current = screen_verifier.identify(image, screens, prefix)
    if current is None:
        return 0
    for i, step in enumerate(steps):
        if step.get("expect") == current:
            return i + 1
    return 0


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
    - button: <naam> [repeat: N] [duration: short|long|service] [expect: <id>] [max_retries: N]
    - settle_ms: <ms>    — pauze zonder knopdruk
    - verify: <id>       — hash-check (backward compatible); bij mismatch: ESC×5 + VerifyError
    - action: <naam>     — recursieve sub-actie

    Als locate_resume: true in de actie-definitie staat, wordt de huidige schermpositie
    bepaald voor de eerste stap en de navigatie hervat vanaf de bekende positie.
    """
    if _depth > 10:
        raise RecursionError("menu_engine: maximale nesting-diepte overschreden")

    delay_ms = inverter_cfg.get("button_delay_ms", 300)
    service_long = inverter_cfg.get("service_button_long", False)
    api_style = inverter_cfg.get("api_style", "new")

    steps = actions[action_name]["steps"]

    start_index = 0
    if actions[action_name].get("locate_resume", False) and screens:
        start_index = _find_resume_index(ip, inverter_cfg, steps, screens)

    for step in steps[start_index:]:
        if "action" in step:
            run_action(step["action"], ip, inverter_cfg, actions, screens, _depth=_depth + 1)

        elif "settle_ms" in step:
            time.sleep(step["settle_ms"] / 1000)

        elif "button" in step:
            button = step["button"]
            repeat = step.get("repeat", 1)
            expect = step.get("expect")
            max_retries = step.get("max_retries", 3)
            raw_duration = step.get("duration", "short")
            if raw_duration == "service":
                duration = "long" if service_long else "short"
            else:
                duration = raw_duration
            for _ in range(repeat):
                inverter_client.press(ip, button, duration=duration, delay_ms=delay_ms, api_style=api_style)
            if expect and screens:
                _press_and_locate(
                    ip, button, duration, expect, max_retries, delay_ms, inverter_cfg, screens
                )

        elif "verify" in step:
            screen_id = step["verify"]
            settle_ms = inverter_cfg.get("screenshot_settle_ms", 800)
            time.sleep(settle_ms / 1000)
            image = inverter_client.get_screen(ip)
            if not screen_verifier.verify(image, screen_id, screens):
                for _ in range(5):
                    inverter_client.press(ip, "ESC", delay_ms=delay_ms, api_style=api_style)
                raise VerifyError(
                    f"Scherm '{screen_id}' niet herkend op {ip} — recovery uitgevoerd (ESC×5)"
                )
