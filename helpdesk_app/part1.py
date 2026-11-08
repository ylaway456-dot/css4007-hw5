"""Part 1: two versions of a LangGraph with deterministic Python routing."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .fixtures import helpdesk_data


class HelpdeskState(TypedDict):
    message: str
    category: str
    reply: str


def read_request(state: HelpdeskState) -> dict:
    message = state["message"].casefold()
    if "wifi" in message or "wi-fi" in message:
        category = "wifi"
    elif "password" in message:
        category = "password"
    else:
        category = "other"
    return {"category": category}


def read_request_v2(state: HelpdeskState) -> dict:
    message = state["message"].casefold()
    wifi = "wifi" in message or "wi-fi" in message
    password = "password" in message
    if wifi and password:
        category = "clarify"
    elif wifi:
        category = "wifi"
    elif password:
        category = "password"
    else:
        category = "other"
    return {"category": category}


def wifi_help(state: HelpdeskState) -> dict:
    guide = helpdesk_data()["instructions"]["wifi"]
    return {"reply": f"{guide['title']}\n" + "\n".join(guide["steps"])}


def password_help(state: HelpdeskState) -> dict:
    guide = helpdesk_data()["instructions"]["password"]
    return {"reply": f"{guide['title']}\n" + "\n".join(guide["steps"])}


def other_help(state: HelpdeskState) -> dict:
    return {"reply": "Is your problem about Wi-Fi or a password?"}


def clarify_problem(state: HelpdeskState) -> dict:
    return {"reply": "Is the problem connecting to Wi-Fi or recovering your account password?"}


def choose_next_node(state: HelpdeskState) -> str:
    return state["category"]


def build_part1_graph(with_clarification: bool = False):
    builder = StateGraph(HelpdeskState)
    builder.add_node("read_request", read_request_v2 if with_clarification else read_request)
    nodes = {"wifi_help": wifi_help, "password_help": password_help, "other_help": other_help}
    if with_clarification:
        nodes["clarify_problem"] = clarify_problem
    for name, function in nodes.items():
        builder.add_node(name, function)
    builder.add_edge(START, "read_request")
    routes = {"wifi": "wifi_help", "password": "password_help", "other": "other_help"}
    if with_clarification:
        routes["clarify"] = "clarify_problem"
    builder.add_conditional_edges("read_request", choose_next_node, routes)
    for name in nodes:
        builder.add_edge(name, END)
    return builder.compile()


PREDICTIONS = {
    "S01": ["read_request", "wifi_help"],
    "S02": ["read_request", "password_help"],
    "S03": ["read_request", "other_help"],
    "S04": ["read_request", "wifi_help"],
    "S05": ["read_request", "clarify_problem"],
}


def run_part1(message: str, scenario_id: str, with_clarification: bool = False) -> dict:
    graph = build_part1_graph(with_clarification)
    state: HelpdeskState = {"message": message, "category": "", "reply": ""}
    trace = []
    for update in graph.stream(state.copy(), stream_mode="updates"):
        for node_name, changed in update.items():
            state.update(changed)
            trace.append({"node": node_name, "update": changed, "state_after": state.copy()})
    route = [step["node"] for step in trace]
    return {
        "scenario": scenario_id, "mode": "python_rules_without_llm",
        "variant": "with_clarification" if with_clarification else "original",
        "message": message, "predicted_route": PREDICTIONS[scenario_id],
        "actual_route": route, "match": route == PREDICTIONS[scenario_id],
        "trace": trace, "final_answer": state["reply"], "final_state": state,
        "sources": ["data/helpdesk.json"],
    }
