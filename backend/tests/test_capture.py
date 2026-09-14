from teams_archive.capture.extractor import FORBIDDEN_ACTION_NAMES, safe_filename, stable_hash, team_from_title
from teams_archive.capture.service import sanitize_post


def test_capture_helpers_are_stable_and_cross_platform_safe() -> None:
    assert stable_hash("A", "B") == stable_hash("A", "B")
    assert safe_filename('a<b>:c?.pdf') == "a_b__c_.pdf"
    assert team_from_title("Teams and Channels | Client | Legal | Microsoft Teams", "Legal") == "Client"


def test_message_html_is_sanitized_before_storage() -> None:
    captured = {"messages": [{"html": '<p onclick="bad()">Safe<script>bad()</script></p>'}]}
    result = sanitize_post(captured)
    assert "script" not in result["messages"][0]["html"]
    assert "onclick" not in result["messages"][0]["html"]
    assert "Safe" in result["messages"][0]["html"]


def test_forbidden_write_actions_are_explicitly_owned() -> None:
    assert {"send", "share", "edit", "delete", "reply in thread"} <= FORBIDDEN_ACTION_NAMES
