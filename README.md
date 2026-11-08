# CSS-4007 HW5 — University IT Helpdesk with LangGraph

**Author:** Ulyana Timofeyeva  
**Course:** CSS-4007 Artificial Intelligence  
**Environment:** Python 3.11+ (the included CI uses Python 3.11). Designed for Google Colab too.

## What I built

The terminal app implements all four HW5 parts. Part 1 is a fixed LangGraph with Wi-Fi/password/other routing and a second version with clarification. Parts 2–3 use a LangGraph model/tool loop, `ToolNode`, fictional reference JSON, local ticket drafts, SQLite conversation checkpoints, and a separate SQLite preference database. Part 4 adds pytest and GitHub Actions. Inputs are fictional; no real IT ticket is submitted.

## Install

```bash
python --version
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Top-level library versions are pinned in `requirements.txt`. Run `python -m pip freeze` to see the complete transitive dependency set installed in your environment. The code was designed for the pinned versions; verify the install in your own runtime.

## Run locally without API key (offline fake model)

```bash
python -m pytest -q
python -m helpdesk_app.cli part1 --scenario S04
python -m helpdesk_app.cli part1 --scenario S05
python -m helpdesk_app.cli message --user demo-user-a --thread demo-1 --profile normal --text "Show me Wi-Fi troubleshooting steps." --mode offline
python run_scenarios.py --mode offline
python generate_submission.py
```

**Warning:** `--mode offline` is a deterministic **fake model** for repeatable tests, not an OpenAI LLM. Tool calls are still processed through LangGraph `ToolNode`. Never cite offline runs as real LLM evidence.

## Run the real OpenAI LLM demonstration

Copy `.env.example` to `.env`, set `OPENAI_API_KEY` and `MODEL_NAME=gpt-4.1-mini` (or a model with tool calling available to your account). `.env` is ignored by Git. OpenAI API use may cost money.

```bash
python -m helpdesk_app.cli message --user demo-user-a --thread live-demo --profile normal --text "Show me the Wi-Fi troubleshooting steps." --mode real
python run_scenarios.py --mode real --ids S06 S07 S08 S09 S14
# To run the real model on ALL supplied scenarios:
python run_scenarios.py --mode real
python generate_submission.py
```

If a real-model scenario fails, its saved log must be inspected. Do not change assertions merely to show PASS. The exact generated wording is nondeterministic.

## Persistent memory and process restart

- Conversation checkpoint: `local-storage/{mode}/{scenario}/conversations.sqlite` (LangGraph `SqliteSaver`). For manual message calls the default is `local-storage/conversations.sqlite`.
- User preference: `local-storage/{mode}/{scenario}/preferences.sqlite`, indexed by `user_id`. It is **separate** from thread history.
- Ticket drafts: `local-storage/{mode}/{scenario}/tickets/*.json`.
- `thread_id` identifies one conversation; `user_id` identifies the user. The app stores messages under `user_id::thread_id` to avoid cross-user contamination.
- To reset: delete the whole `local-storage/` directory. **Do not commit local-storage**.

`run_scenarios.py` launches **one fresh Python subprocess for each message** (so every second message comes after an actual process exit). It does not replay earlier messages into new inputs. For S11/S12, it follows the explicit `restart_process` events while preserving the same SQLite files. Commands and separate launches are recorded in the traces.

## Exact scenarios and logs

- Run `python run_scenarios.py --mode offline` to produce `outputs/offline/S01.json` to `S14.json`.
- Run `python run_scenarios.py --mode real` with API configured to produce `outputs/real/S01.json` to `S14.json`.
- The two modes' logs are never mixed, and scenario `passed` fields are calculated from observed results.
- `python generate_submission.py` updates `SUBMISSION.md` from **existing** log files; missing real runs stay `Not run`.

Fixture meanings, requirements, and scenario ordering are from the starter's `SCENARIOS.md` and `data/README.md`.

## Tests and CI

```bash
python -m pytest -q
```

Tests check original/updated routes, tools, ticket policy, SQLite persistence after a **new process**, and separation between user IDs and threads. No API key is needed. `.github/workflows/tests.yml` runs these tests on every push or pull request. The offline model is explicitly labelled as fake; real LLM runs are separate.

## GitHub submission

Keep the fork public and push all `.py`, `.md`, `.json` fixtures, `requirements.txt`, `.github/workflows/tests.yml`, notebook and small synthetic `outputs/` traces. Do **not** upload `.env`, API keys, `local-storage/`, or SQLite DBs. Confirm CI is green and submit the fork URL in the course LMS.
