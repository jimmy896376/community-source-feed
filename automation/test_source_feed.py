import io
import unittest
from unittest.mock import Mock, patch

from PIL import Image

import source_feed


class SourceFeedTests(unittest.TestCase):
    def test_humoruniv_loading_control_is_not_collected(self):
        data = io.BytesIO()
        Image.new("RGB", (20, 20), "red").save(data, format="PNG")
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
        Image.new("RGB", (20, 20), "red").save(content, format="PNG")
        Image.new("RGB", (20, 20), "blue").save(artwork, format="PNG")
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


if __name__ == "__main__":
    unittest.main()
