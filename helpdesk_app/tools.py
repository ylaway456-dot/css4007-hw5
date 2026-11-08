"""Part 2: reusable direct-call tools. Only fictional data, only local drafts."""
import json
import re
import uuid
from pathlib import Path
from .fixtures import load_json, helpdesk_data, service_data, normalize_topic, normalize_service


def find_instructions(topic: str) -> dict:
    category = normalize_topic(topic)
    if category is None:
        return {"error": "Unknown helpdesk topic. Ask about Wi-Fi or password recovery."}
    guide = helpdesk_data()["instructions"][category]
    return {"topic": category, "instruction_id": guide["instruction_id"],
            "title": guide["title"], "steps": list(guide["steps"]),
            "source": "data/helpdesk.json"}


def check_service_status(service: str, status_profile: str = "normal") -> dict:
    key = normalize_service(service)
    profiles = service_data()["profiles"]
    if status_profile not in profiles:
        return {"error": "Unknown status profile."}
    if key is None or key not in profiles[status_profile]:
        return {"error": "Unknown service; use Wi-Fi or account recovery."}
    entry = profiles[status_profile][key]
    return {"service": key, "status_profile": status_profile,
            "status": entry["status"], "message": entry["message"],
            "source": "data/service_status.json"}


STEP_PATTERNS = [
    (r"\b(?:i\s+)?(?:enabled|turned on|switched on)\s+(?:the\s+)?(?:wi[ -]?fi|it)\b", "Enabled Wi-Fi"),
    (r"\b(?:i\s+)?(?:forgot|removed|deleted)\s+(?:the\s+)?saved\s+network\b", "Forgot the saved network"),
    (r"\b(?:i\s+)?(?:tried\s+)?reconnect(?:ed|ing)?\b", "Tried reconnecting"),
]


def extract_claimed_steps(user_messages: list[str]) -> list[str]:
    """Conservative parsing: only steps EXPLICITLY claimed in USER messages."""
    steps = []
    for text in user_messages:
        for pattern, step in STEP_PATTERNS:
            if re.search(pattern, text, flags=re.I) and step not in steps:
                steps.append(step)
    return steps


def get_last_problem_message(user_messages: list[str]) -> str:
    for message in reversed(user_messages):
        if normalize_topic(message) and ("fail" in message.lower() or "will not" in message.lower()
                                          or "issue" in message.lower() or "problem" in message.lower()
                                          or "unavailable" in message.lower() or "not connect" in message.lower()):
            return message
    return ""


def conditional_ticket_requested(user_messages: list[str]) -> bool:
    text = user_messages[-1].casefold() if user_messages else ""
    return bool(re.search(r"\bif\s+(?:it\s+is|it's|the\s+service\s+is)\s+(?:operating|working|operational)\b", text))


def ticket_requested(user_messages: list[str]) -> bool:
    return any(re.search(r"\b(?:ticket|support\s+request)\b", text, re.I) for text in user_messages)


SECRET_PATTERNS = [
    r"\b(?:my\s+)?(?:password|passcode|recovery\s*code|api[_ -]?key)\s*(?:is|=|:)\s*\S+",
    r"\bsk-[A-Za-z0-9_-]{12,}\b",
]


def contains_secret(value: str) -> bool:
    return any(re.search(pattern, value, re.I) for pattern in SECRET_PATTERNS)


def prepare_ticket(
    *, problem_description: str, steps_tried: list[str], category: str,
    user_id: str, thread_id: str, status_profile: str,
    checked_status: str | None = None, only_if_operational: bool = False,
    reference_ids: list[str] | None = None, storage_dir: str | Path = "local-storage",
) -> dict:
    """Save locally. The model never selects identity, profile or claimed steps."""
    category = normalize_topic(category)
    if category is None:
        return {"result": "needs_information", "message": "Is the issue Wi-Fi or password recovery?", "file_path": None}
    if not problem_description.strip() or not steps_tried:
        return {"result": "needs_information", "message": "What problem are you having, and what have you already tried?", "file_path": None}
    if any(contains_secret(text) for text in [problem_description, *steps_tried]):
        return {"result": "blocked", "message": "Remove passwords, recovery codes, and API keys.", "file_path": None}
    if only_if_operational and checked_status != "operational":
        return {"result": "skipped", "message": "Conditional ticket not created; service is not confirmed operational.",
                "service_status": checked_status or "not_checked", "file_path": None}
    template = load_json("data/ticket_template.json")["ticket"].copy()
    ticket_id = "DEMO-" + uuid.uuid4().hex[:12]
    ticket = {
        **template,
        "ticket_id": ticket_id,
        "status": "draft",
        "user_id": user_id, "thread_id": thread_id, "category": category,
        "summary": problem_description.strip(),
        "steps_tried": list(dict.fromkeys(steps_tried)),
        "service_status": checked_status or "not_checked",
        "status_profile": status_profile,
        "reference_ids": list(dict.fromkeys(reference_ids or [])),
    }
    directory = Path(storage_dir) / "tickets"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (ticket_id + ".json")
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"ticket": ticket}, handle, indent=2, ensure_ascii=False)
    return {"result": "draft_created", "message": "Local draft saved; nothing was sent.",
            "ticket_id": ticket_id, "file_path": str(path), "ticket": ticket}
