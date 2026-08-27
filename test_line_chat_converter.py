import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from line_chat_converter import ChatMedia, MediaFile, convert_chat, match_media, parse_chat_media


class StrictMediaMatchTests(unittest.TestCase):
    def test_bubbles_fit_short_message_content(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t好\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")

        self.assertIn(".bubble{width:fit-content;max-width:100%", page)
        self.assertIn(".message-content{display:flex;flex-direction:column;align-items:flex-start", page)

    def test_parses_date_sender_and_media_type(self):
        text = "2026/6/16（週二）\n15:31\tPenny\t[語音訊息]\n15:31\t莊閔皓\t[照片]\n"
        messages = parse_chat_media(text)
        self.assertEqual([(m.kind, m.sender, m.timestamp) for m in messages], [
            ("audio", "Penny", datetime(2026, 6, 16, 15, 31)),
            ("photo", "莊閔皓", datetime(2026, 6, 16, 15, 31)),
        ])

    def test_does_not_shift_media_when_a_message_is_missing(self):
        first = ChatMedia("photo", datetime(2026, 6, 16, 15, 21), "莊閔皓", 2)
        later = ChatMedia("photo", datetime(2026, 6, 16, 15, 25), "莊閔皓", 3)
        file = MediaFile(Path("240402"), "photo", ".jpg", datetime(2026, 6, 16, 15, 25, 49))
        matches, unmatched, _ = match_media([first, later], [file])
        self.assertNotIn(2, matches)
        self.assertEqual(matches[3], file)
        self.assertEqual(unmatched["photo"], [])

    def test_matches_unique_same_day_file_when_cache_time_is_wrong(self):
        message = ChatMedia("photo", datetime(2026, 1, 21, 19, 13), "Penny", 2)
        file = MediaFile(Path("134047"), "photo", ".jpg", datetime(2026, 1, 21, 22, 42, 43))
        matches, unmatched, methods = match_media([message], [file])
        self.assertEqual(matches[2], file)
        self.assertEqual(methods[2], "日期唯一候選")
        self.assertEqual(unmatched["photo"], [])

    def test_matches_same_day_photo_batch_in_numeric_order(self):
        messages = [
            ChatMedia("photo", datetime(2026, 1, 21, 19, 13), "Penny", 2),
            ChatMedia("photo", datetime(2026, 1, 21, 19, 13), "Penny", 3),
        ]
        files = [
            MediaFile(Path("134047"), "photo", ".jpg", datetime(2026, 1, 21, 22, 42, 43)),
            MediaFile(Path("134048"), "photo", ".jpg", datetime(2026, 1, 21, 22, 42, 44)),
        ]
        matches, unmatched, methods = match_media(messages, files)
        self.assertEqual([matches[line].path.name for line in (2, 3)], ["134047", "134048"])
        self.assertEqual([methods[line] for line in (2, 3)], ["日期整批順序", "日期整批順序"])
        self.assertEqual(unmatched["photo"], [])

    def test_does_not_guess_when_same_day_counts_differ(self):
        messages = [
            ChatMedia("photo", datetime(2026, 1, 21, 19, 13), "Penny", 2),
            ChatMedia("photo", datetime(2026, 1, 21, 19, 13), "Penny", 3),
        ]
        file = MediaFile(Path("134047"), "photo", ".jpg", datetime(2026, 1, 21, 22, 42, 43))
        matches, unmatched, _ = match_media(messages, [file])
        self.assertEqual(matches, {})
        self.assertEqual(unmatched["photo"], [file])

    def test_does_not_use_same_day_fallback_for_audio(self):
        message = ChatMedia("audio", datetime(2025, 9, 18, 22, 24), "Penny", 2)
        file = MediaFile(Path("voice_123559.aac"), "audio", ".aac", datetime(2025, 9, 18, 22, 28, 29))
        matches, unmatched, _ = match_media([message], [file])
        self.assertEqual(matches, {})
        self.assertEqual(unmatched["audio"], [file])

    def test_same_minute_audio_keeps_original_order(self):
        messages = [
            ChatMedia("audio", datetime(2026, 6, 16, 15, 31), "Penny", 2),
            ChatMedia("audio", datetime(2026, 6, 16, 15, 31), "Penny", 3),
            ChatMedia("audio", datetime(2026, 6, 16, 15, 32), "Penny", 4),
        ]
        files = [
            MediaFile(Path("voice_1.aac"), "audio", ".aac", datetime(2026, 6, 16, 15, 31, 23)),
            MediaFile(Path("voice_2.aac"), "audio", ".aac", datetime(2026, 6, 16, 15, 31, 50)),
            MediaFile(Path("voice_3.aac"), "audio", ".aac", datetime(2026, 6, 16, 15, 32, 12)),
        ]
        matches, _, _ = match_media(messages, files)
        self.assertEqual([matches[line].path.name for line in (2, 3, 4)], ["voice_1.aac", "voice_2.aac", "voice_3.aac"])

    def test_uses_order_only_between_two_time_confirmed_anchors(self):
        messages = [
            ChatMedia("photo", datetime(2026, 7, 20, 20, 33), "莊閔皓", 2),
            ChatMedia("photo", datetime(2026, 7, 20, 20, 37), "Penny", 3),
            ChatMedia("photo", datetime(2026, 7, 20, 20, 39), "Penny", 4),
            ChatMedia("photo", datetime(2026, 7, 21, 3, 29), "莊閔皓", 5),
        ]
        files = [
            MediaFile(Path("269642"), "photo", ".jpg", datetime(2026, 7, 20, 20, 33, 41)),
            MediaFile(Path("269664"), "photo", ".jpg", datetime(2026, 7, 20, 20, 40, 35)),
            MediaFile(Path("269693"), "photo", ".jpg", datetime(2026, 7, 20, 20, 40, 35)),
            MediaFile(Path("269843"), "photo", ".jpg", datetime(2026, 7, 21, 3, 29, 23)),
        ]
        matches, unmatched, methods = match_media(messages, files)
        self.assertEqual([matches[line].path.name for line in (3, 4)], ["269664", "269693"])
        self.assertEqual([methods[line] for line in (3, 4)], ["順序推定", "順序推定"])
        self.assertEqual(unmatched["photo"], [])


if __name__ == "__main__":
    unittest.main()
