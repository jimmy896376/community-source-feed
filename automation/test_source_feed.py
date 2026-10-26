import io
import unittest
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
