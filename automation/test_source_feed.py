import hashlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import source_feed


class SourceFeedTests(unittest.TestCase):
    def test_humoruniv_loading_control_is_not_collected(self):
        data = io.BytesIO()
        Image.new("RGB", (800, 600), "red").save(data, format="PNG")
        download = Mock(return_value=data.getvalue())
        raw = ('<h2><a>Story</a></h2><div id="wrap_copy"><p>Original story text is here.</p>'
               '<img src="https://down.humoruniv.com/story.png">'
               '<img src="https://m.humoruniv.com/images/loading_bar2.gif"></div>').encode()
        item = source_feed.article(
            raw, "https://m.humoruniv.com/board/read.html?table=pds&number=1430195", download)
        self.assertEqual(len(item["images"]), 1)
        self.assertNotIn("loading_bar", item["body"])
        download.assert_called_once()


    def test_excluded_artwork_is_removed_and_only_artwork_post_is_skipped(self):
        content, artwork = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (800, 600), "red").save(content, format="PNG")
        Image.new("RGB", (800, 600), "blue").save(artwork, format="PNG")
        source = "https://m.humoruniv.com/board/read.html?table=pds&number=1430195"
        def download(url, **kwargs):
            return artwork.getvalue() if url.endswith("art.png") else content.getvalue()
        raw = ('<h2><a>Story</a></h2><div id="wrap_copy"><p>Original story.</p>'
               '<img src="https://down.humoruniv.com/story.png">'
               '<img src="https://down.humoruniv.com/art.png"></div>').encode()
        with patch.object(source_feed, "is_excluded_artwork",
                          side_effect=lambda data: data == artwork.getvalue()):
            item = source_feed.article(raw, source, download)
            self.assertEqual(len(item["images"]), 1)
            self.assertEqual(item["body"].count("<img"), 1)
            self.assertNotIn("art.png", item["body"])
            only_art = ('<h2><a>Story</a></h2><div id="wrap_copy">'
                        '<img src="https://down.humoruniv.com/art.png"></div>').encode()
            self.assertIsNone(source_feed.article(only_art, source, download))


    def test_first_self_introduction_image_is_removed(self):
        data = io.BytesIO()
        Image.new("RGB", (800, 600), "red").save(data, format="PNG")
        source = "https://m.humoruniv.com/board/read.html?table=pds&number=1430195"
        raw = ('<h2><a>Story</a></h2><div id="wrap_copy">'
               '<img alt="자기소개 사진" src="https://down.humoruniv.com/intro.png">'
               '<img src="https://down.humoruniv.com/story.png"></div>').encode()
        item = source_feed.article(raw, source, Mock(return_value=data.getvalue()))
        self.assertEqual(len(item["images"]), 1)
        self.assertEqual(item["body"].count("<img"), 1)
        self.assertNotIn("자기소개", item["body"])


    def test_unreadable_images_and_sparrow_text_are_skipped(self):
        tiny, tall, normal = io.BytesIO(), io.BytesIO(), io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(tiny, format="PNG")
        Image.new("RGB", (153, 1600), "white").save(tall, format="PNG")
        Image.new("RGB", (800, 600), "green").save(normal, format="PNG")
        source = "https://m.humoruniv.com/board/read.html?table=pds&number=1430196"
        raw = '<h2><a>Story</a></h2><div id="wrap_copy"><img src="https://down.humoruniv.com/a.png"></div>'.encode()
        self.assertIsNone(source_feed.article(raw, source, Mock(return_value=tiny.getvalue())))
        self.assertIsNone(source_feed.article(raw, source, Mock(return_value=tall.getvalue())))
        sparrow = '<h2><a>참새 이야기</a></h2><div id="wrap_copy"><img src="https://down.humoruniv.com/a.png"></div>'.encode()
        self.assertIsNone(source_feed.article(sparrow, source, Mock(return_value=normal.getvalue())))


    def test_collect_falls_back_to_next_listing_page(self):
        img = io.BytesIO()
        Image.new("RGB", (800, 600), "red").save(img, format="PNG")
        image_bytes = img.getvalue()
        listing_html = (
            '<a href="/board/read.html?table=pds&number=999">'
            '<span class="ok_num">120</span></a>'
        )
        article_html = (
            '<h2><a>둘째 페이지 글</a></h2>'
            '<div id="wrap_copy"><p>재미있는 본문입니다.</p>'
            '<img src="https://down.humoruniv.com/second.png"></div>'
        )

        class FakeReader:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def html(self, url):
                if url == source_feed.LISTS[0]:
                    raise source_feed.ActionRequired("first page timed out")
                if url == source_feed.LISTS[1]:
                    return listing_html, url
                if url == source_feed.LISTS[2]:
                    return "", url
                return article_html, url

            def image(self, url, referer=None):
                return image_bytes

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(source_feed, "SourceReader", return_value=FakeReader()):
            result = source_feed.collect(media_dir=directory)
        self.assertTrue(result["media_cached"])
        self.assertEqual([row["source_id"] for row in result["posts"]], ["hu:999"])


    def test_recent_feed_images_are_cached_when_listing_fails(self):
        data = io.BytesIO()
        Image.new("RGB", (800, 600), "red").save(data, format="PNG")
        image = data.getvalue()
        digest = hashlib.sha256(image).hexdigest()
        post = {
            "source_id": "hu:1430195",
            "source_url": "https://m.humoruniv.com/board/read.html?table=pds&number=1430195",
            "title": "원본 글",
            "body": f'<img src="asset:{digest}">',
            "images": [{"digest": digest, "source_url": "https://down.humoruniv.com/story.png",
                        "mime": "image/png"}],
        }

        class Reader:
            def image(self, url, referer=None):
                return image

        with tempfile.TemporaryDirectory() as directory:
            old = os.getcwd()
            try:
                os.chdir(directory)
                Path("feed.json").write_text(json.dumps({
                    "generated_at": datetime.now(timezone.utc).isoformat(), "posts": [post],
                }), encoding="utf-8")
                result = source_feed.cached_previous_feed(Reader(), Path(directory) / "media")
                self.assertTrue(result["media_cached"])
                self.assertEqual(result["posts"], [post])
                self.assertEqual((Path(directory) / "media" / digest).read_bytes(), image)
            finally:
                os.chdir(old)

if __name__ == "__main__":
    unittest.main()
