#!/usr/bin/env python3
"""Collect public highlight links from Korean sports-rights-holder YouTube channels."""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CHANNELS = {
    "UCnBht7BrOx-A328KFXgysqQ": "쿠팡플레이 스포츠",
    "UCtm_QoN2SIxwCE-59shX7Qg": "SPOTV",
}
ATOM = "{http://www.w3.org/2005/Atom}"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
HIGHLIGHT = re.compile(r"하이라이트|highlights?", re.I)


def collect():
    videos = {}
    for channel_id, channel_name in CHANNELS.items():
        url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id
        request = urllib.request.Request(url, headers={"User-Agent": "NUDETV-Highlight-Feed/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            root = ET.fromstring(response.read())
        for entry in root.findall(ATOM + "entry"):
            raw_id = entry.findtext("{http://www.youtube.com/xml/schemas/2015}videoId", "")
            title = entry.findtext(ATOM + "title", "").strip()
            published = entry.findtext(ATOM + "published", "")
            if not VIDEO_ID.fullmatch(raw_id) or not HIGHLIGHT.search(title):
                continue
            videos[raw_id] = {
                "video_id": raw_id,
                "title": title,
                "channel_id": channel_id,
                "channel": channel_name,
                "published_at": published,
                "url": "https://www.youtube.com/watch?v=" + raw_id,
            }
    ordered = sorted(videos.values(), key=lambda item: item["published_at"], reverse=True)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "videos": ordered[:100]}


if __name__ == "__main__":
    Path("highlights.json").write_text(json.dumps(collect(), ensure_ascii=False, indent=2) + "\n")
