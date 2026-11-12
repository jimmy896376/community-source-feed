#!/usr/bin/env python3
"""Collect major-match candidates from official sports-rights-holder YouTube channels."""
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHANNELS = {
    "UCnBht7BrOx-A328KFXgysqQ": "쿠팡플레이 스포츠",
    "UCtm_QoN2SIxwCE-59shX7Qg": "SPOTV",
    "UCWJ2lWNubArHWmf3FIHbfcQ": "NBA",
    "UCoVz66yWHzVsXAFG8WhJK9g": "KBO",
    "UCG5qGWdu8nIRZqJ_GgDwQ-w": "Premier League",
    "UC6UL29enLNe4mqwTfAyeNuw": "Bundesliga",
    "UCTv-XvfzLX3i4IGWAm4sbmA": "LaLiga",
    "UCoLrcjPV5PbUrUyXq5mjc_A": "MLB",
    "UCak5ZEX4BjijJcf7fdppuIQ": "K League",
    "UC-QIqPAffXGJVgy_tnn145w": "KOVO",
    "UCyGa1YEx9ST66rYrJTGIKOw": "UEFA",
    "UCpcTrCXblq78GZrTUTLWeBw": "FIFA",
}
ATOM = "{http://www.w3.org/2005/Atom}"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
HIGHLIGHT = re.compile(r"하이라이트|highlights?", re.I)
MAJOR_EVENT = re.compile(r"한국시리즈|Korean Series|NBA (?:Finals|Cup|Playoffs|Postseason)|네이션스리그|Nations League|World Cup|FIFA World Cup|UEFA Euro|Euro 20\\d{2}|Copa America|Copa América|Asian Cup|아시안컵|Africa Cup of Nations|AFCON|Gold Cup|국가대표|International Friendly|International Match|National Team", re.I)
# Curated popular teams. Candidate title must name one unless it is a major final/tournament.
MAJOR_TEAMS = (
    # Football
    "바이에른 뮌헨", "바이에른", "Bayern Munich",
    "레알 마드리드", "Real Madrid", "바르셀로나", "FC Barcelona",
    "아틀레티코 마드리드", "Atletico Madrid",
    "파리 생제르맹", "파리생제르맹", "PSG",
    "맨체스터 시티", "Manchester City", "맨체스터 유나이티드", "Manchester United",
    "리버풀", "Liverpool", "아스널", "Arsenal", "첼시", "Chelsea",
    "토트넘", "Tottenham", "유벤투스", "Juventus",
    "인터 밀란", "인터밀란", "Inter Milan", "AC 밀란", "AC Milan",
    "나폴리", "Napoli",
    # Baseball
    "KIA 타이거즈", "KIA", "삼성 라이온즈", "삼성", "LG 트윈스", "두산 베어스",
    "롯데 자이언츠", "한화 이글스", "KT 위즈", "KT위즈", "KT Wiz",
    "Dodgers", "Yankees", "Mets", "Blue Jays", "Red Sox", "Cubs", "Braves", "Phillies", "Padres", "Astros",
    # Basketball
    "서울 SK 나이츠", "SK 나이츠", "부산 KCC", "KCC 이지스", "수원 KT",
    "창원 LG 세이커스", "원주 DB 프로미", "안양 정관장",
    "Lakers", "Warriors", "Celtics", "Knicks", "Bulls", "Spurs",
    "Mavericks", "Nuggets", "76ers", "Clippers", "Heat", "Suns",
    "Cavaliers", "Thunder", "Rockets",
    # K League
    "전북 현대", "울산 HD", "FC 서울", "포항 스틸러스", "인천 유나이티드", "대전 하나", "수원 삼성",
    # Volleyball
    "대한항공 점보스", "현대캐피탈 스카이워커스", "OK저축은행 읏맨",
    "흥국생명 핑크스파이더스", "현대건설 힐스테이트", "삼성화재 블루팡스", "우리카드 우리WON", "정관장 레드스파크스", "GS칼텍스 서울 KIXX",
)
MAJOR_MATCH = re.compile("|".join(re.escape(name) for name in MAJOR_TEAMS), re.I)


def is_major_highlight(title):
    return bool(HIGHLIGHT.search(title) and (MAJOR_MATCH.search(title) or MAJOR_EVENT.search(title)))


def collect():
    videos = {}
    failed_channels = set()
    for channel_id, channel_name in CHANNELS.items():
        url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id
        request = urllib.request.Request(url, headers={"User-Agent": "NUDETV-Highlight-Feed/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                root = ET.fromstring(response.read())
        except (urllib.error.URLError, TimeoutError, ET.ParseError) as error:
            failed_channels.add(channel_id)
            print("[Feed] channel failed %s: %s" % (channel_name, error), flush=True)
            continue
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
    if failed_channels:
        try:
            previous = json.loads(Path("highlights.json").read_text()).get("videos", [])
        except (OSError, ValueError):
            previous = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        for item in previous:
            if item.get("channel_id") not in failed_channels or item.get("video_id") in videos:
                continue
            try:
                published = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                if published.tzinfo is None or published < cutoff:
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            videos[item["video_id"]] = item
    ordered = sorted(videos.values(), key=lambda item: item["published_at"], reverse=True)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "videos": ordered[:100]}


if __name__ == "__main__":
    Path("highlights.json").write_text(json.dumps(collect(), ensure_ascii=False, indent=2) + "\n")
