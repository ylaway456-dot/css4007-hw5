"""Terminal entry point. Run: python -m helpdesk_app.cli --help"""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from .fixtures import get_scenario
from .part1 import run_part1
from .assistant import run_message


def main():
    load_dotenv()
    os.environ["LANGSMITH_TRACING"] = "false"
    parser = argparse.ArgumentParser(description="Fictional university helpdesk HW5")
    subs = parser.add_subparsers(dest="command", required=True)
    part1 = subs.add_parser("part1", help="Run one S01-S05 route")
    part1.add_argument("--scenario", required=True, choices=[f"S{i:02}" for i in range(1, 6)])
    msg = subs.add_parser("message", help="Send one turn with explicit identity/profile")
    msg.add_argument("--user", required=True)
    msg.add_argument("--thread", required=True)
    msg.add_argument("--profile", default="normal")
    msg.add_argument("--text", required=True)
    msg.add_argument("--mode", choices=["offline", "real"], default="offline")
    msg.add_argument("--storage-dir", default="local-storage")
    ev = subs.add_parser("event", help="Run exactly one event from the JSON fixtures")
    ev.add_argument("--scenario", required=True)
    ev.add_argument("--index", type=int, required=True)
    ev.add_argument("--mode", choices=["offline", "real"], default="offline")
    ev.add_argument("--storage-dir", default="local-storage")
    args = parser.parse_args()
    if args.command == "part1":
        s = get_scenario(args.scenario)
        result = run_part1(s["events"][0]["message"], args.scenario,
                           with_clarification=args.scenario == "S05")
    elif args.command == "message":
        result = run_message(args.text, user_id=args.user, thread_id=args.thread,
                             profile=args.profile, storage_dir=args.storage_dir, mode=args.mode)
    else:
        s = get_scenario(args.scenario)
        event = s["events"][args.index]
        if event["action"] != "message":
            raise ValueError("Only message events can be executed as a turn")
        result = run_message(event["message"], user_id=event["user_id"],
                             thread_id=event["thread_id"], profile=s["status_profile"],
                             storage_dir=args.storage_dir, mode=args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
