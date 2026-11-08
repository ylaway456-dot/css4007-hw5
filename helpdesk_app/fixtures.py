"""Only the supplied HW5 fictional JSON fixtures are used as reference data."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    with (ROOT / relative_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def helpdesk_data() -> dict:
    return load_json("data/helpdesk.json")


def service_data() -> dict:
    return load_json("data/service_status.json")


def scenarios() -> list[dict]:
    return load_json("data/scenarios.json")["scenarios"]


def get_scenario(scenario_id: str) -> dict:
    return next(s for s in scenarios() if s["id"] == scenario_id)


def normalize_topic(text: str) -> str | None:
    """Recognise long tool arguments, not just exact 'Wi-Fi'."""
    value = str(text).casefold()
    wifi = bool(re.search(r"wi[\s-]?fi|wireless|campus.demo", value))
    password = bool(re.search(r"password|account.recovery|forgot.*account", value))
    if wifi and not password:
        return "wifi"
    if password and not wifi:
        return "password"
    if wifi and password:
        return "wifi"  # Wi-Fi-password ambiguity is handled in Part 1, not a tool guess.
    return None


def normalize_service(text: str) -> str | None:
    """Map model paraphrases to the exact service keys in service_status.json."""
    value = str(text).casefold()
    if re.search(r"account[\s_-]*recovery|password[\s_-]*recovery|recover.*password", value):
        return "account_recovery"
    topic = normalize_topic(value)
    if topic is not None:
        return helpdesk_data()["topic_services"][topic]
    return None
