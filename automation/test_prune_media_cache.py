import unittest
from datetime import datetime, timedelta, timezone

from prune_media_cache import expired_assets


class MediaCachePruneTests(unittest.TestCase):
    def test_keeps_current_and_recent_assets(self):
        now = datetime(2026, 11, 23, tzinfo=timezone.utc)
        current = "a" * 64
        old = "b" * 64
        recent = "c" * 64
        feed = {"posts": [{"images": [{"digest": current}]}]}
        assets = [
            {"id": 1, "name": current, "created_at": (now - timedelta(days=4)).isoformat()},
            {"id": 2, "name": old, "created_at": (now - timedelta(days=3)).isoformat()},
            {"id": 3, "name": recent, "created_at": (now - timedelta(hours=4)).isoformat()},
            {"id": 4, "name": "release-notes", "created_at": (now - timedelta(days=3)).isoformat()},
        ]
        self.assertEqual(expired_assets(feed, assets, now), [2])


if __name__ == "__main__":
    unittest.main()
