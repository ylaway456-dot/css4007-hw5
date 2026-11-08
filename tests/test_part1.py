from helpdesk_app.part1 import PREDICTIONS, run_part1
from helpdesk_app.fixtures import get_scenario


def test_all_original_and_updated_routes():
    for scenario_id, predicted in PREDICTIONS.items():
        scenario = get_scenario(scenario_id)
        report = run_part1(scenario["events"][0]["message"], scenario_id,
                           with_clarification=scenario_id == "S05")
        assert report["actual_route"] == predicted
        assert report["final_state"]["message"] == scenario["events"][0]["message"]
        assert report["trace"][0]["node"] == "read_request"
        assert report["trace"][-1]["state_after"]["reply"]


def test_original_wifi_priority_and_changed_clarification():
    original = run_part1("My Wi-Fi password does not work.", "S04")
    updated = run_part1("My Wi-Fi password does not work.", "S05", True)
    assert original["actual_route"] == ["read_request", "wifi_help"]
    assert updated["actual_route"] == ["read_request", "clarify_problem"]


def test_password_is_case_insensitive():
    assert run_part1("I forgot my PASSWORD.", "S02")["final_state"]["category"] == "password"
