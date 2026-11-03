#!/usr/bin/env python3
"""Collect major-match candidates from Korean sports-rights-holder YouTube channels."""
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
# Curated major-club filter. Candidate must name one club in its title.
MAJOR_CLUBS = (
    "바이에른 뮌헨", "바이에른", "Bayern Munich",
    "레알 마드리드", "Real Madrid", "바르셀로나", "FC Barcelona",
    "아틀레티코 마드리드", "Atletico Madrid",
    "파리 생제르맹", "파리생제르맹", "PSG",
    "맨체스터 시티", "Manchester City", "맨체스터 유나이티드", "Manchester United",
    "리버풀", "Liverpool", "아스널", "Arsenal", "첼시", "Chelsea",
    "토트넘", "Tottenham", "유벤투스", "Juventus",
    "인터 밀란", "인터밀란", "Inter Milan", "AC 밀란", "AC Milan",
    "나폴리", "Napoli",
)
MAJOR_MATCH = re.compile("|".join(re.escape(name) for name in MAJOR_CLUBS), re.I)


def is_major_highlight(title):
    return bool(HIGHLIGHT.search(title) and MAJOR_MATCH.search(title))


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
            if not VIDEO_ID.fullmatch(raw_id) or not is_major_highlight(title):
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
