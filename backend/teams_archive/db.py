from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 2
ACTIVE_RUN_STATES = ("queued", "running", "paused", "interrupted")

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_info (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY, display_name TEXT NOT NULL, description TEXT,
    tenant_id TEXT, is_archived INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY, team_id TEXT NOT NULL REFERENCES teams(id),
    display_name TEXT NOT NULL, description TEXT,
    membership_type TEXT NOT NULL DEFAULT 'unknown', web_url TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL,
    source_locator TEXT, identity_confidence TEXT NOT NULL DEFAULT 'name_fingerprint',
    last_capture_status TEXT, last_captured_at TEXT
);
CREATE TABLE IF NOT EXISTS selected_channels (
    channel_id TEXT PRIMARY KEY REFERENCES channels(id) ON DELETE CASCADE,
    selected INTEGER NOT NULL DEFAULT 1 CHECK(selected IN (0, 1)), updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY, team_id TEXT NOT NULL REFERENCES teams(id),
    channel_id TEXT NOT NULL REFERENCES channels(id), parent_id TEXT REFERENCES messages(id),
    author_name TEXT NOT NULL DEFAULT 'Không rõ', subject TEXT,
    body_html TEXT NOT NULL DEFAULT '', body_text TEXT NOT NULL DEFAULT '',
    created_at TEXT, modified_at TEXT, deleted_at TEXT, etag TEXT,
    raw_json TEXT NOT NULL DEFAULT '{}', archived_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_channel_created ON messages(channel_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_parent ON messages(parent_id, created_at ASC);
CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
    subject, body_text, author_name, content='messages', content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO message_fts(rowid, subject, body_text, author_name)
    VALUES (new.rowid, new.subject, new.body_text, new.author_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO message_fts(message_fts, rowid, subject, body_text, author_name)
    VALUES ('delete', old.rowid, old.subject, old.body_text, old.author_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO message_fts(message_fts, rowid, subject, body_text, author_name)
    VALUES ('delete', old.rowid, old.subject, old.body_text, old.author_name);
    INSERT INTO message_fts(rowid, subject, body_text, author_name)
    VALUES (new.rowid, new.subject, new.body_text, new.author_name);
END;
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY, message_id TEXT REFERENCES messages(id),
    channel_id TEXT NOT NULL REFERENCES channels(id), source_drive_id TEXT,
    source_item_id TEXT, source_etag TEXT, name TEXT NOT NULL, mime_type TEXT,
    size_bytes INTEGER, source_url TEXT, google_file_id TEXT, google_web_url TEXT,
    local_cache_path TEXT, status TEXT NOT NULL DEFAULT 'pending', error_code TEXT,
    updated_at TEXT NOT NULL, capture_mode TEXT NOT NULL DEFAULT 'download'
);
CREATE TABLE IF NOT EXISTS hosted_assets (
    id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id),
    mime_type TEXT, local_path TEXT NOT NULL, size_bytes INTEGER,
    archived_at TEXT NOT NULL, source_url TEXT,
    capture_mode TEXT NOT NULL DEFAULT 'original'
);
CREATE TABLE IF NOT EXISTS capture_runs (
    id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL, current_channel_id TEXT REFERENCES channels(id),
    summary_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS capture_channel_runs (
    run_id TEXT NOT NULL REFERENCES capture_runs(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL REFERENCES channels(id), status TEXT NOT NULL,
    posts_seen INTEGER NOT NULL DEFAULT 0, posts_completed INTEGER NOT NULL DEFAULT 0,
    expected_replies INTEGER NOT NULL DEFAULT 0, captured_replies INTEGER NOT NULL DEFAULT 0,
    files_captured INTEGER NOT NULL DEFAULT 0, error_code TEXT, error_message TEXT,
    updated_at TEXT NOT NULL, PRIMARY KEY(run_id, channel_id)
);
CREATE TABLE IF NOT EXISTS capture_post_runs (
    run_id TEXT NOT NULL REFERENCES capture_runs(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL REFERENCES channels(id), post_id TEXT NOT NULL,
    status TEXT NOT NULL, expected_replies INTEGER NOT NULL DEFAULT 0,
    captured_replies INTEGER NOT NULL DEFAULT 0, count_matches INTEGER,
    updated_at TEXT NOT NULL, PRIMARY KEY(run_id, post_id)
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArchiveDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_column(connection, "channels", "source_locator", "TEXT")
            self._ensure_column(connection, "channels", "identity_confidence", "TEXT NOT NULL DEFAULT 'name_fingerprint'")
            self._ensure_column(connection, "channels", "last_capture_status", "TEXT")
            self._ensure_column(connection, "channels", "last_captured_at", "TEXT")
            self._ensure_column(connection, "attachments", "capture_mode", "TEXT NOT NULL DEFAULT 'download'")
            self._ensure_column(connection, "hosted_assets", "source_url", "TEXT")
            self._ensure_column(connection, "hosted_assets", "capture_mode", "TEXT NOT NULL DEFAULT 'original'")
            row = connection.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_info(version) VALUES (?)", (SCHEMA_VERSION,))
            elif row["version"] > SCHEMA_VERSION:
                raise RuntimeError(f"Unsupported database schema {row['version']}; expected <= {SCHEMA_VERSION}")
            else:
                connection.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION,))
            connection.execute("UPDATE capture_runs SET status='interrupted' WHERE status='running'")
            connection.execute("UPDATE capture_channel_runs SET status='interrupted', updated_at=? WHERE status='running'", (utc_now(),))

    def set_setting(self, key: str, value: Any) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at""",
                (key, json.dumps(value, ensure_ascii=False), utc_now()),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as connection:
            row = connection.execute("SELECT value_json FROM app_settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value_json"]) if row else default

    def upsert_channel(self, item: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO teams(id, display_name, raw_json, updated_at) VALUES (?, ?, '{}', ?)
                   ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name, updated_at=excluded.updated_at""",
                (item["teamId"], item["teamName"], now),
            )
            connection.execute(
                """INSERT INTO channels(
                       id, team_id, display_name, membership_type, web_url, raw_json,
                       updated_at, source_locator, identity_confidence
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                     membership_type=excluded.membership_type, web_url=excluded.web_url,
                     raw_json=excluded.raw_json, source_locator=excluded.source_locator,
                     identity_confidence=excluded.identity_confidence, updated_at=excluded.updated_at""",
                (
                    item["id"], item["teamId"], item["displayName"], item.get("membershipType", "unknown"),
                    item.get("webUrl"), json.dumps(item, ensure_ascii=False), now,
                    item.get("sourceLocator"), item.get("identityConfidence", "name_fingerprint"),
                ),
            )
            connection.execute(
                """INSERT INTO selected_channels(channel_id, selected, updated_at) VALUES (?, 1, ?)
                   ON CONFLICT(channel_id) DO UPDATE SET selected=1, updated_at=excluded.updated_at""",
                (item["id"], now),
            )
        return self.get_channel(item["id"])

    def get_channel(self, channel_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT c.*, t.display_name team_name, COALESCE(s.selected, 0) selected
                   FROM channels c JOIN teams t ON t.id=c.team_id
                   LEFT JOIN selected_channels s ON s.channel_id=c.id WHERE c.id=?""",
                (channel_id,),
            ).fetchone()
        if not row:
            raise KeyError(channel_id)
        return dict(row)

    def list_channels(self, selected_only: bool = True) -> list[dict[str, Any]]:
        where = "WHERE COALESCE(s.selected, 0)=1" if selected_only else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"""SELECT c.id, c.display_name displayName, c.membership_type membershipType,
                    c.identity_confidence identityConfidence, c.last_capture_status lastCaptureStatus,
                    c.last_captured_at lastCapturedAt, t.id teamId, t.display_name teamName,
                    COALESCE(s.selected, 0) selected
                    FROM channels c JOIN teams t ON t.id=c.team_id
                    LEFT JOIN selected_channels s ON s.channel_id=c.id {where}
                    ORDER BY t.display_name, c.display_name"""
            ).fetchall()
        return [dict(row) for row in rows]

    def deselect_channel(self, channel_id: str) -> bool:
        with self.connect() as connection:
            result = connection.execute(
                "UPDATE selected_channels SET selected=0, updated_at=? WHERE channel_id=? AND selected=1",
                (utc_now(), channel_id),
            )
        return result.rowcount > 0

    def create_capture_run(self, channel_ids: list[str]) -> str:
        run_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as connection:
            active = connection.execute(
                "SELECT id FROM capture_runs WHERE status IN ('queued','running','paused') LIMIT 1"
            ).fetchone()
            if active:
                raise RuntimeError("capture-already-active")
            connection.execute(
                "INSERT INTO capture_runs(id, started_at, status) VALUES (?, ?, 'queued')", (run_id, now)
            )
            connection.executemany(
                """INSERT INTO capture_channel_runs(run_id, channel_id, status, updated_at)
                   VALUES (?, ?, 'queued', ?)""",
                [(run_id, channel_id, now) for channel_id in channel_ids],
            )
        return run_id

    def update_run(self, run_id: str, status: str, *, current_channel_id: str | None = None, summary: dict | None = None) -> None:
        finished = utc_now() if status in {"completed", "partial", "failed"} else None
        with self.connect() as connection:
            connection.execute(
                """UPDATE capture_runs SET status=?, current_channel_id=?,
                   summary_json=COALESCE(?, summary_json), finished_at=COALESCE(?, finished_at) WHERE id=?""",
                (status, current_channel_id, json.dumps(summary, ensure_ascii=False) if summary is not None else None, finished, run_id),
            )

    def update_channel_run(self, run_id: str, channel_id: str, **values: Any) -> None:
        allowed = {"status", "posts_seen", "posts_completed", "expected_replies", "captured_replies", "files_captured", "error_code", "error_message"}
        selected = {key: value for key, value in values.items() if key in allowed}
        selected["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in selected)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE capture_channel_runs SET {assignments} WHERE run_id=? AND channel_id=?",
                (*selected.values(), run_id, channel_id),
            )

    def completed_post_ids(self, run_id: str) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT post_id FROM capture_post_runs WHERE run_id=? AND status='completed'", (run_id,)
            ).fetchall()
        return {row["post_id"] for row in rows}

    def upsert_post(self, run_id: str, channel_id: str, post: dict[str, Any]) -> None:
        channel = self.get_channel(channel_id)
        now = utc_now()
        messages = post.get("messages", [])
        if not messages:
            raise ValueError("captured post has no messages")
        root_id = post["id"]
        with self.connect() as connection:
            for index, message in enumerate(messages):
                message_id = message.get("id") or f"{root_id}:deleted:{index}"
                parent_id = None if index == 0 else root_id
                connection.execute(
                    """INSERT INTO messages(
                           id, team_id, channel_id, parent_id, author_name, subject,
                           body_html, body_text, created_at, deleted_at, raw_json, archived_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,
                         author_name=excluded.author_name, subject=excluded.subject,
                         body_html=excluded.body_html, body_text=excluded.body_text,
                         created_at=excluded.created_at, deleted_at=excluded.deleted_at,
                         raw_json=excluded.raw_json, archived_at=excluded.archived_at""",
                    (
                        message_id, channel["team_id"], channel_id, parent_id,
                        message.get("author") or "Không rõ", message.get("subject") or None,
                        message.get("html") or "", message.get("text") or "",
                        message.get("timestamp"), now if message.get("deleted") else None,
                        json.dumps(message, ensure_ascii=False), now,
                    ),
                )
                for attachment in message.get("attachments", []):
                    connection.execute(
                        """INSERT INTO attachments(
                               id, message_id, channel_id, name, source_url, local_cache_path,
                               status, error_code, updated_at, capture_mode
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                             source_url=excluded.source_url, local_cache_path=excluded.local_cache_path,
                             status=excluded.status, error_code=excluded.error_code,
                             updated_at=excluded.updated_at, capture_mode=excluded.capture_mode""",
                        (
                            attachment["id"], message_id, channel_id, attachment.get("name") or "Tệp đính kèm",
                            attachment.get("url"), attachment.get("localPath"), attachment.get("status", "pending"),
                            attachment.get("errorCode"), now, attachment.get("captureMode", "download"),
                        ),
                    )
                for asset in message.get("images", []):
                    if not asset.get("localPath"):
                        continue
                    connection.execute(
                        """INSERT INTO hosted_assets(
                               id, message_id, mime_type, local_path, size_bytes, archived_at,
                               source_url, capture_mode
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET local_path=excluded.local_path,
                             size_bytes=excluded.size_bytes, archived_at=excluded.archived_at,
                             source_url=excluded.source_url, capture_mode=excluded.capture_mode""",
                        (
                            asset["id"], message_id, asset.get("mimeType"), asset["localPath"],
                            asset.get("sizeBytes"), now, asset.get("src"), asset.get("captureMode", "original"),
                        ),
                    )
            connection.execute(
                """INSERT INTO capture_post_runs(
                       run_id, channel_id, post_id, status, expected_replies,
                       captured_replies, count_matches, updated_at
                   ) VALUES (?, ?, ?, 'completed', ?, ?, ?, ?)
                   ON CONFLICT(run_id, post_id) DO UPDATE SET status='completed',
                     expected_replies=excluded.expected_replies,
                     captured_replies=excluded.captured_replies,
                     count_matches=excluded.count_matches, updated_at=excluded.updated_at""",
                (
                    run_id, channel_id, root_id, post.get("expectedReplies", 0),
                    post.get("capturedReplies", 0), int(bool(post.get("countMatches"))), now,
                ),
            )

    def current_capture(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            run = connection.execute(
                "SELECT * FROM capture_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if not run:
                return None
            channels = connection.execute(
                """SELECT r.*, c.display_name displayName, t.display_name teamName
                   FROM capture_channel_runs r JOIN channels c ON c.id=r.channel_id
                   JOIN teams t ON t.id=c.team_id WHERE r.run_id=? ORDER BY r.rowid""",
                (run["id"],),
            ).fetchall()
        result = dict(run)
        result["summary"] = json.loads(result.pop("summary_json"))
        result["channels"] = [dict(row) for row in channels]
        return result

    def capture_channel_ids(self, run_id: str) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT channel_id FROM capture_channel_runs WHERE run_id=? ORDER BY rowid", (run_id,)
            ).fetchall()
        return [row["channel_id"] for row in rows]

    @staticmethod
    def _fts_query(query: str) -> str:
        return '"' + query.replace('"', '""') + '"'

    def list_posts(self, query: str = "", channel_id: str | None = None, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        params: list[Any] = []
        filters = ["root.parent_id IS NULL"]
        if channel_id:
            filters.append("root.channel_id=?")
            params.append(channel_id)
        if query.strip():
            root_source = """SELECT DISTINCT COALESCE(m.parent_id, m.id) root_id
                FROM message_fts JOIN messages m ON m.rowid=message_fts.rowid
                WHERE message_fts MATCH ?"""
            params.insert(0, self._fts_query(query.strip()))
            filters.append("root.id IN (SELECT root_id FROM matched)")
            cte = f"WITH matched AS ({root_source})"
        else:
            cte = ""
        sql = f"""{cte}
            SELECT root.id, root.subject, root.body_text bodyText, root.author_name authorName,
                   root.created_at createdAt, c.display_name channelName, t.display_name teamName,
                   (SELECT COUNT(*) FROM messages r WHERE r.parent_id=root.id) replyCount,
                   (SELECT COUNT(*) FROM attachments a WHERE a.message_id=root.id OR a.message_id IN
                     (SELECT id FROM messages r2 WHERE r2.parent_id=root.id)) attachmentCount
            FROM messages root JOIN channels c ON c.id=root.channel_id
            JOIN teams t ON t.id=root.team_id WHERE {' AND '.join(filters)}
            ORDER BY root.created_at DESC LIMIT ? OFFSET ?"""
        params.extend([limit + 1, offset])
        with self.connect() as connection:
            rows = [dict(row) for row in connection.execute(sql, params).fetchall()]
        has_more = len(rows) > limit
        return {"items": rows[:limit], "nextCursor": str(offset + limit) if has_more else None}

    def get_post(self, root_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT m.*, c.display_name channelName, t.display_name teamName
                   FROM messages m JOIN channels c ON c.id=m.channel_id JOIN teams t ON t.id=m.team_id
                   WHERE m.id=? OR m.parent_id=? ORDER BY CASE WHEN m.id=? THEN 0 ELSE 1 END, m.created_at""",
                (root_id, root_id, root_id),
            ).fetchall()
            if not rows:
                return None
            message_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in message_ids)
            attachments = connection.execute(
                f"SELECT * FROM attachments WHERE message_id IN ({placeholders}) ORDER BY name", message_ids
            ).fetchall()
        messages = [dict(row) for row in rows]
        return {"root": messages[0], "replies": messages[1:], "attachments": [dict(row) for row in attachments]}

    def get_attachment(self, attachment_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
        return dict(row) if row else None
