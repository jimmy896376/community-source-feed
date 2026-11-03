import unittest

from highlights_feed import is_major_highlight


class MajorHighlightTests(unittest.TestCase):
    def test_example_football_clubs_are_included(self):
        self.assertTrue(is_major_highlight("[26/27 분데스리가] 바이에른 뮌헨 하이라이트"))
        self.assertTrue(is_major_highlight("[리그앙] PSG highlights"))

    def test_non_major_football_clubs_are_excluded(self):
        self.assertFalse(is_major_highlight("[분데스리가] 베르더 브레멘 하이라이트"))
        self.assertFalse(is_major_highlight("[리그앙] 스타드 드 랭스 하이라이트"))

    def test_popular_teams_across_four_sports_are_included(self):
        for title in (
            "KIA 타이거즈 하이라이트",
            "서울 SK 나이츠 하이라이트",
            "흥국생명 핑크스파이더스 하이라이트",
        ):
            with self.subTest(title=title):
                self.assertTrue(is_major_highlight(title))

    def test_non_highlight_video_is_excluded(self):
        self.assertFalse(is_major_highlight("바이에른 뮌헨 경기 프리뷰"))


if __name__ == "__main__":
    unittest.main()
