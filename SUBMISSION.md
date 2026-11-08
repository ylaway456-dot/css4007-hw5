# CSS-4007 HW5 — Submission

**Student:** Ulyana Timofeyeva  
**Project:** University IT Helpdesk with LangGraph

## Part 1 — Graph without an LLM

I started with a simple graph that checks a user's message and chooses one of three topics: Wi-Fi, password, or other. I used a `HelpdeskState` with `message`, `category`, and `reply`.

At first my graph had these routes:

```text
START → read_request → wifi_help / password_help / other_help → END
```

In S04, the message had both Wi-Fi and password. My code chose Wi-Fi because I checked that word first. Then I added `clarify_problem`, so in S05 the graph asks which issue the user means.

```text
START → read_request → wifi_help / password_help / other_help / clarify_problem → END
```

I predicted the paths before testing and compared them with the saved results:

| Scenario | My prediction | Actual route | Result |
|---|---|---|---|
| S01 | `read_request → wifi_help` | `read_request → wifi_help` | PASS |
| S02 | `read_request → password_help` | `read_request → password_help` | PASS |
| S03 | `read_request → other_help` | `read_request → other_help` | PASS |
| S04 | `read_request → wifi_help` | `read_request → wifi_help` | PASS |
| S05 | `read_request → clarify_problem` | `read_request → clarify_problem` | PASS |

The main thing I learned here is that a node changes the state, while a conditional edge decides which node runs next. I did not use an LLM in this part.

## Part 2 — LLM and tools

Next, I connected an OpenAI model to LangGraph. Instead of choosing a route with `if` conditions, the model can request a tool. `ToolNode` runs that tool and returns the result. The model then continues with that information.

I used these three tools:

- `find_instructions` reads the Wi-Fi or password guide from `data/helpdesk.json`.
- `check_service_status` reads the selected service status from `data/service_status.json`.
- `prepare_ticket` makes a local JSON draft using `data/ticket_template.json`. It does not send anything.

The graph works like this:

```text
START → llm → tools → llm → END
```

It can go back from `tools` to `llm` when another step is needed. I set `recursion_limit=16` to stop a very long loop.

For S06, the assistant found the instructions, checked that Wi-Fi was working, and made a ticket draft using the steps the user reported. For S07 and S08, it did not make the conditional ticket because Wi-Fi was down or the status was unknown. In S09 it asked for missing details. In S14 it checked account recovery rather than Wi-Fi.

I tested the Python tools with an offline test model, and I also ran the OpenAI model separately. The offline mode is only for repeatable testing, not a real LLM run. The log files below show the recorded results.

| Scenario | Status profile | Offline | OpenAI model | Log files |
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

## Part 3 — Memory

I used SQLite for two different types of memory:

- **Conversation memory:** LangGraph `SqliteSaver` keeps earlier messages in a thread.
- **User memory:** a separate SQLite file saves the user's preferred language using `user_id`.

For conversation history, I use both the user ID and thread ID, so two users do not share the same conversation by mistake.

I tested four situations. S10 checked whether the assistant remembered an earlier message in the same conversation. In S11, I ran the next message in a new Python process and checked whether the stored conversation could still be read. S12 used a new thread but the same user, so the Kazakh language preference was remembered. S13 used another user and confirmed that the preference and previous conversation were not shared.

I had a problem with S11 at first: the model gave a correct Kazakh answer, but my test searched for an English word. I corrected the check for the Kazakh wording and ran S11 again. It passed.

For the restart test I used:

```bash
python run_scenarios.py --mode real --ids S11
```

The recorded commands and memory information are in `outputs/real/S11.json`. I did not copy the old user message into the new input.

## Part 4 — Tests and files

I added tests in the `tests/` folder. They check the graph routes, tool results, ticket conditions, saved memory, and separation between users. These tests work without an OpenAI API key.

My final Colab check showed **17 passed** in pytest. The saved scenario checks also showed **S01–S14 PASS**. The real model was used in Parts 2 and 3; Part 1 used Python rules.

To run the project:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python run_scenarios.py --mode offline
# Real LLM run (requires OPENAI_API_KEY):
python run_scenarios.py --mode real
```

The code is in `helpdesk_app/`, tests are in `tests/`, and the recorded runs are in `outputs/`. I also prepared `.github/workflows/tests.yml` for GitHub Actions. The API key and local SQLite databases should not be uploaded.

## Final result

I built and tested the helpdesk graph, tools, and memory. All 14 scenarios in my saved results passed, and the 17 pytest tests passed in Colab. The project prepares local ticket drafts only; it does not contact a real university helpdesk.

Before submission, I still need to confirm that the GitHub Actions test run is green and that my final notebook is included in the repository.
