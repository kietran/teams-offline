# Chrome Channel Capture Pilot

This directory contains development-only Playwright CLI functions used to
inspect the rendered Teams web interface. Real capture output belongs outside
the repository under the user's application-data directory.

## Extract the currently open thread

With the named persistent Chrome session already open and a thread expanded:

```bash
PLAYWRIGHT_CLI_SESSION=teams-channel-pilot \
  /home/kitkit/.codex/skills/playwright/scripts/playwright_cli.sh \
  --raw run-code --filename scripts/pilot/extract_open_thread.js \
  > /home/kitkit/.local/share/teams-offline-archive/pilot/capture/open-thread.json
```

The function scrolls the reply viewport toward the oldest reply until the
rendered message count stabilizes, then captures the root post, replies,
attachments, embedded-image metadata, and count evidence.

It does not submit forms, post messages, extract bearer tokens, or call an
undocumented Teams endpoint.

## Capture the open channel (pilot cap: 20 posts)

Close any open reply pane, keep the channel Posts view visible, then run:

```bash
PLAYWRIGHT_CLI_SESSION=teams-channel-pilot \
  /home/kitkit/.codex/skills/playwright/scripts/playwright_cli.sh \
  --raw run-code --filename scripts/pilot/capture_channel_20.js \
  > /home/kitkit/.local/share/teams-offline-archive/pilot/capture/channel-20.json
```

The pilot starts from the newest rendered region, walks toward older posts,
opens reply panes, waits for reply counts to stabilize, and stops after 20 root
posts. Real channels in the accepted scope typically contain only 1–5 root
posts; the higher cap protects the pilot from an unexpectedly large channel.
It returns evidence separately from captured content.

## Merge into a durable checkpoint

```bash
python3 scripts/pilot/merge_capture.py \
  /home/kitkit/.local/share/teams-offline-archive/pilot/capture/channel-20.json \
  /home/kitkit/.local/share/teams-offline-archive/pilot/capture/checkpoint.json
```

Rerunning the command for the same channel replaces matching post IDs instead
of appending duplicates. The checkpoint is written atomically.

## Render an offline preview

```bash
python3 scripts/pilot/render_capture.py \
  /home/kitkit/.local/share/teams-offline-archive/pilot/capture/channel-20.json \
  --html /home/kitkit/.local/share/teams-offline-archive/pilot/capture/preview.html \
  --report /home/kitkit/.local/share/teams-offline-archive/pilot/capture/report.json
```
