import html
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PHOTO = "[照片]"
VOICE = "[語音訊息]"
VIDEO = "[影片]"
MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".mp4", ".mov", ".m4a", ".aac", ".amr", ".3gp"}
DATE_LINE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})(?:（.*）)?$")
MESSAGE_LINE = re.compile(r"^(\d{1,2}):(\d{2})\t([^\t]+)\t(.*)$")


@dataclass(frozen=True)
class ChatMedia:
    kind: str
    timestamp: datetime
    sender: str
    line_number: int


@dataclass(frozen=True)
class MediaFile:
    path: Path
    kind: str
    suffix: str
    timestamp: datetime


def open_line_cache_folder():
    # MTP phone folders are Windows Shell objects, not normal C:\ paths.
    script = r'''
$shell = New-Object -ComObject Shell.Application
$target = $null
foreach ($device in $shell.NameSpace(17).Items()) {
    try {
        foreach ($storage in $device.GetFolder().Items()) {
            $folder = $storage.GetFolder()
            foreach ($name in @('Android', 'data', 'jp.naver.line.android', 'files', 'chats')) {
                $item = $folder.ParseName($name)
                if (-not $item) { $folder = $null; break }
                $folder = $item.GetFolder()
            }
            if ($folder) { $target = $folder; break }
        }
    } catch { }
    if ($target) { break }
}
if (-not $target) { throw '找不到可讀取的 LINE chats 資料夾。請連接手機、解鎖、選擇「檔案傳輸」，並確認 LINE 已安裝。' }
$target.Self.InvokeVerb('open')
'''
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "無法開啟 LINE 快取資料夾。")


def media_type(path: Path):
    suffix = path.suffix.lower()
    # LINE voice messages can be ISO MP4 containers while retaining an .aac name.
    if suffix in {".aac", ".m4a", ".amr", ".3gp"}:
        return "audio", suffix
    try:
        with path.open("rb") as f:
            head = f.read(32)
            f.seek(4)
            box = f.read(12)
    except OSError:
        return None
    if head.startswith(b"\xff\xd8\xff"):
        return "photo", ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "photo", ".png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "photo", ".gif"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "photo", ".webp"
    if head[4:12] == b"ftypheic" or head[4:12] == b"ftypheix":
        return "photo", ".heic"
    if head.startswith(b"ID3") or head.startswith(b"\xff\xfb") or head.startswith(b"\xff\xf3"):
        return "audio", ".mp3"
    if head.startswith(b"#!AMR"):
        return "audio", ".amr"
    if box[:4] == b"ftyp":
        brand = box[4:8]
        if brand in {b"M4A ", b"M4B ", b"mp42", b"isom", b"M4V ", b"qt  "}:
            return ("audio", ".m4a") if brand in {b"M4A ", b"M4B "} else ("video", ".mp4")
    return None


def natural_key(path: Path):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", path.name)]


def media_id(path: Path):
    numbers = re.findall(r"\d+", path.stem)
    return int(numbers[-1]) if numbers else None


def index_media(folder: Path):
    photos, voices, videos = [], [], []
    for path in folder.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".thumb", ".hash", ".hmac"}:
            continue
        detected = media_type(path)
        if not detected and path.suffix.lower() in MEDIA_EXTENSIONS:
            suffix = path.suffix.lower()
            kind = "audio" if suffix in {".m4a", ".aac", ".amr", ".3gp"} else "video" if suffix in {".mp4", ".mov"} else "photo"
            detected = (kind, suffix)
        if detected:
            item = MediaFile(path, detected[0], detected[1], datetime.fromtimestamp(path.stat().st_mtime))
            (photos if item.kind == "photo" else voices if item.kind == "audio" else videos).append(item)
    photos.sort(key=lambda x: (x.timestamp, natural_key(x.path)))
    voices.sort(key=lambda x: (x.timestamp, natural_key(x.path)))
    videos.sort(key=lambda x: (x.timestamp, natural_key(x.path)))
    return photos, voices, videos


def parse_chat_media(text: str):
    current_date = None
    messages = []
    for line_number, line in enumerate(text.splitlines(), 1):
        date_match = DATE_LINE.match(line)
        if date_match:
            current_date = tuple(map(int, date_match.groups()))
            continue
        message_match = MESSAGE_LINE.match(line)
        if not current_date or not message_match:
            continue
        hour, minute, sender, content = message_match.groups()
        kind = "photo" if PHOTO in content else "audio" if VOICE in content else "video" if VIDEO in content else None
        if kind:
            messages.append(ChatMedia(kind, datetime(*current_date, int(hour), int(minute)), sender, line_number))
    return messages


def match_media(chat_media, media):
    """Match by time first, then only use provable cache-file ordering."""
    available = {"photo": [], "video": [], "audio": []}
    for item in media:
        available[item.kind].append(item)
    matches = {}
    methods = {}
    for message in sorted(chat_media, key=lambda x: (x.timestamp, x.line_number)):
        # The text export has no seconds. Permit only this minute, plus five seconds
        # for a cache write crossing a minute boundary.
        start = message.timestamp
        end = start + timedelta(seconds=64)
        candidates = [item for item in available[message.kind] if start <= item.timestamp <= end]
        if not candidates:
            continue
        item = min(candidates, key=lambda x: (x.timestamp, natural_key(x.path)))
        matches[message.line_number] = item
        methods[message.line_number] = "同分鐘"
        available[message.kind].remove(item)

    # Numeric names are increasing LINE cache IDs, not timestamps. They are useful
    # only between two time-confirmed items in the same three-digit ID batch.
    previous_anchors = {}
    ordered_messages = sorted(chat_media, key=lambda x: (x.line_number, x.timestamp))
    for message in ordered_messages:
        if methods.get(message.line_number) != "同分鐘":
            continue
        identifier = media_id(matches[message.line_number].path)
        if identifier is None:
            continue
        key = (message.kind, str(identifier)[:3])
        previous = previous_anchors.get(key)
        previous_anchors[key] = (message, matches[message.line_number], identifier)
        if not previous:
            continue
        previous_message, _, previous_id = previous
        messages_between = [
            candidate for candidate in ordered_messages
            if candidate.kind == message.kind
            and previous_message.line_number < candidate.line_number < message.line_number
            and candidate.line_number not in matches
        ]
        files_between = [
            candidate for candidate in available[message.kind]
            if (candidate_id := media_id(candidate.path)) is not None
            and previous_id < candidate_id < identifier
        ]
        if not messages_between or len(messages_between) != len(files_between):
            continue
        for candidate_message, candidate_file in zip(messages_between, sorted(files_between, key=lambda x: media_id(x.path))):
            matches[candidate_message.line_number] = candidate_file
            methods[candidate_message.line_number] = "順序推定"
            available[message.kind].remove(candidate_file)

    # Android can rewrite a photo cache file's modification time hours after receipt.
    # A whole same-day photo batch is safe only when its remaining message and
    # cache-file counts agree exactly. Audio and video stay strict.
    remaining_messages = [message for message in chat_media if message.line_number not in matches]
    for kind in ("photo",):
        by_date = {}
        for message in remaining_messages:
            if message.kind == kind:
                by_date.setdefault(message.timestamp.date(), [[], []])[0].append(message)
        for item in available[kind]:
            by_date.setdefault(item.timestamp.date(), [[], []])[1].append(item)
        for messages, files in by_date.values():
            if messages and len(messages) == len(files):
                method = "日期唯一候選" if len(messages) == 1 else "日期整批順序"
                for message, item in zip(
                    sorted(messages, key=lambda x: (x.timestamp, x.line_number)),
                    sorted(files, key=lambda x: (media_id(x.path) is None, media_id(x.path), natural_key(x.path))),
                ):
                    matches[message.line_number] = item
                    methods[message.line_number] = method
                    available[kind].remove(item)
    return matches, available, methods


def write_match_report(output_folder: Path, chat_media, matches, unmatched_media, methods, media_folder: Path):
    lines = ["LINE 媒體嚴格時間配對報告", "", "規則：優先配對同一分鐘內的同類型快取檔。兩個同分鐘錨點間，若同前三位檔名群組的未配對數量完全相同，才會順序推定。若同日期的剩餘照片訊息和照片檔案數量完全相同，會依檔名順序整批配對。其他情況不配對。", ""]
    matched = 0
    for item in chat_media:
        media = matches.get(item.line_number)
        if media:
            delta = abs((media.timestamp - item.timestamp).total_seconds())
            method = methods[item.line_number]
            lines.append(f"已配對（{method}）\t{item.timestamp:%Y/%m/%d %H:%M}\t{item.sender}\t{item.kind}\t{media.path.name}\t差 {delta:.0f} 秒")
            matched += 1
        else:
            lines.append(f"快取不存在或時間不符\t{item.timestamp:%Y/%m/%d %H:%M}\t{item.sender}\t{item.kind}")
    for kind, files in unmatched_media.items():
        for media in files:
            lines.append(f"未使用快取\t{media.timestamp:%Y/%m/%d %H:%M:%S}\t{kind}\t{media.path.name}")
    thumbs_without_original = []
    for thumb in media_folder.rglob("*.thumb"):
        original = thumb.with_suffix("")
        if not original.exists():
            thumbs_without_original.append(thumb)
            lines.append(f"只有預覽圖，原始檔缺失\t{datetime.fromtimestamp(thumb.stat().st_mtime):%Y/%m/%d %H:%M:%S}\t{thumb.name}")
    lines.extend(["", f"摘要：已配對 {matched}，未配對訊息 {len(chat_media) - matched}，未使用快取 {sum(map(len, unmatched_media.values()))}，只有預覽圖 {len(thumbs_without_original)}。"])
    report = output_folder / "媒體配對報告.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def convert_chat(chat_file: Path, media_folder: Path, output_folder: Path, log):
    photos, voices, videos = index_media(media_folder)
    text = chat_file.read_text(encoding="utf-8-sig", errors="replace")
    chat_media = parse_chat_media(text)
    matches, unmatched_media, methods = match_media(chat_media, [*photos, *voices, *videos])
    output_folder.mkdir(parents=True, exist_ok=True)
    photo_dir = output_folder / "media" / "photos"
    audio_dir = output_folder / "media" / "audio"
    video_dir = output_folder / "media" / "videos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)

    photo_i = voice_i = video_i = 0
    missing_photos = missing_voices = missing_videos = 0
    body = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split("\t", 2)
        if len(fields) == 3:
            time, sender, content = fields
            escaped_content = html.escape(content)
            if PHOTO in content:
                media = matches.get(line_number)
                if media:
                    src, suffix = media.path, media.suffix
                    name = f"photo_{photo_i + 1:05d}{suffix}"
                    shutil.copy2(src, photo_dir / name)
                    escaped_content = escaped_content.replace(PHOTO, f'<img src="media/photos/{name}" loading="lazy" alt="照片">')
                    photo_i += 1
                else:
                    missing_photos += 1
            elif VOICE in content:
                media = matches.get(line_number)
                if media:
                    src, suffix = media.path, media.suffix
                    name = f"voice_{voice_i + 1:05d}{suffix}"
                    shutil.copy2(src, audio_dir / name)
                    escaped_content = escaped_content.replace(VOICE, f'<audio controls preload="none" src="media/audio/{name}"></audio>')
                    voice_i += 1
                else:
                    missing_voices += 1
            elif VIDEO in content:
                media = matches.get(line_number)
                if media:
                    src, suffix = media.path, media.suffix
                    name = f"video_{video_i + 1:05d}{suffix}"
                    shutil.copy2(src, video_dir / name)
                    escaped_content = escaped_content.replace(VIDEO, f'<video controls preload="metadata" src="media/videos/{name}"></video>')
                    video_i += 1
                else:
                    missing_videos += 1
            side = "right" if sender == "莊閔皓" else "left"
            avatar = f'<div class="avatar">{html.escape(sender[:1])}</div>' if side == "left" else ""
            body.append(f'<div class="message-row {side}">{avatar}<div class="message-content"><div class="meta"><span>{html.escape(sender)}</span><time>{html.escape(time)}</time></div><div class="bubble">{escaped_content}</div></div></div>')
            continue

        escaped = html.escape(line)
        if re.match(r"^\d{4}/\d{1,2}/\d{1,2}", line):
            body.append(f'<div class="date-divider"><span>{escaped}</span></div>')
        else:
            body.append(f'<div class="notice">{escaped}</div>')
        continue

    title = html.escape(chat_file.stem)
    display_name = html.escape(re.sub(r"的聊天(?:記錄)?$", "", chat_file.stem))
    page = f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
*{{box-sizing:border-box}}body{{font-family:system-ui,"Microsoft JhengHei",sans-serif;background:#86a9d6;color:#172235;margin:0}}
body:before{{content:"";position:fixed;inset:0;background:radial-gradient(circle at 18% 35%,#ffffff18 0 12%,transparent 30%),radial-gradient(circle at 82% 70%,#ffffff12 0 10%,transparent 28%);pointer-events:none}}
.topbar{{height:76px;background:#91b2dc;display:flex;align-items:center;gap:18px;padding:10px max(16px,calc((100% - 920px)/2));position:sticky;top:0;z-index:3;border-bottom:1px solid #6f95c4}}
.topbar .back{{font-size:38px;font-weight:200;line-height:1}}.topbar h1{{font-size:23px;margin:0;flex:1;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.topbar .tools{{font-size:26px;letter-spacing:10px;white-space:nowrap}}
main{{max-width:920px;margin:0 auto;padding:18px 14px 40px;position:relative}}.message-row{{display:flex;align-items:flex-end;gap:8px;margin:11px 0;max-width:86%}}.message-row.left{{margin-right:auto}}.message-row.right{{margin-left:auto;flex-direction:row-reverse}}
.avatar{{width:42px;height:42px;flex:0 0 42px;border-radius:50%;background:#5d7697;color:#fff;display:grid;place-items:center;font-size:18px;box-shadow:0 1px 3px #425e8055}}
.message-content{{display:flex;flex-direction:column;align-items:flex-start;min-width:0;max-width:calc(100% - 50px)}}.right .message-content{{align-items:flex-end}}.meta{{font-size:11px;color:#405a78;line-height:1.35;margin:0 8px 3px}}.right .meta{{text-align:right}}.meta span,.meta time{{display:inline-block;margin-right:8px}}
.bubble{{width:fit-content;max-width:100%;background:#fff;border-radius:4px 18px 18px 18px;padding:10px 13px;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 1px 2px #4f729955;min-width:46px;font-size:16px}}.right .bubble{{background:#9bea81;border-radius:18px 4px 18px 18px}}
.date-divider{{text-align:center;margin:18px 0 12px;color:#3e5879;font-size:12px}}.date-divider span{{background:#d0e0f2aa;padding:5px 12px;border-radius:14px}}.notice{{text-align:center;color:#3e5879;font-size:12px;margin:12px 0}}
img{{display:block;max-width:min(620px,70vw);max-height:620px;margin-top:5px;border-radius:10px}}audio{{max-width:100%;vertical-align:middle}}video{{display:block;max-width:min(620px,70vw);max-height:620px;margin-top:5px;border-radius:10px}}
@media(max-width:600px){{.topbar{{height:64px;padding:8px 14px}}.topbar h1{{font-size:20px}}main{{padding-left:8px;padding-right:8px}}.message-row{{max-width:96%}}.avatar{{width:34px;height:34px;flex-basis:34px;font-size:15px}}.message-content{{max-width:calc(100% - 42px)}}.meta{{font-size:10px}}img,video{{max-width:78vw}}}}
</style></head><body><header class="topbar"><h1>{display_name}</h1></header><main>{''.join(body)}</main></body></html>'''
    output_file = output_folder / "chat.html"
    output_file.write_text(page, encoding="utf-8")
    report = write_match_report(output_folder, chat_media, matches, unmatched_media, methods, media_folder)
    log(f"完成：照片 {photo_i} 張，影片 {video_i} 個，語音 {voice_i} 個")
    if missing_photos or missing_videos or missing_voices:
        log(f"找不到媒體：照片 {missing_photos} 張，影片 {missing_videos} 個，語音 {missing_voices} 個")
    log(f"已建立嚴格配對報告：{report.name}")
    return output_file


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LINE 聊天記錄轉 HTML")
        self.geometry("700x450")
        self.resizable(False, False)
        self.chat = tk.StringVar()
        self.media = tk.StringVar()
        self.output = tk.StringVar()
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="LINE 聊天記錄轉換器", font=("Microsoft JhengHei", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="照下面順序選好資料後，按「開始整理」即可。", wraplength=620).pack(anchor="w", pady=(4, 14))
        self._row(frame, "1. 聊天文字檔：", self.chat, self.pick_chat, "選擇 TXT")
        ttk.Button(frame, text="2. 開啟連接手機的 LINE 資料夾", command=self.open_phone_cache).pack(anchor="w", pady=(2, 6))
        self._row(frame, "3. LINE 資料夾：", self.media, self.pick_media, "選擇資料夾")
        self._row(frame, "4. 輸出資料夾：", self.output, self.pick_output, "選擇資料夾")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(18, 8))
        self.status = tk.StringVar(value="等待開始")
        ttk.Label(frame, textvariable=self.status).pack(anchor="w")
        ttk.Button(frame, text="開始整理", command=self.start).pack(anchor="e", pady=(18, 0))

    def _row(self, parent, label, variable, command, button):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text=label, width=13).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=button, command=command).pack(side="left", padx=(8, 0))

    def pick_chat(self):
        value = filedialog.askopenfilename(filetypes=[("LINE 聊天記錄", "*.txt"), ("所有檔案", "*.*")])
        if value:
            self.chat.set(value)
            if not self.output.get(): self.output.set(str(Path(value).parent / (Path(value).stem + "HTML")))

    def pick_media(self):
        value = filedialog.askdirectory(title="請選擇聊天室裡的 messages 資料夾")
        if value: self.media.set(value)

    def open_phone_cache(self):
        self.status.set("正在開啟手機 LINE 快取資料夾...")
        threading.Thread(target=self.open_phone_cache_worker, daemon=True).start()

    def open_phone_cache_worker(self):
        try:
            open_line_cache_folder()
            self.after(0, self.status.set, "已開啟手機的 LINE chats 資料夾")
        except Exception as exc:
            self.after(0, self.failed, str(exc))

    def pick_output(self):
        value = filedialog.askdirectory(title="選擇輸出資料夾")
        if value: self.output.set(value)

    def start(self):
        if not all((self.chat.get(), self.media.get(), self.output.get())):
            messagebox.showwarning("還沒選好", "請依照 1 到 4 的順序，選好聊天文字檔、LINE 資料夾和輸出資料夾。")
            return
        self.progress.start(10)
        self.status.set("正在整理照片、影片和語音...")
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            result = convert_chat(Path(self.chat.get()), Path(self.media.get()), Path(self.output.get()), lambda s: self.after(0, self.status.set, s))
            self.after(0, self.finished, result)
        except Exception as exc:
            self.after(0, self.failed, str(exc))

    def finished(self, result):
        self.progress.stop()
        self.status.set("轉換完成")
        if messagebox.askyesno("完成", f"已建立：\n{result}\n\n要開啟輸出資料夾嗎？"):
            os.startfile(result.parent)

    def failed(self, error):
        self.progress.stop()
        self.status.set("轉換失敗")
        messagebox.showerror("轉換失敗", error)


if __name__ == "__main__":
    App().mainloop()
