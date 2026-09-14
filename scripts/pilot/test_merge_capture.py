import unittest

from merge_capture import merge


def capture(channel: str, posts: list[dict]) -> dict:
    return {"capturedAt": "2026-09-14T00:00:00Z", "source": {"channel": channel}, "posts": posts}


class MergeCaptureTests(unittest.TestCase):
    def test_rerun_updates_without_duplicate(self) -> None:
        post = {
            "id": "1000",
            "expectedReplies": 1,
            "capturedReplies": 1,
            "countMatches": True,
            "messages": [{"attachments": [], "images": []}],
        }
        first, first_stats = merge(None, capture("Channel A", [post]))
        second, second_stats = merge(first, capture("Channel A", [post]))

        self.assertEqual(first_stats, {"added": 1, "updated": 0, "total": 1})
        self.assertEqual(second_stats, {"added": 0, "updated": 1, "total": 1})
        self.assertEqual(len(second["posts"]), 1)

    def test_rejects_different_channel(self) -> None:
        existing, _ = merge(None, capture("Channel A", []))
        with self.assertRaisesRegex(ValueError, "different Teams channel"):
            merge(existing, capture("Channel B", []))


if __name__ == "__main__":
    unittest.main()
