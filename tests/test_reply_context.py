import unittest

from services.context_service import build_reply_context


class ReplyContextTests(unittest.TestCase):
    def test_reply_context_contains_parent_and_current_message(self):
        result = build_reply_context(
            "طب أنهي واحدة بتتمسح؟",
            "الفرق بين RAM وROM إن الأولى مؤقتة والثانية غير متطايرة.",
        )

        self.assertIn("[REPLY CONTEXT", result)
        self.assertIn("الفرق بين RAM وROM", result)
        self.assertIn("[CURRENT MEMBER MESSAGE]", result)
        self.assertIn("طب أنهي واحدة بتتمسح؟", result)

    def test_empty_parent_does_not_add_fake_context(self):
        self.assertEqual(
            build_reply_context("اختلف معاك", ""),
            "اختلف معاك",
        )

    def test_empty_current_message_gets_a_neutral_follow_up(self):
        result = build_reply_context("  ", "رسالة فهيم الأصلية")

        self.assertIn("رسالة فهيم الأصلية", result)
        self.assertIn("كمّل كلامك عن الرسالة دي.", result)

    def test_whitespace_is_trimmed(self):
        self.assertEqual(
            build_reply_context("  تمام  ", "  نص الرسالة  "),
            "[REPLY CONTEXT - MESSAGE THE MEMBER IS REPLYING TO]\n"
            "نص الرسالة\n\n"
            "[CURRENT MEMBER MESSAGE]\n"
            "تمام",
        )


if __name__ == "__main__":
    unittest.main()
