"""Parts 2-3: LLM/ToolNode loop + SQLite conversation and user memory."""
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite import SqliteSaver

from .fixtures import normalize_topic, normalize_service, helpdesk_data
from .memory import UserMemory, checkpoint_thread_id, parse_language_preference
from .tools import (find_instructions as direct_instructions,
                    check_service_status as direct_status,
                    prepare_ticket as direct_ticket,
                    extract_claimed_steps, get_last_problem_message,
                    conditional_ticket_requested, ticket_requested, contains_secret)

SYSTEM_PROMPT = """You are a student helpdesk assistant using FICTIONAL local exercise data.
The application supplies the user identity, conversation thread, saved language and fixed service snapshot.
Use the provided tools rather than inventing instructions or service status.
Use find_instructions for troubleshooting instructions.
Use check_service_status to answer whether Wi-Fi or account_recovery is operating.
For conditional tickets, check the correct service first. Only prepare a ticket when status is operational.
If status is outage or unknown, do NOT call prepare_ticket for a conditional request.
Unknown is not operational. Do not make up a repair time.
When the user requests a ticket but no topic or tried steps are known, ask for these details.
Once a user gives missing details in a follow-up, use the conversation history and create a LOCAL draft.
Do not invent steps, store passwords or secret codes, or claim a ticket was sent.
For a user preference, reply in the saved language when feasible.
Keep replies concise and clearly describe the source of service facts.
"""


@dataclass
class RequestContext:
    user_id: str
    thread_id: str
    profile: str
    storage_dir: Path
    user_messages: list[str]
    language: str | None
    checked_services: dict[str, str] = field(default_factory=dict)
    reference_ids: list[str] = field(default_factory=list)

    @property
    def category(self) -> str | None:
        for text in reversed(self.user_messages):
            topic = normalize_topic(text)
            if topic:
                return topic
        return None

    @property
    def steps(self) -> list[str]:
        return extract_claimed_steps(self.user_messages)

    @property
    def has_ticket_request(self) -> bool:
        return ticket_requested(self.user_messages)

    @property
    def is_conditional(self) -> bool:
        return conditional_ticket_requested(self.user_messages)


def build_tools(ctx: RequestContext):
    @tool("find_instructions")
    def instructions_tool(topic: str) -> dict:
        """Fetch instructions for a Wi-Fi or password problem from the fictional reference guide."""
        result = direct_instructions(topic)
        if "instruction_id" in result and result["instruction_id"] not in ctx.reference_ids:
            ctx.reference_ids.append(result["instruction_id"])
        return result

    @tool("check_service_status")
    def status_tool(service: str) -> dict:
        """Check demo Wi-Fi or account recovery status. The app selects the status snapshot."""
        result = direct_status(service, ctx.profile)
        if "status" in result:
            ctx.checked_services[result["service"]] = result["status"]
        return result

    @tool("prepare_ticket")
    def ticket_tool() -> dict:
        """Create a local draft ticket from USER-stated problem and steps; no arguments needed.
        For conditional requests, first call check_service_status and get operational.
        The tool itself enforces the identity, steps and status rules.
        """
        if not ctx.has_ticket_request:
            return {"result": "skipped", "message": "The user has not requested a ticket.", "file_path": None}
        category = ctx.category
        if category is None:
            return {"result": "needs_information", "message": "Is your issue Wi-Fi or password recovery?", "file_path": None}
        if not ctx.steps:
            return {"result": "needs_information", "message": "What troubleshooting steps did you try?", "file_path": None}
        service = helpdesk_data()["topic_services"][category]
        known_status = ctx.checked_services.get(service)
        if ctx.is_conditional and known_status != "operational":
            return {"result": "skipped", "message": "Condition not confirmed; check status first.",
                    "service_status": known_status or "not_checked", "file_path": None}
        description = get_last_problem_message(ctx.user_messages)
        if not description:
            return {"result": "needs_information", "message": "Please describe the actual problem.", "file_path": None}
        return direct_ticket(
            problem_description=description, steps_tried=ctx.steps,
            category=category, user_id=ctx.user_id, thread_id=ctx.thread_id,
            status_profile=ctx.profile, checked_status=known_status,
            only_if_operational=ctx.is_conditional, reference_ids=ctx.reference_ids,
            storage_dir=ctx.storage_dir,
        )

    return [instructions_tool, status_tool, ticket_tool]


def _fake_tool_call(name: str, args: dict) -> AIMessage:
    """Clearly marked deterministic TEST SUBSTITUTE, never presented as a real LLM."""
    import uuid
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": args,
        "id": "offline_" + uuid.uuid4().hex[:12], "type": "tool_call"
    }])


def offline_fake_model(messages: list, ctx: RequestContext) -> AIMessage:
    """Rule-based simulated model for offline CI; it issues genuine ToolNode requests."""
    latest = ctx.user_messages[-1].casefold()
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    this_turn = messages[last_human + 1:]
    used_tools = [m.name for m in this_turn if isinstance(m, ToolMessage)]
    ticket_results = []
    for msg in this_turn:
        if isinstance(msg, ToolMessage) and msg.name == "prepare_ticket":
            try:
                ticket_results.append(json.loads(msg.content))
            except (ValueError, TypeError):
                pass
    if ticket_results:
        ticket = ticket_results[-1]
        if ticket.get("result") == "draft_created":
            return AIMessage(content="I saved a local ticket draft at " + ticket["file_path"] + ". Nothing was sent.")
        return AIMessage(content=ticket.get("message", "No draft was created."))

    if re.search(r"which (?:problem|steps)|what (?:did|have) (?:we|i) (?:discuss|try)", latest):
        steps = ctx.steps
        topic = ctx.category
        if topic and steps:
            return AIMessage(content=f"We discussed your {topic} issue. You tried: " + "; ".join(steps) + ".")
        return AIMessage(content="I do not have enough earlier details in this conversation.")

    if "which language" in latest or "preferred language" in latest:
        if ctx.language == "Kazakh":
            return AIMessage(content="Сіз жауаптарды қазақ тілінде алуды сұрадыңыз. Мен Wi-Fi және құпиясөз бойынша көмектесе аламын.")
        if ctx.language:
            return AIMessage(content=f"You asked me to reply in {ctx.language}.")
        return AIMessage(content="You have not saved a language preference for this user.")

    if "have i told you" in latest or "previous problem" in latest:
        if not ctx.language and not ctx.category:
            return AIMessage(content="No preferred language or previous problem has been recorded for this user.")

    needs_instructions = (
        "instructions" in latest or "troubleshooting steps" in latest
        or ("wi-fi problem" in latest and not ctx.has_ticket_request)
        or ("cannot connect" in latest and not ctx.has_ticket_request)
    )
    needs_status = (
        "check whether" in latest or "check the service status" in latest
        or "is it down" in latest or "known problem" in latest
        or ctx.is_conditional
    )
    if needs_instructions and "find_instructions" not in used_tools and ctx.category:
        return _fake_tool_call("find_instructions", {"topic": ctx.category})

    if needs_status and "check_service_status" not in used_tools and ctx.category:
        service = helpdesk_data()["topic_services"][ctx.category]
        return _fake_tool_call("check_service_status", {"service": service})

    if ctx.has_ticket_request:
        if ctx.category is None or not ctx.steps:
            return AIMessage(content="What problem are you having, and what have you already tried?")
        if ctx.is_conditional:
            service = helpdesk_data()["topic_services"][ctx.category]
            service_status = ctx.checked_services.get(service)
            if service_status == "outage":
                return AIMessage(content="The demo service has a known outage. I did not create a conditional ticket. No repair time was provided.")
            if service_status == "unknown":
                return AIMessage(content="The service status is unknown, not operational. I did not create the conditional ticket. Would you like a draft describing this?")
        if "prepare_ticket" not in used_tools:
            return _fake_tool_call("prepare_ticket", {})

    if ctx.language == "Kazakh" and "remember" in latest:
        return AIMessage(content="Қазақ тіліндегі жауап қалауыңыз сақталды. Сұрағыңызды алдым.")
    if "check_service_status" in used_tools:
        service = helpdesk_data()["topic_services"].get(ctx.category or "wifi", "wifi")
        status = ctx.checked_services.get(service, "unknown")
        return AIMessage(content=f"The fictional {service} status is {status}. No repair time is provided.")
    if "find_instructions" in used_tools:
        guide = direct_instructions(ctx.category or "")
        return AIMessage(content=guide.get("title", "Helpdesk") + ": " + " ".join(guide.get("steps", [])))
    return AIMessage(content="I can help with the fictional Wi-Fi and password-recovery services.")



def _system_message(ctx: RequestContext) -> SystemMessage:
    pref = ctx.language or "not saved"

    text = SYSTEM_PROMPT + (
        f"\nSaved language preference for this user: {pref}."
    )

    latest = (
        ctx.user_messages[-1].casefold()
        if ctx.user_messages else ""
    )

    # Check if the user asks about previous actions
    recall_question = any(
        phrase in latest
        for phrase in [
            "which problem",
            "which steps",
            "what did we discuss",
            "what did i try"
        ]
    )

    if recall_question:
        # Read only previous USER messages
        earlier_messages = ctx.user_messages[:-1]

        reported_steps = extract_claimed_steps(
            earlier_messages
        )

        reported_topics = [
            normalize_topic(message)
            for message in earlier_messages
        ]

        category = next(
            (topic for topic in reversed(reported_topics) if topic),
            None
        )

        text += (
            "\nMemory recall task. "
            "Use only actions explicitly reported by the USER. "
            "Do not confuse completed actions with instructions "
            "previously suggested by the assistant. "
            f"Earlier problem: {category or 'not recorded'}. "
            f"Steps actually tried: {reported_steps!r}. "
            "Do not invent additional steps. "
            "Answer in the user's saved language."
        )

    return SystemMessage(content=text)



def build_agent(ctx: RequestContext, checkpointer, mode: str = "offline"):
    tools = build_tools(ctx)
    if mode == "real":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is missing. Configure a Colab Secret or .env file.")
        from langchain_openai import ChatOpenAI
        model_name = os.environ.get("MODEL_NAME", "gpt-4.1-mini")
        model = ChatOpenAI(model=model_name, temperature=0).bind_tools(tools, parallel_tool_calls=False)
    elif mode != "offline":
        raise ValueError("mode must be offline or real")

    def call_model(state: MessagesState):
        messages = state["messages"]
        if mode == "offline":
            response = offline_fake_model(messages, ctx)
        else:
            response = model.invoke([_system_message(ctx), *messages])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("llm", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", tools_condition)
    builder.add_edge("tools", "llm")
    return builder.compile(checkpointer=checkpointer)


def run_message(message: str, *, user_id: str, thread_id: str, profile: str,
                storage_dir: str | Path, mode: str = "offline") -> dict:
    """One process invocation: read persisted state, perform a turn, save its trace."""
    storage_dir = Path(storage_dir).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    memory = UserMemory(storage_dir)
    preference_before = memory.get_language(user_id)
    new_preference = parse_language_preference(message)
    if new_preference:
        memory.set_language(user_id, new_preference)
    language = memory.get_language(user_id)

    # Refuse secrets rather than retaining them in messages/checkpoints/logs.
    if contains_secret(message):
        return {"error": "Message includes a secret. Remove it and retry.",
                "user_id": user_id, "thread_id": thread_id, "final_answer": "Please remove credentials."}

    checkpoint_file = storage_dir / "conversations.sqlite"
    config = {"configurable": {"thread_id": checkpoint_thread_id(user_id, thread_id)},
              "recursion_limit": 16}
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
    with SqliteSaver.from_conn_string(str(checkpoint_file)) as saver:
        ctx = RequestContext(user_id=user_id, thread_id=thread_id, profile=profile,
                             storage_dir=storage_dir, user_messages=[message], language=language)
        graph = build_agent(ctx, saver, mode=mode)
        previous = graph.get_state(config).values
        previous_messages = previous.get("messages", [])
        old_humans = [m.content for m in previous_messages if isinstance(m, HumanMessage) and isinstance(m.content, str)]
        ctx.user_messages = old_humans + [message]
        for m in previous_messages:
            if isinstance(m, ToolMessage) and m.name == "find_instructions":
                try:
                    reference_id = json.loads(m.content).get("instruction_id")
                    if reference_id and reference_id not in ctx.reference_ids:
                        ctx.reference_ids.append(reference_id)
                except (ValueError, TypeError):
                    pass
        trace, tool_calls, tool_results = [], [], []
        final_answer = ""
        for event in graph.stream({"messages": [HumanMessage(content=message)]},
                                  config=config, stream_mode="updates"):
            for node_name, update in event.items():
                observed = []
                for msg in update.get("messages", []):
                    if isinstance(msg, AIMessage):
                        if msg.content:
                            final_answer = str(msg.content)
                        for call in msg.tool_calls:
                            tool_calls.append({"tool": call["name"], "args": call.get("args", {})})
                            observed.append({"tool_request": call["name"], "args": call.get("args", {})})
                    elif isinstance(msg, ToolMessage):
                        value = msg.content
                        try:
                            value = json.loads(value) if isinstance(value, str) else value
                        except (ValueError, TypeError):
                            pass
                        tool_results.append({"tool": msg.name, "result": value})
                        observed.append({"tool_result": msg.name, "result": value})
                trace.append({"node": node_name, "updates": observed})
        current = graph.get_state(config).values
        current_messages = current.get("messages", [])
        source_names = sorted(set(
            (["data/helpdesk.json"] if any(t["tool"] == "find_instructions" for t in tool_results) else [])
            + (["data/service_status.json"] if any(t["tool"] == "check_service_status" for t in tool_results) else [])
            + (["conversation_checkpoint"] if previous_messages else [])
            + (["user_preference_memory"] if preference_before else [])
        ))
        return {
            "mode": "real_openai_llm" if mode == "real" else "offline_fake_model_NOT_REAL_LLM",
            "provider": "OpenAI" if mode == "real" else "deterministic_fake_for_tests",
            "model": os.environ.get("MODEL_NAME", "gpt-4.1-mini") if mode == "real" else "offline_rules",
            "status_profile": profile, "user_id": user_id, "thread_id": thread_id,
            "message": message, "history_messages_before": len(previous_messages),
            "checkpoint_thread_key": checkpoint_thread_id(user_id, thread_id),
            "stored_language_before": preference_before,
            "stored_language_after": language,
            "read_sources": source_names,
            "visited_nodes": [x["node"] for x in trace],
            "trace": trace, "tool_calls": tool_calls, "tool_results": tool_results,
            "final_answer": final_answer, "saved_message_count": len(current_messages),
            "loop_limit": 16, "loop_limit_reached": False,
            "tickets": [x["result"].get("file_path") for x in tool_results
                        if x["tool"] == "prepare_ticket" and isinstance(x["result"], dict)
                        and x["result"].get("file_path")],
        }
