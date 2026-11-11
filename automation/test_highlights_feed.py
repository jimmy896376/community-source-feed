#!/usr/bin/env python3
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import highlights_feed


class FeedRecoveryTests(unittest.TestCase):
    def test_failed_channel_keeps_recent_candidates_and_scans_others(self):
        channel_id = next(iter(highlights_feed.CHANNELS))
        old_video = {
            "video_id": "AbCdEf12345",
            "title": "Example FC vs Sample United Highlights",
            "channel_id": channel_id,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "url": "https://www.youtube.com/watch?v=AbCdEf12345",
        }
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request.full_url)
            if channel_id in request.full_url:
                raise URLError("temporary failure")
            return io.BytesIO(b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>')

        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            try:
                os.chdir(directory)
                Path("highlights.json").write_text(json.dumps({"videos": [old_video]}))
                with patch.object(highlights_feed.urllib.request, "urlopen", side_effect=fake_urlopen):
                    result = highlights_feed.collect()
            finally:
                os.chdir(previous)

        self.assertEqual([video["video_id"] for video in result["videos"]], [old_video["video_id"]])
        self.assertEqual(len(calls), len(highlights_feed.CHANNELS))


if __name__ == "__main__":
    unittest.main()
