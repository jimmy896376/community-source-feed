import unittest

from highlights_feed import is_major_highlight


class MajorHighlightTests(unittest.TestCase):
    def test_bayern_and_psg_are_included(self):
        self.assertTrue(is_major_highlight("[26/27 분데스리가] 바이에른 뮌헨 하이라이트"))
        self.assertTrue(is_major_highlight("[리그앙] PSG highlights"))

    def test_non_major_clubs_are_excluded(self):
        self.assertFalse(is_major_highlight("[분데스리가] 베르더 브레멘 하이라이트"))
        self.assertFalse(is_major_highlight("[리그앙] 스타드 드 랭스 하이라이트"))

    def test_non_highlight_video_is_excluded(self):
        self.assertFalse(is_major_highlight("바이에른 뮌헨 경기 프리뷰"))


if __name__ == "__main__":
    unittest.main()
