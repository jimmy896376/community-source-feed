"""Remove unused release assets only after every feed that could reference them has expired."""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


def expired_assets(feed, assets, now):
    active = {image["digest"] for post in feed["posts"] for image in post["images"]}
    cutoff = now - timedelta(hours=48)
    return [
        asset["id"] for asset in assets
        if re.fullmatch(r"[0-9a-f]{64}", asset.get("name", ""))
        and asset["name"] not in active
        and datetime.fromisoformat(asset["created_at"].replace("Z", "+00:00")) < cutoff
    ]


def main():
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}"
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
    feed = json.loads(Path("feed.json").read_text(encoding="utf-8"))
    release = requests.get(url + "/releases/tags/source-media-cache", headers=headers, timeout=20)
    release.raise_for_status()
    release_id = release.json()["id"]
    assets = []
    page = 1
    while True:
        response = requests.get(
            url + f"/releases/{release_id}/assets",
            headers=headers, params={"per_page": 100, "page": page}, timeout=20)
        response.raise_for_status()
        batch = response.json()
        assets.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    stale = expired_assets(feed, assets, datetime.now(timezone.utc))
    for asset_id in stale:
        response = requests.delete(url + f"/releases/assets/{asset_id}", headers=headers, timeout=20)
        response.raise_for_status()
    print(f"Pruned {len(stale)} expired source media assets.")


if __name__ == "__main__":
    main()
