#!/usr/bin/env python3
"""Render a pilot capture JSON as an offline HTML preview and count report."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def escaped_text(value: str | None) -> str:
    return html.escape(value or "").replace("\n", "<br>")


def render_message(message: dict, is_root: bool) -> str:
    label = "Bài viết" if is_root else "Bình luận"
    attachments = "".join(
        f'<li>{html.escape(item.get("name") or "Tệp đính kèm")}</li>'
        for item in message.get("attachments", [])
    )
    attachment_block = f'<ul class="attachments">{attachments}</ul>' if attachments else ""
    return f"""
      <article class="message {'root' if is_root else 'reply'}">
        <div class="meta"><span>{label} · {html.escape(message.get('author') or 'Không rõ')}</span>
        <time>{html.escape(message.get('timestampLabel') or message.get('timestamp') or '')}</time></div>
        {f'<h2>{html.escape(message.get("subject") or "Không có tiêu đề")}</h2>' if is_root else ''}
        <p>{escaped_text(message.get('text'))}</p>
        {attachment_block}
      </article>
    """


def render_document(payload: dict) -> str:
    posts = []
    for index, post in enumerate(payload.get("posts", []), start=1):
        messages = post.get("messages", [])
        body = "".join(render_message(message, offset == 0) for offset, message in enumerate(messages))
        posts.append(
            f"""
            <section class="thread">
              <div class="thread-count">Thread {index} · {post.get('capturedReplies', 0)} bình luận</div>
              {body}
            </section>
            """
        )

    evidence = payload.get("evidence", {})
    channel = payload.get("source", {}).get("channel") or "Kênh Teams"
    summary = (
        f"{evidence.get('capturedPosts', 0)} bài viết · "
        f"{evidence.get('capturedReplies', 0)} bình luận · "
        f"{evidence.get('attachmentReferences', 0)} tệp tham chiếu · "
        f"{evidence.get('embeddedImages', 0)} ảnh"
    )
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(channel)} — Pilot capture</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, "Segoe UI", "Noto Sans", sans-serif; color: #1e293b; background: #f8fafc; }}
    * {{ box-sizing: border-box; }} body {{ margin: 0; }}
    header {{ position: sticky; top: 0; background: rgba(255,255,255,.96); border-bottom: 1px solid #e2e8f0; padding: 20px 28px; }}
    header h1 {{ margin: 0 0 6px; font-size: 24px; }} header p {{ margin: 0; color: #64748b; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 28px; }}
    .thread {{ background: white; border: 1px solid #e2e8f0; border-radius: 10px; margin-bottom: 24px; overflow: hidden; }}
    .thread-count {{ padding: 12px 18px; background: #eff6ff; color: #1d4ed8; font-weight: 600; }}
    .message {{ padding: 18px; border-top: 1px solid #e2e8f0; }} .message:first-of-type {{ border-top: 0; }}
    .message.reply {{ margin-left: 28px; border-left: 3px solid #dbeafe; }}
    .meta {{ display: flex; justify-content: space-between; gap: 16px; color: #64748b; font-size: 14px; }}
    h2 {{ margin: 10px 0; font-size: 19px; }} p {{ margin: 10px 0 0; line-height: 1.6; overflow-wrap: anywhere; }}
    .attachments {{ margin: 14px 0 0; padding-left: 20px; color: #334155; }}
  </style>
</head>
<body>
  <header><h1>{html.escape(channel)}</h1><p>{html.escape(summary)}</p></header>
  <main>{''.join(posts)}</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_json", type=Path)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.capture_json.read_text(encoding="utf-8"))
    args.html.write_text(render_document(payload), encoding="utf-8")
    report = {
        "schemaVersion": payload.get("schemaVersion"),
        "capturedAt": payload.get("capturedAt"),
        "source": payload.get("source"),
        "evidence": payload.get("evidence"),
        "errors": payload.get("errors", []),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
