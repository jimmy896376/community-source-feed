#!/usr/bin/env python3
"""Collect approved public community posts. No target-site URL or credentials."""
import hashlib
import io
import os
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

LISTS = ["https://www.dogdrip.net/dogdrip?sort_index=popular&page=1",
         "https://www.dogdrip.net/dogdrip?sort_index=popular&page=2"]
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
                   for d in ("dogdrip.net", "fmkorea.com", "humoruniv.com", "todayhumor.co.kr")):
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
    if host in ("www.dogdrip.net", "dogdrip.net"):
        m = re.fullmatch(r"/dogdrip/(\d+)", p.path)
        number = m.group(1) if m else q.get("document_srl", [None])[0]
        return "dd:" + number if number and number.isdigit() else None
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
    if "dogdrip.net" in urlsplit(listing).netloc:
        urls = {}
        for a in soup.select("a[href]"):
            if a.find_parent(class_=lambda c: c and "notice" in c):
                continue
            url = urljoin(listing, a["href"])
            key = source_id(url)
            if key and key.startswith("dd:"):
                clean_url = f"https://www.dogdrip.net/dogdrip/{key.split(':', 1)[1]}"
                urls.setdefault(key, clean_url)
        return list(urls.items())[:30]
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

def unreadable_tall_image(data):
    """Reject tiny placeholders and tall images unreadable after the site's 1600px fit."""
    try:
        with Image.open(io.BytesIO(data)) as picture:
            width, height = picture.size
    except Exception:
        return False
    return min(width, height) < 100 or height >= 1000 and width * min(1, 1600 / height) < 500


def article(raw, url, download=None):
    download = download or public_download
    soup = BeautifulSoup(raw, "html.parser")
    sid = source_id(url) or ""
    if sid.startswith("dd:"):
        title = soup.select_one(".article-head h4, .ed.article-head h4, h4.title, .title-wrapper h4")
        if title is None:
            og = soup.select_one('meta[property="og:title"]')
            if og and og.get("content"):
                title = soup.new_tag("span")
                title.string = re.sub(r"\s*-\s*DogDrip\.Net.*$", "", og["content"]).strip()
        body = soup.select_one("#article_1 .rhymix_content, #article_1 .xe_content, .article-wrapper .rhymix_content, .article-wrapper .xe_content, .rhymix_content, .xe_content")
    elif sid.startswith("fm:"):
        title, body = soup.select_one(".rd_hd .np_18px, .rd_hd .title"), soup.select_one(".xe_content")
    elif sid.startswith("hu:"):
        title, body = soup.select_one("h2 a"), soup.select_one("#wrap_copy")
    else:
        title, body = soup.select_one(".viewSubjectDiv"), soup.select_one(".viewContent")
    if title is None or body is None or body.select_one("video, iframe, audio, object, embed, canvas, svg"):
        return None
    if sid.startswith(("hu:", "dd:")):
        audience = title.get_text(" ", strip=True) + " " + body.get_text(" ", strip=True)
        if re.search(r"웃대|웃긴대학|개드립|개붕이?|붐업|여러분|(?<![가-힣])님들|회원님들?|(?:여기|이곳)\s*(?:계신\s*)?분들|(?:먹을|받을|가져갈|필요한|원하는)\s*사람|(?:살면|살면\s*더)\s*우대|(?:해주셈|해줘요|해주실|인증샷\s*받을)", audience):
            return None
    for node in body.select("script, style, .member_plate, .member-info, .profile, .avatar, .sign, .author"):
        node.decompose()
    for node in body.select('[id^="timg_prog_"], [id^="btn_nemo_"]'):
        node.decompose()
    # Embedded links are unwrapped. No original article URL is published.
    for node in body.select("a"):
        node.unwrap()
    for text in body.find_all(string=True):
        if any(domain in str(text).lower() for domain in ("dogdrip.net", "fmkorea.com", "humoruniv.com", "todayhumor.co.kr")):
            return None
    if re.search(r"참새|sparrow", title.get_text(" ", strip=True) + " " + body.get_text(" ", strip=True), re.I):
        return None
    images, seen = [], set()
    for image in body.select("img"):
        src = image.get("img_file_url") or image.get("data-original") or image.get("data-src") or image.get("src")
        if src:
            image_url = urljoin(url, src)
            path_l = urlsplit(image_url).path.lower()
            if (urlsplit(image_url).hostname in ("m.humoruniv.com", "web.humoruniv.com")
                    and re.fullmatch(r"/images/loading_bar\d*\.gif", path_l)):
                image.decompose()
            elif sid.startswith("dd:") and any(seg in path_l for seg in ("/modules/point/icons/", "/layouts/", "/addons/", "/common/img/")):
                image.decompose()
    body_images = body.select("img")
    topical_art = re.search(r"겨울사람|그림|일러스트|캐릭터|팬아트|작화|스케치", title.get_text(" ", strip=True))
    for index, image in enumerate(body_images):
        src = image.get("img_file_url") or image.get("data-original") or image.get("data-src") or image.get("src")
        if not src:
            return None
        image_url = urljoin(url, src)
        try:
            data = download(image_url, referer=url)
        except ActionRequired:
            displayed = urljoin(url, image.get("src", ""))
            if (displayed == image_url or
                    urlsplit(displayed).hostname != "down-webp.humoruniv.com"):
                raise
            data = download(displayed, referer=url)
            image_url = displayed
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
        if unreadable_tall_image(data):
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
        if parts.scheme != "https" or parts.hostname not in ("www.dogdrip.net", "dogdrip.net", "m.humoruniv.com", "web.humoruniv.com"):
            raise ActionRequired("Only approved community source pages may be opened.")
        if parts.hostname in ("www.dogdrip.net", "dogdrip.net"):
            raw = public_download(url)
            return raw.decode("utf-8", "ignore"), url
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
                from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
                timed_out_with_content = False
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                except PlaywrightTimeoutError:
                    if page.url != url or not (page.locator("#wrap_copy").count() if source_id(url)
                                               else candidates(page.content(), page.url)):
                        raise
                    response = None
                    timed_out_with_content = True
                if (response is None and not timed_out_with_content) or (response is not None and response.status != 200):
                    raise ActionRequired("Humoruniv browser access is blocked.")
                if "브라우저 쿠키 발행이 필요합니다" in page.locator("body").inner_text():
                    # Use the visible site's normal anonymous-cookie issuance button. Never solve CAPTCHAs.
                    for control in (page.get_by_role("link", name="목록으로 이동", exact=True),
                                    page.get_by_role("button", name="목록으로 이동", exact=True),
                                    page.get_by_text("목록으로 이동", exact=True)):
                        if control.count():
                            control.first.click()
                            page.wait_for_load_state("domcontentloaded")
                            timed_out_with_content = False
                            response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                            break
                if ((response is None and not timed_out_with_content) or
                        (response is not None and response.status != 200) or
                        urlsplit(page.url).hostname not in ("m.humoruniv.com", "web.humoruniv.com")):
                    raise ActionRequired("Humoruniv anonymous session could not be established.")
                if source_id(url) and page.locator('[id^="comment_file_"]').count():
                    page.locator('#wrap_copy img[img_file_url]').first.wait_for(timeout=10000)
                # Return text, not UTF-8 bytes carrying an old EUC-KR meta tag.
                return page.content(), page.url
            except ActionRequired:
                raise
            except Exception as error:
                raise ActionRequired("Humoruniv page could not be read by the browser (%s)." % type(error).__name__) from None
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


def save_media(data, media_dir):
    digest = hashlib.sha256(data).hexdigest()
    directory = Path(media_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / digest
    if not target.exists():
        target.write_bytes(data)
    return digest


def prune_media(media_dir, posts):
    needed = {image["digest"] for post in posts for image in post["images"]}
    for target in Path(media_dir).iterdir():
        if target.is_file() and target.name not in needed:
            target.unlink()


def cached_previous_feed(reader, media_dir):
    """Keep recent, already reviewed candidates when the listing is unavailable."""
    path = Path("feed.json")
    if not path.exists():
        raise ActionRequired("No suitable public source is available.")
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(previous["generated_at"].replace("Z", "+00:00"))
        if not 0 <= (datetime.now(timezone.utc) - generated).total_seconds() <= 24 * 3600:
            raise ValueError("Previous feed expired")
    except (ValueError, KeyError, TypeError):
        raise ActionRequired("No recent approved source feed is available.") from None
    if previous.get("media_cached") is True:
        return previous
    posts = []
    for post in previous.get("posts", []):
        try:
            images = post["images"]
            if not images:
                continue
            for image in images:
                digest, url = image["digest"], image["source_url"]
                host = urlsplit(url).hostname or ""
                if not re.fullmatch(r"[0-9a-f]{64}", digest) or not any(
                        host == d or host.endswith("." + d) for d in ("dogdrip.net", "humoruniv.com")):
                    raise ActionRequired("Previous feed has an unapproved image.")
                data = reader.image(url, referer=post["source_url"])
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ActionRequired("Previous source image changed.")
                save_media(data, media_dir)
            posts.append(post)
        except (ActionRequired, KeyError, TypeError):
            continue
    if not posts:
        raise ActionRequired("No recent source images could be cached.")
    prune_media(media_dir, posts)
    return {"generated_at": previous["generated_at"], "media_cached": True, "posts": posts}


def collect(media_dir=None):
    posts, seen_keys = [], set()
    with SourceReader() as reader:
        def download(url, referer=None):
            data = reader.image(url, referer=referer)
            if media_dir:
                save_media(data, media_dir)
            return data

        listings_loaded = False
        for listing_url in LISTS:
            try:
                raw, listing = reader.html(listing_url)
                listings_loaded = True
            except ActionRequired:
                continue
            for key, url in candidates(raw, listing)[:30]:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                try:
                    raw, final_url = reader.html(url)
                    item = article(raw, final_url, download=download)
                    visible = (item["title"] + " " + item["body"]) if item else ""
                    # Keep destination addresses out of the public feed even if a source mentions one.
                    if item and not re.search(r"(?:https?://|www\\.|[a-z0-9-]+\\.(?:com|net|kr|org))", visible, re.I):
                        posts.append({"source_id": key, "source_url": final_url, **item})
                        if len(posts) >= 35:
                            break
                except ActionRequired:
                    continue
            if len(posts) >= 35:
                break
        if (not listings_loaded or not posts) and media_dir:
            return cached_previous_feed(reader, media_dir)
    if not posts:
        raise ActionRequired("No suitable public source is available.")
    feed = {"generated_at": datetime.now(timezone.utc).isoformat(), "posts": posts}
    if media_dir:
        prune_media(media_dir, posts)
        feed["media_cached"] = True
    return feed


if __name__ == "__main__":
    feed = collect(os.environ.get("SOURCE_MEDIA_CACHE_DIR"))
    Path("feed.json").write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")
