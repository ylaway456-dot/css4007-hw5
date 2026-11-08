# CSS-4007 HW5 — Submission Report

**Project:** University IT Helpdesk with LangGraph
**Student:** Ulyana Timofeyeva
**Python used for report generation:** 3.13.18

## Part 1 — My graph without an LLM

**Original graph:**
```text
START -> read_request -> [wifi_help | password_help | other_help] -> END
```
**Updated graph:**
```text
START -> read_request -> [wifi_help | password_help | other_help | clarify_problem] -> END
```
I store `message`, `category` and `reply` in `HelpdeskState`. The first node reads the message and returns a category update. The conditional edge reads category and chooses a node. The next node receives the current graph state, not only the previous update. START is the entry point, END stops execution, and compile builds an executable graph.

### My predictions compared with saved traces

| Scenario | Predicted route | Actual saved route | Match |
|---|---|---|---|
| S01 | read_request → wifi_help | read_request → wifi_help | PASS |
| S02 | read_request → password_help | read_request → password_help | PASS |
| S03 | read_request → other_help | read_request → other_help | PASS |
| S04 | read_request → wifi_help | read_request → wifi_help | PASS |
| S05 | read_request → clarify_problem | read_request → clarify_problem | PASS |

In S04 both words appear, but my Python code checks Wi-Fi before password. In S05 I changed the routing and added a new clarification node. LangGraph controls the node sequence; Python conditions decide the category. There is no model in Part 1.

## Part 2 — LLM and three tools

**Execution loop:** `START -> llm -> tools -> llm -> ... -> END`. `tools_condition` checks whether the last AI message requests a tool. The LLM requests it; `ToolNode` executes it. Its result becomes a `ToolMessage` in `MessagesState`, and the model reads the result before continuing. The graph has a `recursion_limit=16` (config in `run_message`).

This differs from Part 1 because a real tool-capable model chooses the tool calls. The deterministic offline model is only a clearly labelled test substitute.

- `find_instructions`: reads `data/helpdesk.json`.
- `check_service_status`: reads the selected snapshot in `data/service_status.json`.
- `prepare_ticket`: checks user-stated steps and conditional status; saves only a local draft from `data/ticket_template.json`.

### Measured scenario runs (not examples from SCENARIOS.md)

| ID | Profile | Offline test substitute | Real OpenAI model | Saved logs |
|---|---|---|---|---|
| S01 | normal | PASS | N/A (Part 1 has no LLM) | `outputs/offline/S01.json`, `outputs/real/S01.json` |
| S02 | normal | PASS | N/A (Part 1 has no LLM) | `outputs/offline/S02.json`, `outputs/real/S02.json` |
| S03 | normal | PASS | N/A (Part 1 has no LLM) | `outputs/offline/S03.json`, `outputs/real/S03.json` |
| S04 | normal | PASS | N/A (Part 1 has no LLM) | `outputs/offline/S04.json`, `outputs/real/S04.json` |
| S05 | normal | PASS | N/A (Part 1 has no LLM) | `outputs/offline/S05.json`, `outputs/real/S05.json` |
| S06 | normal | PASS | PASS | `outputs/offline/S06.json`, `outputs/real/S06.json` |
| S07 | wifi_outage | PASS | PASS | `outputs/offline/S07.json`, `outputs/real/S07.json` |
| S08 | status_unavailable | PASS | PASS | `outputs/offline/S08.json`, `outputs/real/S08.json` |
| S09 | normal | PASS | PASS | `outputs/offline/S09.json`, `outputs/real/S09.json` |
| S10 | normal | PASS | PASS | `outputs/offline/S10.json`, `outputs/real/S10.json` |
| S11 | normal | PASS | PASS | `outputs/offline/S11.json`, `outputs/real/S11.json` |
| S12 | normal | PASS | PASS | `outputs/offline/S12.json`, `outputs/real/S12.json` |
| S13 | normal | PASS | PASS | `outputs/offline/S13.json`, `outputs/real/S13.json` |
| S14 | recovery_outage | PASS | PASS | `outputs/offline/S14.json`, `outputs/real/S14.json` |

**Important distinction:** Offline PASS means the Python graph, tools and deterministic fake model passed checks. It does not prove a real LLM selected the tools correctly. The real demonstration is separate and requires OPENAI_API_KEY. Refer to `outputs/real/` for measured LLM tool requests and results; do not claim it ran if there are no files.

S06 uses instructions, status and a local draft. S07 uses `wifi_outage`: a conditional draft must not be created. S08 uses `status_unavailable`: unknown is not operational. S09 asks for missing details before drafting. S14 checks `account_recovery`, not Wi-Fi. Actual behavior is stored in per-event logs, not hard-coded in this report.

## Part 3 — Persistent conversation and user memory

I use LangGraph `SqliteSaver` in `local-storage/.../conversations.sqlite` for conversation history. The application composes its checkpoint key from `user_id::thread_id`, so even an identical thread name does not cross users. I save the language choice separately in `local-storage/.../preferences.sqlite`, indexed by `user_id`.

- S10: a later message in the same thread reads the prior conversation.
- S11: separate Python subprocesses read the same SQLite checkpoint after a genuine restart event.
- S12: the new thread has no prior conversation messages, but the same user's preference remains.
- S13: a different user does not inherit the first user's preference or thread history.

Looking up Wi-Fi instructions is **retrieval** from the reference fixture. Remembering a preferred language is **user memory**. Remembering earlier messages in one thread is **conversation memory**. The trace records the read source.

### Commands for actual restart demonstration

The scenario runner uses `subprocess.run` to launch each turn in a **new Python process**, so a previous CLI process exits before the next turn. It never re-injects the first turn's text into the second turn. Restart events are recorded in `outputs/*/S11.json` and `S12.json`.

```bash
python run_scenarios.py --mode offline --ids S10 S11 S12 S13
# After setting OPENAI_API_KEY, to repeat with the actual model:
python run_scenarios.py --mode real --ids S10 S11 S12 S13
```

## Part 4 — Reproducibility, tests and CI

I supply a terminal CLI (`python -m helpdesk_app.cli`), exact dependencies in requirements.txt, offline pytest tests in `tests/`, and `.github/workflows/tests.yml` that runs pytest after a push. Live SQLite files and API keys are ignored by Git.

The tests catch wrong Wi-Fi/password routing, bad tool aliases, unknown-status-as-working bugs, invented/missing ticket steps, draft creation during outage, failure to persist conversation state, and leaks of preferences or threads between users. They do not use a real LLM or require an API key.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python run_scenarios.py --mode offline
python run_scenarios.py --mode real   # requires a key and can incur API charges
```

**Storage reset:** Delete `local-storage/` to clear preferences, tickets and checkpoints. The outputs folder contains shareable synthetic traces. Never commit real user credentials or .env files.

## Final check before submission

- [ ] Run pytest successfully in Colab or locally.
- [ ] Check the offline scenario table and read any FAIL trace.
- [ ] Run the real LLM examples with API key and inspect `outputs/real`.
- [ ] Make sure all claimed results match saved logs.
- [ ] Push code, requirements, tests, workflow, notebook and logs to my public GitHub fork.
- [ ] Check GitHub Actions for a green test run.
- [ ] Submit the GitHub link on the LMS.
