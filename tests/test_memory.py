import json
import subprocess
import sys
from helpdesk_app.fixtures import ROOT
from helpdesk_app.memory import UserMemory, checkpoint_thread_id


def send_turn(storage_dir, user, thread, message, profile="normal"):
    """Run in an entirely new Python process to test disk checkpoint recovery."""
    command = [sys.executable, "-m", "helpdesk_app.cli", "message",
               "--user", user, "--thread", thread, "--text", message,
               "--profile", profile, "--mode", "offline",
               "--storage-dir", str(storage_dir)]
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_conversation_persists_across_process_restart(tmp_path):
    first = send_turn(tmp_path, "demo-user-a", "same-thread", "I cannot connect to Wi-Fi. I enabled it and tried reconnecting.")
    second = send_turn(tmp_path, "demo-user-a", "same-thread", "Which steps did I already try?")
    assert first["history_messages_before"] == 0
    assert second["history_messages_before"] > 0
    assert "enabled" in second["final_answer"].lower()
    assert "reconnect" in second["final_answer"].lower()


def test_user_preference_shared_only_across_own_threads(tmp_path):
    send_turn(tmp_path, "demo-user-a", "first", "Please remember that I prefer replies in Kazakh. I have a Wi-Fi problem.")
    same_user = send_turn(tmp_path, "demo-user-a", "second", "Which language did I ask you to use?")
    other_user = send_turn(tmp_path, "demo-user-b", "first", "Have I told you a preferred language or a previous problem?")
    assert same_user["history_messages_before"] == 0
    assert same_user["stored_language_before"] == "Kazakh"
    assert other_user["stored_language_before"] is None
    assert other_user["history_messages_before"] == 0
    assert UserMemory(tmp_path).get_language("demo-user-a") == "Kazakh"
    assert UserMemory(tmp_path).get_language("demo-user-b") is None


def test_same_thread_name_does_not_cross_user_boundary(tmp_path):
    send_turn(tmp_path, "demo-user-a", "shared-name", "My issue is Wi-Fi. I enabled it.")
    other = send_turn(tmp_path, "demo-user-b", "shared-name", "Have I told you a preferred language or a previous problem?")
    assert checkpoint_thread_id("demo-user-a", "shared-name") != checkpoint_thread_id("demo-user-b", "shared-name")
    assert other["history_messages_before"] == 0


def test_scenario_s09_multi_turn(tmp_path):
    first = send_turn(tmp_path, "demo-user-a", "s09", "Prepare a support ticket.")
    second = send_turn(tmp_path, "demo-user-a", "s09", "The issue is Wi-Fi. I enabled it and tried reconnecting, but it still fails.")
    assert not first["tickets"]
    assert second["tickets"]
    assert second["history_messages_before"] > 0


def test_offline_s06_s07_s08_status_drives_action(tmp_path):
    base = "I enabled Wi-Fi and forgot the saved network, but Campus-Demo still will not connect. Check whether Wi-Fi is down. If it is operating, prepare a ticket about this problem."
    normal = send_turn(tmp_path / "normal", "demo-user-a", "normal", base, "normal")
    down = send_turn(tmp_path / "down", "demo-user-a", "down", base, "wifi_outage")
    unknown = send_turn(tmp_path / "unknown", "demo-user-a", "unknown", base, "status_unavailable")
    assert normal["tickets"]
    assert not down["tickets"]
    assert not unknown["tickets"]


def test_offline_account_recovery_outage(tmp_path):
    result = send_turn(tmp_path, "demo-user-a", "s14", "My password recovery page is unavailable. Check the service status. Is there a known problem?", "recovery_outage")
    status_calls = [x for x in result["tool_results"] if x["tool"] == "check_service_status"]
    assert status_calls and status_calls[0]["result"]["service"] == "account_recovery"
    assert status_calls[0]["result"]["status"] == "outage"
