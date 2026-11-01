import unittest

from cogs.music import format_duration


class MusicFormattingTests(unittest.TestCase):

    def test_formats_short_track(self):
        self.assertEqual(format_duration(185000), "3:05")

    def test_formats_track_with_hours(self):
        self.assertEqual(format_duration(3661000), "1:01:01")

    def test_formats_zero_length(self):
        self.assertEqual(format_duration(0), "0:00")

    def test_formats_live_stream(self):
        self.assertEqual(format_duration(0, is_stream=True), "بث مباشر")


if __name__ == "__main__":
    unittest.main()
