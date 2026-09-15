import sqlite3
from pathlib import Path

from teams_archive.db import ArchiveDatabase, SCHEMA_VERSION


def channel() -> dict:
    return {
        "id": "ui-channel:one", "teamId": "ui-team:one", "teamName": "Client",
        "displayName": "Legal", "membershipType": "shared", "webUrl": "https://teams.cloud.microsoft/",
        "sourceLocator": "19:channel@thread.tacv2", "identityConfidence": "source_id",
    }


def post(subject: str = "Cập nhật báo giá") -> dict:
    return {
        "id": "1000", "expectedReplies": 1, "capturedReplies": 1, "countMatches": True,
        "messages": [
            {"id": "1000", "author": "Lan", "subject": subject, "text": "Dự án Minh Phát", "html": "<p>Dự án Minh Phát</p>", "timestamp": "2026-09-14T00:00:00Z", "attachments": [], "images": []},
            {"id": "1001", "author": "Nam", "text": "Đã đồng ý", "html": "<p>Đã đồng ý</p>", "timestamp": "2026-09-14T00:01:00Z", "attachments": [], "images": []},
        ],
    }


def test_schema_v1_migrates_without_losing_settings(tmp_path: Path) -> None:
    path = tmp_path / "archive.db"
    connection = sqlite3.connect(path)
    connection.executescript("CREATE TABLE schema_info(version INTEGER NOT NULL); INSERT INTO schema_info VALUES(1); CREATE TABLE app_settings(key TEXT PRIMARY KEY,value_json TEXT NOT NULL,updated_at TEXT NOT NULL);")
    connection.execute("INSERT INTO app_settings VALUES('legacy','true','now')")
    connection.commit(); connection.close()
    db = ArchiveDatabase(path); db.initialize()
    with db.connect() as current:
        assert current.execute("SELECT version FROM schema_info").fetchone()[0] == SCHEMA_VERSION
    assert db.get_setting("legacy") is True


def test_capture_upsert_search_and_rerun_are_idempotent(tmp_path: Path) -> None:
    db = ArchiveDatabase(tmp_path / "archive.db"); db.initialize(); db.upsert_channel(channel())
    run_id = db.create_capture_run([channel()["id"]])
    db.upsert_post(run_id, channel()["id"], post())
    db.upsert_post(run_id, channel()["id"], post("Tiêu đề mới"))
    results = db.list_posts("đồng ý")
    assert len(results["items"]) == 1
    assert results["items"][0]["id"] == "1000"
    detail = db.get_post("1000")
    assert detail and len(detail["replies"]) == 1
    assert detail["root"]["subject"] == "Tiêu đề mới"


def test_initialization_marks_running_capture_interrupted(tmp_path: Path) -> None:
    db = ArchiveDatabase(tmp_path / "archive.db"); db.initialize(); db.upsert_channel(channel())
    run_id = db.create_capture_run([channel()["id"]]); db.update_run(run_id, "running")
    db.initialize()
    assert db.current_capture()["status"] == "interrupted"


def test_post_uses_summary_id_as_canonical_root(tmp_path: Path) -> None:
    db = ArchiveDatabase(tmp_path / "archive.db"); db.initialize(); db.upsert_channel(channel())
    run_id = db.create_capture_run([channel()["id"]])
    captured = post()
    captured["messages"][0]["id"] = "reply-pane-rendered-first"

    db.upsert_post(run_id, channel()["id"], captured)

    detail = db.get_post("1000")
    assert detail is not None
    assert detail["root"]["id"] == "1000"
    assert detail["replies"][0]["parent_id"] == "1000"


def test_matching_rerun_replaces_stale_synthetic_tombstones(tmp_path: Path) -> None:
    db = ArchiveDatabase(tmp_path / "archive.db"); db.initialize(); db.upsert_channel(channel())
    run_id = db.create_capture_run([channel()["id"]])
    captured = post()
    captured.update({"expectedReplies": 2, "capturedReplies": 2, "countMatches": True})
    captured["messages"] = [
        captured["messages"][0],
        {"id": None, "captureKey": "after:1000:1", "deleted": True, "attachments": [], "images": []},
        {"id": None, "captureKey": "after:1000:2", "deleted": True, "attachments": [], "images": []},
    ]
    db.upsert_post(run_id, channel()["id"], captured)

    captured["messages"][1]["captureKey"] = "before:1001:2"
    captured["messages"][2]["captureKey"] = "before:1001:1"
    db.upsert_post(run_id, channel()["id"], captured)

    detail = db.get_post("1000")
    assert detail is not None
    assert len(detail["replies"]) == 2
