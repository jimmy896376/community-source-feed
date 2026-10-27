#!/usr/bin/env python3
"""Collect approved public community posts. No target-site URL or credentials."""
import hashlib
import io
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps

LISTS = ["https://m.humoruniv.com/board/list.html?table=pds"]
REFERENCE_ARTWORK = ((0x07170FB5E576361F, 0.64, 0.70),
                     (0x000C76772D9A6401, 0.98, 1.02))
EXCLUDED_ARTWORK = ((0x0F3C18D1C336930F, 0.68, 0.73),
                    (0x0081C3C060200000, 1.47, 1.53),
                    (0xD8C190C1C5D57A12, 1.44, 1.50),
                    (0x9C868C84C6D6C7EE, 0.75, 0.80),
                    (0x594D1D4E2E5D4F6C, 1.74, 1.82))

class ActionRequired(Exception):
    pass


def public_download(url, referer=None):
    """Source HTML must never direct the worker to a private network or receive admin auth."""
    for _ in range(5):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
            raise ActionRequired("Source contains an unsafe media URL.")
        if not any(parts.hostname == d or parts.hostname.endswith("." + d)
                   for d in ("fmkorea.com", "humoruniv.com", "todayhumor.co.kr")):
            raise ActionRequired("Source media is outside the approved community domains.")
        try:
            addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise ActionRequired("Source contains a private network URL.")
            headers = {"User-Agent": "Mozilla/5.0"}
            if referer:
                headers["Referer"] = referer
            with requests.get(url, headers=headers, timeout=30, allow_redirects=False, stream=True) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers["Location"])
                    continue
                if r.status_code != 200:
                    raise ActionRequired("Approved source or image is blocked (HTTP %d)." % r.status_code)
                chunks, size = [], 0
                for chunk in r.iter_content(65536):
                    size += len(chunk)
                    if size > 30 * 1024 * 1024:
                        raise ActionRequired("Source image or page exceeds the supported size.")
                    chunks.append(chunk)
                return b"".join(chunks)
        except (requests.RequestException, OSError):
            raise ActionRequired("Approved source or image is unavailable.") from None
    raise ActionRequired("Source has too many redirects.")

def source_id(url):
    p = urlsplit(url)
    host = p.hostname or ""
    q = parse_qs(p.query)
    if host in ("www.fmkorea.com", "fmkorea.com"):
        m = re.fullmatch(r"/(?:best2/)?(\d+)", p.path)
        number = m.group(1) if m else q.get("document_srl", [None])[0]
        return "fm:" + number if number and number.isdigit() else None
    if host in ("m.humoruniv.com", "web.humoruniv.com"):
        if q.get("table") == ["pds"] and q.get("number", [""])[0].isdigit() and "read" in p.path:
            return "hu:" + q["number"][0]
    if host in ("www.todayhumor.co.kr", "todayhumor.co.kr"):
        if "view.php" in p.path and q.get("no", [""])[0].isdigit():
            return "oh:" + q["no"][0]
    return None

def candidates(raw, listing):
    soup = BeautifulSoup(raw, "html.parser")
    if "humoruniv.com" in urlsplit(listing).netloc:
        ranked = {}
        for a in soup.select("a[href]"):
            url = urljoin(listing, a["href"])
            key = source_id(url)
            score = a.select_one(".ok_num, font[color=red]")
            if not key or not key.startswith("hu:") or score is None:
                continue
            digits = score.get_text(strip=True).replace(",", "")
            if not digits.isdigit():
                continue
            if key not in ranked or int(digits) > ranked[key][0]:
                ranked[key] = (int(digits), url)
        return [(key, value[1]) for key, value in
                sorted(ranked.items(), key=lambda item: item[1][0], reverse=True)][:30]
    urls = {}
    selector = ".fm_best_widget li a[href]" if "fmkorea.com" in urlsplit(listing).netloc else "a[href]"
    for a in soup.select(selector):
        url = urljoin(listing, a["href"])
        key = source_id(url)
        if key:
            urls.setdefault(key, url)
    return list(urls.items())[:30]

def matches_artwork(data, references):
    try:
        with Image.open(io.BytesIO(data)) as picture:
            width, height = picture.size
            pixels = list(ImageOps.grayscale(picture).resize((9, 8)).getdata())
    except Exception:
        return False
    fingerprint = sum((pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x)
                      for y in range(8) for x in range(8))
    return any(low <= width / height <= high and bin(fingerprint ^ reference).count("1") <= 5
               for reference, low, high in references)


def is_reference_artwork(data):
    return matches_artwork(data, REFERENCE_ARTWORK)


def is_excluded_artwork(data):
    return matches_artwork(data, EXCLUDED_ARTWORK)

def looks_like_detached_artwork(data):
    """Flag a paper-backed edge illustration; callers skip the whole candidate."""
    try:
        with Image.open(io.BytesIO(data)) as picture:
            width, height = picture.size
            if min(width, height) < 400 or not 0.6 <= width / height <= 1.2:
                return False
            pixels = list(picture.convert("RGB").resize((32, 32)).getdata())
    except Exception:
        return False
    pale = lambda rgb: min(rgb) >= 205 and max(rgb) - min(rgb) <= 50
    corners = (pixels[0], pixels[31], pixels[-32], pixels[-1])
    # shortcut: pale paper is only a suspicion; skip the candidate instead of deleting its image.
    return all(map(pale, corners)) and sum(map(pale, pixels)) >= 300

def article(raw, url, download=None):
    download = download or public_download
    soup = BeautifulSoup(raw, "html.parser")
    if source_id(url).startswith("fm:"):
        title, body = soup.select_one(".rd_hd .np_18px, .rd_hd .title"), soup.select_one(".xe_content")
    elif source_id(url).startswith("hu:"):
        title, body = soup.select_one("h2 a"), soup.select_one("#wrap_copy")
    else:
        title, body = soup.select_one(".viewSubjectDiv"), soup.select_one(".viewContent")
    if title is None or body is None or body.select_one("video, iframe, audio, object, embed, canvas, svg"):
        return None
    if source_id(url).startswith("hu:"):
        audience = title.get_text(" ", strip=True) + " " + body.get_text(" ", strip=True)
        if re.search(r"웃대|웃긴대학|여러분|(?<![가-힣])님들|회원님들?|(?:여기|이곳)\s*(?:계신\s*)?분들", audience):
            return None
    for node in body.select("script, style, .member_plate, .member-info, .profile, .avatar, .sign, .author"):
        node.decompose()
    for node in body.select('[id^="timg_prog_"], [id^="btn_nemo_"]'):
        node.decompose()
    # Embedded links are unwrapped. No original article URL is published.
    for node in body.select("a"):
        node.unwrap()
    for text in body.find_all(string=True):
        if any(domain in str(text).lower() for domain in ("fmkorea.com", "humoruniv.com", "todayhumor.co.kr")):
            return None
    images, seen = [], set()
    for image in body.select("img"):
        src = image.get("img_file_url") or image.get("data-original") or image.get("data-src") or image.get("src")
        if src:
            image_url = urljoin(url, src)
            if (urlsplit(image_url).hostname in ("m.humoruniv.com", "web.humoruniv.com")
                    and re.fullmatch(r"/images/loading_bar\d*\.gif", urlsplit(image_url).path, re.I)):
                image.decompose()
    body_images = body.select("img")
    topical_art = re.search(r"겨울사람|그림|일러스트|캐릭터|팬아트|작화|스케치", title.get_text(" ", strip=True))
    for index, image in enumerate(body_images):
        src = image.get("img_file_url") or image.get("data-original") or image.get("data-src") or image.get("src")
        if not src:
            return None
        image_url = urljoin(url, src)
        data = download(image_url, referer=url)
        extra_image = len(body_images) > 1 or len(body.get_text(" ", strip=True)) >= 80
        marker = " ".join((image.get("alt") or "", image.get("title") or "",
                           " ".join(image.get("class", [])), image.get("id") or "",
                           " ".join(image.parent.get("class", [])), image.parent.get("id") or ""))
        marker += " " + urlsplit(image_url).path.rsplit("/", 1)[-1]
        marked_signature = re.search(
            r"(?:^|[-_./ ])(?:avatar|profile|signature|author|watermark|self[-_ ]?intro|introduction|about[-_ ]?me)(?:$|[-_./ ])|프로필|자기소개|작성자|작가소개|서명",
            marker, re.I)
        if is_excluded_artwork(data) or marked_signature:
            image.decompose()
            continue
        if extra_image and not topical_art and is_reference_artwork(data):
            image.decompose()
            continue
        if (len(body_images) > 1 and index in (0, len(body_images) - 1)
                and not topical_art and looks_like_detached_artwork(data)):
            return None
        try:
            with Image.open(io.BytesIO(data)) as picture:
                picture.verify()
            with Image.open(io.BytesIO(data)) as picture:
                mime = Image.MIME[picture.format]
        except Exception:
            raise ActionRequired("Original image cannot be decoded; candidate was not published.") from None
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            image.decompose()
            continue
        seen.add(digest)
        image.attrs = {"src": "asset:" + digest, "alt": image.get("alt", "")}
        images.append({"digest": digest, "source_url": image_url, "mime": mime})
    allowed = {"div", "p", "span", "br", "strong", "b", "em", "i", "u", "s", "blockquote",
               "ul", "ol", "li", "table", "tbody", "thead", "tr", "td", "th", "img", "hr"}
    for node in list(body.find_all(True)):
        if node.name not in allowed:
            node.unwrap()
        elif node.name != "img":
            node.attrs = {}
    if not body.get_text(strip=True) and not images:
        return None
    # Humoruniv image posts can silently lose their attachment during collection.
    if source_id(url).startswith("hu:") and not images:
        return None
    if len(body.get_text(" ", strip=True)) < 30 and not images:
        return None
    return {"title": title.get_text(" ", strip=True), "body": body.decode_contents(), "images": images}

class SourceReader:
    """Anonymous source browser. Admin authentication is never injected into this context."""
    def __init__(self):
        self.playwright = self.browser = self.context = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def start(self):
        if self.context is None:
            from playwright.sync_api import sync_playwright
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch()
            self.context = self.browser.new_context()

    def html(self, url):
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in ("m.humoruniv.com", "web.humoruniv.com"):
            raise ActionRequired("Only approved Humoruniv source pages may be opened.")
        try:
            # Humoruniv article images are inserted by page scripts. Read rendered DOM.
            if source_id(url) is None:
                raw = public_download(url)
                if candidates(raw, url):
                    return raw, url
                raise ActionRequired("Open listing in browser after anonymous cookie challenge.")
            raise ActionRequired("Open article in browser for rendered images.")
        except ActionRequired:
            self.start()
            page = self.context.new_page()
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if response is None or response.status != 200:
                    raise ActionRequired("Humoruniv browser access is blocked.")
                if "브라우저 쿠키 발행이 필요합니다" in page.locator("body").inner_text():
                    # Use the visible site's normal anonymous-cookie issuance button. Never solve CAPTCHAs.
                    for control in (page.get_by_role("link", name="목록으로 이동", exact=True),
                                    page.get_by_role("button", name="목록으로 이동", exact=True),
                                    page.get_by_text("목록으로 이동", exact=True)):
                        if control.count():
                            control.first.click()
                            page.wait_for_load_state("domcontentloaded")
                            response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                            break
                if response is None or response.status != 200 or urlsplit(page.url).hostname not in ("m.humoruniv.com", "web.humoruniv.com"):
                    raise ActionRequired("Humoruniv anonymous session could not be established.")
                if source_id(url) and page.locator('[id^="comment_file_"]').count():
                    page.locator('#wrap_copy img[img_file_url]').first.wait_for(timeout=10000)
                # Return text, not UTF-8 bytes carrying an old EUC-KR meta tag.
                return page.content(), page.url
            except ActionRequired:
                raise
            except Exception:
                raise ActionRequired("Humoruniv page could not be read by the browser.") from None
            finally:
                page.close()

    def image(self, url, referer=None):
        try:
            return public_download(url, referer=referer)
        except ActionRequired:
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443) or not (parts.hostname or "").endswith(".humoruniv.com"):
                raise ActionRequired("Source image is outside the approved community.")
            self.start()
            try:
                response = self.context.request.get(url, headers={"Referer": referer or LISTS[0]},
                                                    max_redirects=0, timeout=30000)
                if response.status != 200:
                    raise ActionRequired("Humoruniv original image is blocked.")
                data = response.body()
                if len(data) > 30 * 1024 * 1024:
                    raise ActionRequired("Original image exceeds the supported size.")
                return data
            except ActionRequired:
                raise
            except Exception:
                raise ActionRequired("Humoruniv original image could not be read.") from None


def collect():
    posts = []
    with SourceReader() as reader:
        raw, listing = reader.html(LISTS[0])
        for key, url in candidates(raw, listing)[:30]:
            try:
                raw, final_url = reader.html(url)
                item = article(raw, final_url, download=reader.image)
                visible = (item["title"] + " " + item["body"]) if item else ""
                # Keep destination addresses out of the public feed even if a source mentions one.
                if item and not re.search(r"(?:https?://|www\.|[a-z0-9-]+\.(?:com|net|kr|org))", visible, re.I):
                    posts.append({"source_id": key, "source_url": final_url, **item})
                    if len(posts) >= 10:
                        break
            except ActionRequired:
                continue
    if not posts:
        raise ActionRequired("No suitable public source is available.")
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "posts": posts}


if __name__ == "__main__":
    feed = collect()
    Path("feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
