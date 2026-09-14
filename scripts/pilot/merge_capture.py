#!/usr/bin/env python3
"""Atomically merge a channel capture into a durable pilot checkpoint."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def merge(existing: dict | None, incoming: dict) -> tuple[dict, dict]:
    if existing and existing.get("source", {}).get("channel") != incoming.get("source", {}).get("channel"):
        raise ValueError("Checkpoint belongs to a different Teams channel")

    previous_posts = {post["id"]: post for post in (existing or {}).get("posts", []) if post.get("id")}
    incoming_posts = {post["id"]: post for post in incoming.get("posts", []) if post.get("id")}
    added = len(set(incoming_posts) - set(previous_posts))
    updated = len(set(incoming_posts) & set(previous_posts))
    previous_posts.update(incoming_posts)
    posts = sorted(previous_posts.values(), key=lambda post: int(post["id"]))

    result = {
        "schemaVersion": 1,
        "source": incoming.get("source") or (existing or {}).get("source"),
        "lastCapturedAt": incoming.get("capturedAt"),
        "posts": posts,
    }
    messages = [message for post in posts for message in post.get("messages", [])]
    result["evidence"] = {
        "capturedPosts": len(posts),
        "expectedReplies": sum(post.get("expectedReplies", 0) for post in posts),
        "capturedReplies": sum(post.get("capturedReplies", 0) for post in posts),
        "postsWithMatchingReplyCount": sum(bool(post.get("countMatches")) for post in posts),
        "attachmentReferences": sum(len(message.get("attachments", [])) for message in messages),
        "embeddedImages": sum(len(message.get("images", [])) for message in messages),
    }
    stats = {"added": added, "updated": updated, "total": len(posts)}
    return result, stats


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("incoming", type=Path)
    parser.add_argument("checkpoint", type=Path)
    args = parser.parse_args()

    incoming = json.loads(args.incoming.read_text(encoding="utf-8"))
    existing = json.loads(args.checkpoint.read_text(encoding="utf-8")) if args.checkpoint.exists() else None
    result, stats = merge(existing, incoming)
    write_atomic(args.checkpoint, result)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
