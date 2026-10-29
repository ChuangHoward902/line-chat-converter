import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from line_chat_converter import ChatMedia, MediaFile, convert_chat, index_media, match_media, parse_chat_media

JPEG = b"\xff\xd8\xff\xe0" + bytes(28)
GIF = b"GIF89a" + bytes(26)


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
        self.assertEqual(methods[2], "號碼順序")
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
        self.assertEqual([methods[line] for line in (2, 3)], ["號碼順序", "號碼順序"])
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

    def test_does_not_guess_audio_without_time_or_complete_order(self):
        messages = [
            ChatMedia("audio", datetime(2025, 9, 18, 22, 24), "Penny", 2),
            ChatMedia("audio", datetime(2025, 9, 18, 22, 30), "Penny", 3),
        ]
        file = MediaFile(Path("voice_123559.aac"), "audio", ".aac", datetime(2025, 9, 18, 22, 28, 29))
        matches, unmatched, _ = match_media(messages, [file])
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
            ChatMedia("photo", datetime(2026, 7, 21, 4, 0), "Penny", 6),
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
        self.assertNotIn(6, matches)
        self.assertEqual(unmatched["photo"], [])

    def test_matches_whole_chat_in_cache_id_order_when_file_times_are_lost(self):
        copied = datetime(2026, 10, 28, 19, 1)
        messages = [
            ChatMedia("photo", datetime(2026, 1, 23, 1, 26), "Penny", 2),
            ChatMedia("audio", datetime(2026, 1, 23, 1, 27), "莊閔皓", 3),
            ChatMedia("video", datetime(2026, 1, 24, 9, 0), "Penny", 4),
            ChatMedia("photo", datetime(2026, 1, 24, 9, 0), "Penny", 5),
        ]
        files = [
            MediaFile(Path("1004"), "photo", ".jpg", copied),
            MediaFile(Path("voice_1002.aac"), "audio", ".aac", copied),
            MediaFile(Path("1001"), "photo", ".jpg", copied),
            MediaFile(Path("1003.thumb"), "video", ".jpg", copied, preview=True),
        ]
        matches, unmatched, methods = match_media(messages, files)
        self.assertEqual([matches[line].path.name for line in (2, 3, 4, 5)], ["1001", "voice_1002.aac", "1003.thumb", "1004"])
        self.assertEqual(set(methods.values()), {"號碼順序"})
        self.assertEqual(unmatched, {"photo": [], "video": [], "audio": []})

    def test_late_cache_write_does_not_shift_later_photos(self):
        # The first photo was cached almost an hour late; by time alone all three photos moved.
        messages = [
            ChatMedia("photo", datetime(2026, 6, 1, 23, 59), "Penny", 2),
            ChatMedia("photo", datetime(2026, 6, 1, 23, 59), "Penny", 3),
            ChatMedia("photo", datetime(2026, 6, 2, 0, 0), "Penny", 4),
        ]
        files = [
            MediaFile(Path("501"), "photo", ".jpg", datetime(2026, 6, 2, 0, 54, 59)),
            MediaFile(Path("502"), "photo", ".jpg", datetime(2026, 6, 1, 23, 59, 41)),
            MediaFile(Path("503"), "photo", ".jpg", datetime(2026, 6, 2, 0, 0, 4)),
        ]
        matches, _, _ = match_media(messages, files)
        self.assertEqual([matches[line].path.name for line in (2, 3, 4)], ["501", "502", "503"])

    def test_same_minute_photos_follow_cache_ids_not_write_times(self):
        messages = [ChatMedia("photo", datetime(2026, 6, 3, 1, 12), "Penny", line) for line in (2, 3, 4)]
        files = [
            MediaFile(Path("601"), "photo", ".jpg", datetime(2026, 6, 3, 1, 12, 53)),
            MediaFile(Path("602"), "photo", ".jpg", datetime(2026, 6, 3, 1, 12, 53)),
            MediaFile(Path("603"), "photo", ".jpg", datetime(2026, 6, 3, 1, 12, 44)),
        ]
        matches, _, _ = match_media(messages, files)
        self.assertEqual([matches[line].path.name for line in (2, 3, 4)], ["601", "602", "603"])

    def test_time_evidence_overrides_cache_id_order_when_they_disagree(self):
        messages = [
            ChatMedia("photo", datetime(2026, 6, 4, 10, 0), "Penny", 2),
            ChatMedia("photo", datetime(2026, 6, 4, 11, 0), "Penny", 3),
            ChatMedia("photo", datetime(2026, 6, 4, 12, 0), "Penny", 4),
        ]
        files = [
            MediaFile(Path("701"), "photo", ".jpg", datetime(2026, 6, 4, 11, 0, 10)),
            MediaFile(Path("702"), "photo", ".jpg", datetime(2026, 6, 4, 12, 0, 10)),
            MediaFile(Path("703"), "photo", ".jpg", datetime(2026, 6, 4, 15, 0, 0)),
        ]
        matches, unmatched, methods = match_media(messages, files)
        self.assertNotIn(2, matches)
        self.assertEqual([matches[line].path.name for line in (3, 4)], ["701", "702"])
        self.assertEqual([methods[line] for line in (3, 4)], ["同分鐘", "同分鐘"])
        self.assertEqual([item.path.name for item in unmatched["photo"]], ["703"])

    def test_index_prefers_original_and_falls_back_to_preview(self):
        files = {
            "100": JPEG, "100.original": GIF, "100.thumb": JPEG,
            "200.thumb": JPEG, "200-hash": bytes(32), "200-hmac": bytes(32),
            "300.thumb": JPEG,
            "voice_400.aac": b"\x00\x00\x00\x1cftypM4A ",
            "500": b"%PDF-1.4",
        }
        with TemporaryDirectory() as directory:
            for name, data in files.items():
                (Path(directory) / name).write_bytes(data)
            photos, voices, videos = index_media(Path(directory))

        self.assertEqual([(item.path.name, item.suffix, item.preview) for item in photos], [("100.original", ".gif", False), ("300.thumb", ".jpg", True)])
        self.assertEqual([(item.path.name, item.preview) for item in videos], [("200.thumb", True)])
        self.assertEqual([item.path.name for item in voices], ["voice_400.aac"])

    def test_preview_is_shown_with_a_note(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "messages").mkdir()
            (root / "messages" / "300.thumb").write_bytes(JPEG)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t[照片]\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")
            copied = (root / "output" / "media" / "photos" / "photo_00001.jpg").exists()

        self.assertTrue(copied)
        self.assertIn('<div class="message-row left" id="m2">', page)
        self.assertIn('<img src="media/photos/photo_00001.jpg" loading="lazy" alt="預覽圖" data-caption="Penny • 2026/6/16（週二） 15:31"><span class="note">只剩預覽圖</span>', page)
        self.assertIn('<div id="viewer" hidden>', page)
        self.assertIn('<div id="scroll-date" aria-hidden="true"></div>', page)

    def test_days_can_be_searched_and_jumped_to(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t好\n\n2026/6/18（週四）\n09:00\tPenny\t早\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")

        self.assertIn('<section class="day" data-date="2026-06-16"', page)
        self.assertIn('<section class="day" data-date="2026-06-18"', page)
        self.assertIn('<input type="date" id="jump" title="跳到日期" aria-label="跳到日期" min="2026-06-16" max="2026-06-18">', page)
        self.assertIn('<div id="search" hidden>', page)

    def test_multiline_message_stays_in_one_bubble(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t第一行\n第二行\n\t•\t清單\n\n15:32\tPenny\t好\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")

        self.assertEqual(page.count('class="message-row'), 2)
        self.assertNotIn('class="notice"', page)
        self.assertIn('<div class="bubble">第一行\n第二行\n\t•\t清單</div>', page)

    def test_album_and_statistics_pages(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "messages").mkdir()
            for name in ("100", "100.thumb", "200.thumb"):
                (root / "messages" / name).write_bytes(JPEG)
            chat = root / "聊天.txt"
            chat.write_text("[LINE] 與Penny的聊天記錄\n\n2026/6/16（週二）\n15:31\tPenny\t[照片]\n15:32\t阿明\t好😂😂\n15:40\t阿明\t通話時間 1:05:00\n\n"
                            "2026/6/17（週三）\n09:00\tPenny\t[照片]\n09:01\tPenny\t未接來電\n", encoding="utf-8")
            convert_chat(chat, root / "messages", root / "output", lambda _: None)
            album = (root / "output" / "photos.html").read_text(encoding="utf-8")
            stats = (root / "output" / "stats.html").read_text(encoding="utf-8")
            thumb = (root / "output" / "media" / "thumbs" / "photo_00001.jpg").exists()

        self.assertTrue(thumb)
        self.assertIn("<h1>相簿（2 張）</h1>", album)
        self.assertIn('<img src="media/thumbs/photo_00001.jpg" data-full="media/photos/photo_00001.jpg" data-caption="Penny • 2026/6/16（週二） 15:31" data-link="chat.html#m4" loading="lazy" alt="">', album)
        self.assertIn('<img src="media/photos/photo_00002.jpg" data-full="media/photos/photo_00002.jpg"', album)
        self.assertIn('<p class="who">與Penny的聊天</p><p class="figure">5</p>', stats)
        self.assertIn('<div class="label">最多的一天</div><div class="value"><a href="chat.html#d2026-06-16">2026/6/16</a></div><div class=sub>3 則</div>', stats)
        self.assertIn('<div class="label">最長連續聊天</div><div class="value">2 天</div>', stats)
        self.assertIn('<div class="label">最長一通</div><div class="value">1:05:00</div>', stats)
        self.assertIn('<div class="label">未接來電</div><div class="value">1 次</div>', stats)
        self.assertIn('<li><span class="e">😂</span><span class="n">2 次</span></li>', stats)

    def test_links_and_calls_are_shown_as_such(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t看這個https://example.com/a?b=1&c=2好嗎\n15:32\tPenny\t通話時間 1:23\n15:33\tPenny\t未接來電\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")

        self.assertIn('看這個<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">https://example.com/a?b=1&amp;c=2</a>好嗎', page)
        self.assertIn('<span class="call">📞 通話時間 1:23</span>', page)
        self.assertIn('<span class="call missed">📞 未接來電</span>', page)

    def test_file_message_links_to_the_cached_file_between_its_media(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "messages").mkdir()
            for name, data in {"100": JPEG, "150": b"%PDF-1.4", "200": JPEG}.items():
                (root / "messages" / name).write_bytes(data)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t[照片]\n15:32\tPenny\t[檔案]\n15:33\tPenny\t[照片]\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")
            copied = (root / "output" / "media" / "files" / "file_00001.pdf").read_bytes()

        self.assertEqual(copied, b"%PDF-1.4")
        self.assertIn('<a class="file" href="media/files/file_00001.pdf" target="_blank">📎 PDF 檔</a>', page)

    def test_rejects_this_tools_own_output_folder(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "media" / "photos").mkdir(parents=True)
            (root / "media" / "photos" / "photo_00001.jpg").write_bytes(JPEG)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t[照片]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "messages 資料夾"):
                convert_chat(chat, root / "media", root / "output", lambda _: None)

    def test_finds_the_matching_chat_inside_the_chats_folder(self):
        chats = {"a1": {"100": JPEG, "voice_101.aac": b"\x00\x00\x00\x1cftypM4A "}, "b2": {"200": JPEG, "201": JPEG}}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for chat_id, files in chats.items():
                (root / "chats" / chat_id / "messages").mkdir(parents=True)
                for name, data in files.items():
                    (root / "chats" / chat_id / "messages" / name).write_bytes(data)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t[照片]\n15:32\tPenny\t[語音訊息]\n", encoding="utf-8")
            logs = []
            convert_chat(chat, root / "chats", root / "output", logs.append)
            copied = sorted(path.name for path in (root / "output" / "media").rglob("*.*"))

        self.assertIn("已找到對應的聊天室資料夾：a1", logs)
        self.assertEqual(copied, ["photo_00001.jpg", "voice_00001.aac"])

    def test_timed_system_line_is_not_merged_into_a_message(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = root / "聊天.txt"
            chat.write_text("2026/6/16（週二）\n15:31\tPenny\t好\n15:32\t阿明加入群組\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")

        self.assertIn('<div class="bubble">好</div>', page)
        self.assertIn('<div class="notice">15:32\t阿明加入群組</div>', page)

    def test_owner_from_export_header_is_shown_on_the_right(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            chat = root / "聊天.txt"
            chat.write_text("[LINE] 與Penny的聊天記錄\n儲存日期：2026/6/16 15:40\n\n2026/6/16（週二）\n15:31\tPenny\t嗨\n15:32\t阿明\t嗨嗨\n", encoding="utf-8")
            output = convert_chat(chat, root / "messages", root / "output", lambda _: None)
            page = output.read_text(encoding="utf-8")

        self.assertIn('<div class="message-row right"><div class="message-content"><div class="meta"><span>阿明</span>', page)
        self.assertIn('<div class="message-row left"><div class="avatar">P</div><div class="message-content"><div class="meta"><span>Penny</span>', page)


if __name__ == "__main__":
    unittest.main()
