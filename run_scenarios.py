"""Run all real scenario events. A NEW Python process is launched per message."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from helpdesk_app.fixtures import ROOT, get_scenario, scenarios


def execute(command: list[str]) -> dict:
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                             timeout=180, env=os.environ.copy())
    if process.returncode:
        return {"error": process.stderr[-3500:], "returncode": process.returncode,
                "stdout": process.stdout[-800:]}
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"error": "Invalid CLI JSON", "stdout": process.stdout[-1200:]}


def observed_status(result: dict, service: str) -> str | None:
    for item in result.get("tool_results", []):
        value = item.get("result", {})
        if (item.get("tool") == "check_service_status" and isinstance(value, dict)
                and value.get("service") == service):
            return value.get("status")
    return None


def faithful_recall_answer(answer: str) -> bool:
    """Check recalled steps in English or Kazakh."""

    text = answer.casefold()

    has_wifi = any(x in text for x in [
        "wi-fi", "wifi", "wi fi"
    ])

    

    has_enabled = any(x in text for x in [
        "enabled", "turned on", "switched on",
        "қост", "қосып", "қосқан", "қосулы", "қосу"
    ])


    has_reconnect = any(x in text for x in [
        "reconnect", "қайта қос",
        "қайта жалға", "қайта байланыс"
    ])

    invented_steps = any(x in text for x in [
        "airplane mode", "ұшақ режим",
        "campus-demo", "saved network",
        "сақталған жел"
    ])

    return (
        has_wifi
        and has_enabled
        and has_reconnect
        and not invented_steps
    )

def check_scenario(sid: str, turns: list[dict]) -> dict:
    if sid in {"S01", "S02", "S03", "S04", "S05"}:
        return {"route_matches_prediction": bool(turns and turns[0].get("match"))}
    tool_names = [c["tool"] for turn in turns for c in turn.get("tool_calls", [])]
    tickets = [ticket for turn in turns for ticket in turn.get("tickets", [])]
    checks = {}
    if sid == "S06":
        checks = {"three_tools_used": all(t in tool_names for t in
                                         ["find_instructions", "check_service_status", "prepare_ticket"]),
                  "operational_status": observed_status(turns[-1], "wifi") == "operational",
                  "one_or_more_ticket_drafts": bool(tickets)}
    elif sid == "S07":
        checks = {"wifi_outage": observed_status(turns[-1], "wifi") == "outage",
                  "no_ticket_created": not tickets}
    elif sid == "S08":
        checks = {"wifi_unknown": observed_status(turns[-1], "wifi") == "unknown",
                  "no_conditional_ticket": not tickets}
    elif sid == "S09":
        checks = {"first_turn_no_ticket": not turns[0].get("tickets"),
                  "second_turn_ticket": bool(turns[-1].get("tickets")),
                  "prior_history_read": turns[-1].get("history_messages_before", 0) > 0}
    elif sid == "S10":
        checks = {"prior_thread_recovered": turns[-1].get("history_messages_before", 0) > 0,
                  "steps_recalled": "enabled" in turns[-1].get("final_answer", "").lower()}
    elif sid == "S11":
        checks = {
            "thread_recovered_after_restart":
                turns[-1].get("history_messages_before", 0) > 0,

            "preference_stored":
                turns[-1].get("stored_language_before") == "Kazakh",

            "steps_recalled_without_invented_advice":
                faithful_recall_answer(
                    turns[-1].get("final_answer", "")
                )
        }

    elif sid == "S12":
        checks = {"separate_new_thread": turns[-1].get("history_messages_before", -1) == 0,
                  "preference_survives_restart": turns[-1].get("stored_language_before") == "Kazakh"}
    elif sid == "S13":
        checks = {"other_user_has_no_preference": turns[-1].get("stored_language_before") is None,
                  "other_user_has_no_history": turns[-1].get("history_messages_before", -1) == 0}
    elif sid == "S14":
        checks = {"account_recovery_outage": observed_status(turns[-1], "account_recovery") == "outage",
                  "service_status_tool_called": "check_service_status" in tool_names}
    return checks


def run_one(sid: str, mode: str, output_dir: Path, storage_root: Path) -> dict:
    scenario = get_scenario(sid)
    storage = storage_root / sid
    if scenario.get("reset_before") and storage.exists():
        shutil.rmtree(storage)
    storage.mkdir(parents=True, exist_ok=True)
    turns = []
    launches = []
    restart_events = []
    for index, event in enumerate(scenario["events"]):
        if event["action"] == "restart_process":
            restart_events.append({"action": "restart_process", "preserve_local_storage":
                                   event.get("preserve_local_storage", False),
                                   "after_event_index": index - 1,
                                   "description": "Previous CLI subprocess had already exited; next turn launches a fresh one."})
            continue
        if sid in {"S01", "S02", "S03", "S04", "S05"}:
            command = [sys.executable, "-m", "helpdesk_app.cli", "part1", "--scenario", sid]
        else:
            command = [sys.executable, "-m", "helpdesk_app.cli", "event",
                       "--scenario", sid, "--index", str(index),
                       "--mode", mode, "--storage-dir", str(storage)]
        launch = {"event_index": index, "command": command,
                  "fresh_python_subprocess": True}
        launches.append(launch)
        result = execute(command)
        turns.append(result)
        if result.get("error"):
            break
    checks = check_scenario(sid, turns) if turns and not turns[-1].get("error") else {"execution_completed": False}
    log = {
        "scenario": sid, "title": scenario["title"], "part": scenario["part"],
        "status_profile": scenario["status_profile"],
        "mode": "real_openai_llm" if mode == "real" and sid not in {f"S{i:02}" for i in range(1,6)}
                else "offline_fake_model_NOT_REAL_LLM" if sid not in {f"S{i:02}" for i in range(1,6)}
                else "python_rules_without_llm",
        "reset_before": scenario.get("reset_before", False),
        "launches": launches, "restart_events": restart_events,
        "turns": turns, "checks": checks, "passed": bool(checks) and all(checks.values()),
        "note": "Measured run output. Offline mode uses a rule-based substitute, not a real LLM."
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / f"{sid}.json").open("w", encoding="utf-8") as handle:
        json.dump(log, handle, indent=2, ensure_ascii=False)
    return log


def main():
    parser = argparse.ArgumentParser(description="Execute supplied S01-S14 scenarios in fresh subprocesses")
    parser.add_argument("--mode", choices=["offline", "real"], default="offline")
    parser.add_argument("--ids", nargs="*", default=[s["id"] for s in scenarios()])
    args = parser.parse_args()
    output = ROOT / "outputs" / args.mode
    storage_root = ROOT / "local-storage" / args.mode
    failed = []
    for sid in args.ids:
        report = run_one(sid, args.mode, output, storage_root)
        status = "PASS" if report["passed"] else "FAIL"
        print(f"{sid}: {status} | {report['checks']} | outputs/{args.mode}/{sid}.json", flush=True)
        if not report["passed"]:
            failed.append(sid)
    print(f"\nScenarios: {len(args.ids)-len(failed)}/{len(args.ids)} passed ({args.mode} mode)")
    if failed:
        print("Failed:", ", ".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
