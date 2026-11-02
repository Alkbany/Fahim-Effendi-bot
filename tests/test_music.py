import unittest
from collections import deque
from unittest.mock import patch

from cogs.music import format_duration, shuffle_queue


class MusicFormattingTests(unittest.TestCase):

    def test_formats_short_track(self):
        self.assertEqual(format_duration(185), "3:05")

    def test_formats_track_with_hours(self):
        self.assertEqual(format_duration(3661), "1:01:01")

    def test_formats_zero_length(self):
        self.assertEqual(format_duration(0), "0:00")

    def test_formats_live_stream(self):
        self.assertEqual(format_duration(0, is_stream=True), "بث مباشر")


class MusicQueueTests(unittest.TestCase):

    def test_shuffle_queue_preserves_deque_and_shuffles_items(self):
        queue = deque(["first", "second", "third"])

        with patch("cogs.music.random.shuffle", side_effect=lambda items: items.reverse()):
            shuffle_queue(queue)

        self.assertIsInstance(queue, deque)
        self.assertEqual(list(queue), ["third", "second", "first"])


if __name__ == "__main__":
    unittest.main()
