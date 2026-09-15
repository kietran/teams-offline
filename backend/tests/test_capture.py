from teams_archive.capture.extractor import FORBIDDEN_ACTION_NAMES, safe_filename, stable_hash, storage_key, team_from_title
from teams_archive.capture.service import sanitize_post


def test_capture_helpers_are_stable_and_cross_platform_safe() -> None:
    assert stable_hash("A", "B") == stable_hash("A", "B")
    assert storage_key("ui-channel:abc") == storage_key("ui-channel:abc")
    assert len(storage_key("ui-channel:abc")) == 32
    assert all(character in "0123456789abcdef" for character in storage_key("ui-channel:abc"))
    assert safe_filename('a<b>:c?.pdf') == "a_b__c_.pdf"
    assert team_from_title("Teams and Channels | Client | Legal | Microsoft Teams", "Legal") == "Client"


def test_message_html_is_sanitized_before_storage() -> None:
    captured = {
        "messages": [{
            "html": (
                '<p onclick="bad()">Safe<script>bad()</script>'
                '<a href="javascript:bad()">bad link</a>'
                '<a href="https://example.com" target="_blank">good link</a></p>'
            )
        }]
    }
    result = sanitize_post(captured)
    sanitized = result["messages"][0]["html"]
    assert "<script" not in sanitized
    assert "onclick" not in sanitized
    assert "javascript:" not in sanitized
    assert "Safe" in sanitized
    assert 'href="https://example.com"' in sanitized


def test_forbidden_write_actions_are_explicitly_owned() -> None:
    assert {"send", "share", "edit", "delete", "reply in thread"} <= FORBIDDEN_ACTION_NAMES
