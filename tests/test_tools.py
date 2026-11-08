import json
from pathlib import Path
from helpdesk_app.tools import (find_instructions, check_service_status,
                                prepare_ticket, extract_claimed_steps, contains_secret)


def test_find_instructions_handles_long_topic():
    data = find_instructions("Wi-Fi troubleshooting steps")
    assert data["instruction_id"] == "GUIDE-WIFI"
    assert data["source"] == "data/helpdesk.json"
    assert len(data["steps"]) == 4


def test_unknown_instructions_do_not_invent():
    assert "error" in find_instructions("printer and mouse")


def test_each_snapshot_and_recovery_service():
    assert check_service_status("Campus-Demo Wi-Fi", "normal")["status"] == "operational"
    assert check_service_status("Wi-Fi service", "wifi_outage")["status"] == "outage"
    assert check_service_status("wifi", "status_unavailable")["status"] == "unknown"
    entry = check_service_status("password recovery", "recovery_outage")
    assert entry["service"] == "account_recovery" and entry["status"] == "outage"


def _call_ticket(tmp_path, **overrides):
    values = dict(problem_description="Wi-Fi still fails", steps_tried=["Enabled Wi-Fi"],
                  category="wifi", user_id="demo-user-a", thread_id="test-1",
                  status_profile="normal", checked_status="operational",
                  only_if_operational=True, reference_ids=["GUIDE-WIFI"],
                  storage_dir=tmp_path)
    values.update(overrides)
    return prepare_ticket(**values)


def test_ticket_contains_only_user_steps_and_is_local(tmp_path):
    result = _call_ticket(tmp_path)
    assert result["result"] == "draft_created"
    path = Path(result["file_path"])
    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))["ticket"]
    assert saved["steps_tried"] == ["Enabled Wi-Fi"]
    assert saved["status"] == "draft"
    assert saved["reference_ids"] == ["GUIDE-WIFI"]


def test_conditional_ticket_never_created_when_down_or_unknown(tmp_path):
    for status in ["outage", "unknown", None]:
        result = _call_ticket(tmp_path, checked_status=status)
        assert result["result"] == "skipped"
    assert list(tmp_path.glob("tickets/*.json")) == []


def test_missing_information_does_not_create_draft(tmp_path):
    result = _call_ticket(tmp_path, steps_tried=[])
    assert result["result"] == "needs_information"
    assert list(tmp_path.glob("tickets/*.json")) == []


def test_secrets_are_rejected(tmp_path):
    assert contains_secret("my password is ABC123")
    result = _call_ticket(tmp_path, problem_description="my password is ABC123")
    assert result["result"] == "blocked"


def test_extract_user_steps_only_when_claimed():
    assert extract_claimed_steps(["Show Wi-Fi instructions."]) == []
    steps = extract_claimed_steps(["I enabled Wi-Fi and forgot the saved network."])
    assert steps == ["Enabled Wi-Fi", "Forgot the saved network"]
