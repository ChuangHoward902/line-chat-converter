import html
import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from bisect import bisect_left, bisect_right
from collections import Counter
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
# kind: (text in the export, output folder, file name prefix, HTML)
MEDIA_OUTPUT = {
    "photo": (PHOTO, "photos", "photo", '<img src="{src}" loading="lazy" alt="照片" data-caption="{caption}">'),
    "audio": (VOICE, "audio", "voice", '<audio controls preload="none" src="{src}"></audio>'),
    "video": (VIDEO, "videos", "video", '<video controls preload="metadata" src="{src}"></video>'),
}
PREVIEW_HTML = '<img src="{src}" loading="lazy" alt="預覽圖" data-caption="{caption}"><span class="note">{note}</span>'
FILE = "[檔案]"
CALL = re.compile(r"通話時間 \d+(?::\d{2}){1,2}|未接來電|您已結束通話|取消通話")
# A web address ends at whitespace, quotes, CJK text or emoji.
URL = re.compile("https?://[^\\s<>\"'　-ヿ一-鿿＀-￯\U0001F000-\U0001FAFF]+")
# While scrolling, show the date of the day at the top of the screen; hide it again once scrolling stops.
SCROLL_DATE = '''<div id="scroll-date" aria-hidden="true"></div>
<style>
#scroll-date{position:fixed;top:88px;left:50%;transform:translateX(-50%);z-index:4;background:#c9daeeee;color:#3e5879;font-size:12px;padding:5px 12px;border-radius:14px;box-shadow:0 1px 2px #4f729933;pointer-events:none;opacity:0;transition:opacity .3s}
#scroll-date.show{opacity:1}@media(max-width:600px){#scroll-date{top:74px}}
</style>
<script>
(() => {
  const label = document.getElementById("scroll-date"), topbar = document.querySelector(".topbar");
  const days = [...document.querySelectorAll(".day")];
  let timer, pending = false;
  window.addEventListener("scroll", () => {
    if (pending || !days.length) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      const edge = topbar.getBoundingClientRect().bottom + 12;
      let low = 0, high = days.length - 1;
      while (low < high) {
        const middle = Math.ceil((low + high) / 2);
        if (days[middle].getBoundingClientRect().top <= edge) low = middle;
        else high = middle - 1;
      }
      label.textContent = days[low].querySelector(".date-divider span").textContent;
      label.classList.add("show");
      clearTimeout(timer);
      timer = setTimeout(() => label.classList.remove("show"), 1000);
    });
  }, { passive: true });
})();
</script>'''
# Search messages and jump to a date from the top bar.
SEARCH_TOOLS = '''<div id="search" hidden><input type="search" placeholder="搜尋訊息" aria-label="搜尋訊息"><span class="count"></span><button class="up" aria-label="上一筆">&#8593;</button><button class="down" aria-label="下一筆">&#8595;</button><button class="close" aria-label="關閉搜尋">&#215;</button></div>
<style>
#search{position:fixed;top:76px;left:50%;transform:translateX(-50%);width:min(920px,100%);z-index:5;display:flex;align-items:center;gap:6px;padding:8px 14px;background:#f4f8fdf2;box-shadow:0 2px 6px #34507533}#search[hidden]{display:none}
#search input{flex:1;min-width:0;font:inherit;font-size:16px;padding:7px 12px;border:1px solid #9db6d6;border-radius:18px}#search .count{font-size:13px;color:#405a78;white-space:nowrap}
#search button{font:inherit;font-size:18px;background:none;border:0;color:#2f4a6b;cursor:pointer;padding:4px 8px}.bubble.found{outline:3px solid #f5c542;outline-offset:2px}
body.searching #scroll-date{top:140px}@media(max-width:600px){#search{top:64px}body.searching #scroll-date{top:126px}}
</style>
<script>
(() => {
  const bar = document.getElementById("search"), input = bar.querySelector("input"), count = bar.querySelector(".count");
  const topbar = document.querySelector(".topbar");
  let bubbles = null, hits = [], index = -1, searched = "", timer;
  const go = i => {
    if (!hits.length) return;
    hits[index]?.classList.remove("found");
    index = (i + hits.length) % hits.length;
    hits[index].classList.add("found");
    hits[index].scrollIntoView({ block: "center" });
    count.textContent = `${index + 1} / ${hits.length}`;
  };
  const search = () => {
    hits[index]?.classList.remove("found");
    hits = [];
    index = -1;
    searched = input.value.trim().toLowerCase();
    if (!searched) return void (count.textContent = "");
    bubbles ??= [...document.querySelectorAll(".bubble")];
    hits = bubbles.filter(bubble => bubble.textContent.toLowerCase().includes(searched));
    if (!hits.length) return void (count.textContent = "找不到");
    // Start from the first result at or below the current position.
    const edge = topbar.getBoundingClientRect().bottom + 60;
    const below = hits.findIndex(bubble => bubble.getBoundingClientRect().top >= edge);
    go(below < 0 ? hits.length - 1 : below);
  };
  const close = () => {
    bar.hidden = true;
    document.body.classList.remove("searching");
    hits[index]?.classList.remove("found");
  };
  document.getElementById("search-open").addEventListener("click", () => {
    bar.hidden = false;
    document.body.classList.add("searching");
    input.focus();
    input.select();
  });
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 300); });
  input.addEventListener("keydown", event => {
    if (event.key === "Escape") return close();
    if (event.key !== "Enter") return;
    event.preventDefault();
    clearTimeout(timer);
    if (input.value.trim().toLowerCase() !== searched) search();
    else go(index + (event.shiftKey ? -1 : 1));
  });
  bar.querySelector(".up").addEventListener("click", () => go(index - 1));
  bar.querySelector(".down").addEventListener("click", () => go(index + 1));
  bar.querySelector(".close").addEventListener("click", close);
  const jump = document.getElementById("jump");
  jump.addEventListener("change", () => {
    const days = [...document.querySelectorAll(".day")];
    (days.find(day => day.dataset.date >= jump.value) || days[days.length - 1])?.scrollIntoView({ block: "start" });
  });
})();
</script>'''
# Click a photo to view it full screen; buttons, arrow keys or a swipe move between photos.
PHOTO_VIEWER = '''<div id="viewer" hidden><img alt=""><button class="prev" aria-label="上一張">&#8249;</button><button class="next" aria-label="下一張">&#8250;</button><button class="close" aria-label="關閉">&#215;</button><div class="caption"></div><a class="goto" hidden>在聊天中查看</a><a class="save" download aria-label="下載">&#8615;</a></div>
<style>
img[data-caption]{cursor:zoom-in}#viewer{position:fixed;inset:0;z-index:10;background:#000000ee;display:flex;align-items:center;justify-content:center}#viewer[hidden]{display:none}
#viewer img{width:calc(100vw - 140px);height:calc(100vh - 110px);max-width:none;max-height:none;margin:0;border-radius:0;object-fit:contain}
#viewer button,#viewer a{position:absolute;background:none;border:0;color:#fff;font-size:48px;line-height:1;padding:12px 18px;cursor:pointer;text-decoration:none;opacity:.85}#viewer button:hover,#viewer a:hover{opacity:1}#viewer button[disabled]{visibility:hidden}
#viewer .prev{left:8px;top:50%;transform:translateY(-50%)}#viewer .next{right:8px;top:50%;transform:translateY(-50%)}#viewer .close{top:6px;right:8px;font-size:40px}#viewer .save{right:12px;bottom:10px;font-size:30px}
#viewer .goto{right:72px;bottom:16px;font-size:14px;padding:6px 14px;border:1px solid #ffffff88;border-radius:16px}#viewer .goto[hidden]{display:none}
#viewer .caption{position:absolute;left:16px;bottom:14px;color:#fff;font-size:14px;line-height:1.5;white-space:pre-line}
@media(max-width:600px){#viewer img{width:100vw;height:calc(100vh - 120px)}#viewer .prev,#viewer .next{font-size:40px;padding:12px 8px}}
</style>
<script>
(() => {
  const viewer = document.getElementById("viewer");
  const image = viewer.querySelector("img"), caption = viewer.querySelector(".caption"), save = viewer.querySelector(".save");
  const prev = viewer.querySelector(".prev"), next = viewer.querySelector(".next"), goto = viewer.querySelector(".goto");
  let photos = [], index = 0, touchX = null;
  const show = i => {
    index = Math.max(0, Math.min(photos.length - 1, i));
    const photo = photos[index];
    image.src = save.href = photo.dataset.full || photo.getAttribute("src");
    caption.textContent = `第 ${index + 1} 張，共 ${photos.length} 張\\n${photo.dataset.caption}`;
    goto.hidden = !photo.dataset.link;
    goto.href = photo.dataset.link || "";
    prev.disabled = index === 0;
    next.disabled = index === photos.length - 1;
  };
  const close = () => { viewer.hidden = true; image.removeAttribute("src"); document.body.style.overflow = ""; };
  document.addEventListener("click", event => {
    if (!event.target.matches("img[data-caption]")) return;
    photos = [...document.querySelectorAll("img[data-caption]")];
    viewer.hidden = false;
    document.body.style.overflow = "hidden";
    show(photos.indexOf(event.target));
  });
  prev.addEventListener("click", () => show(index - 1));
  next.addEventListener("click", () => show(index + 1));
  viewer.querySelector(".close").addEventListener("click", close);
  viewer.addEventListener("click", event => { if (event.target === viewer) close(); });
  document.addEventListener("keydown", event => {
    if (viewer.hidden) return;
    if (event.key === "ArrowLeft") show(index - 1);
    else if (event.key === "ArrowRight") show(index + 1);
    else if (event.key === "Escape") close();
  });
  viewer.addEventListener("touchstart", event => { touchX = event.touches[0].clientX; }, { passive: true });
  viewer.addEventListener("touchend", event => {
    const moved = event.changedTouches[0].clientX - touchX;
    if (Math.abs(moved) > 50) show(index + (moved < 0 ? 1 : -1));
  });
})();
</script>'''


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
    preview: bool = False
    thumbnail: Path | None = None


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


def detect_media(path: Path):
    detected = media_type(path)
    if not detected and path.suffix.lower() in MEDIA_EXTENSIONS:
        suffix = path.suffix.lower()
        kind = "audio" if suffix in {".m4a", ".aac", ".amr", ".3gp"} else "video" if suffix in {".mp4", ".mov"} else "photo"
        detected = (kind, suffix)
    return detected


def modified(path: Path):
    return datetime.fromtimestamp(path.stat().st_mtime)


def index_media(folder: Path):
    """One entry per LINE cache ID: the .original if downloaded, else the cached file, else its .thumb preview."""
    groups = {}
    for path in folder.rglob("*"):
        if path.is_file():
            groups.setdefault(media_id(path), []).append(path)
    photos, voices, videos = [], [], []
    for identifier, paths in groups.items():
        previews = [p for p in paths if p.suffix.lower() == ".thumb"]
        # A video whose file is no longer cached leaves only its .thumb and -hash/-hmac files.
        markers = [p for p in paths if p.name.lower().endswith(("-hash", "-hmac", ".hash", ".hmac"))]
        others = sorted((p for p in paths if p not in previews and p not in markers), key=lambda p: p.suffix.lower() != ".original")
        found = [(p, detected) for p in others if (detected := detect_media(p))]
        if identifier is None:
            items = [MediaFile(p, *detected, modified(p)) for p, detected in found]
        elif found:
            items = [MediaFile(found[0][0], *found[0][1], min(map(modified, paths)), thumbnail=previews[0] if previews else None)]
        elif not others and previews and (detected := detect_media(previews[0])):
            items = [MediaFile(previews[0], "video" if markers else detected[0], detected[1], min(map(modified, paths)), preview=True, thumbnail=previews[0])]
        else:
            items = []
        for item in items:
            (photos if item.kind == "photo" else voices if item.kind == "audio" else videos).append(item)
    for items in (photos, voices, videos):
        items.sort(key=lambda x: (media_id(x.path) is None, media_id(x.path) or 0, natural_key(x.path)))
    return photos, voices, videos


def index_files(folder: Path):
    """Cache files that are not media, such as a PDF sent with a [檔案] message."""
    return sorted((path for path in folder.rglob("*") if path.is_file() and path.name.isdigit() and not detect_media(path)), key=media_id)


def file_type(path: Path):
    with path.open("rb") as f:
        head = f.read(4096)
    if head.startswith(b"%PDF"):
        return ".pdf", "PDF 檔"
    if head.startswith(b"PK\x03\x04"):
        return ".zip", "壓縮檔"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as error:
        if error.start < len(head) - 3:  # not just a character cut off at the end of the sample
            return "", "檔案"
    return ".txt", "文字檔"


def match_files(lines, matches, files):
    """Give each [檔案] message the cache file whose ID lies between the media matched around it."""
    anchors = sorted((line, media_id(item.path)) for line, item in matches.items())
    anchor_lines = [line for line, _ in anchors]
    groups = {}
    for line_number, line in enumerate(lines, 1):
        if (match := MESSAGE_LINE.match(line)) and match[4].strip() == FILE:
            k = bisect_left(anchor_lines, line_number)
            bounds = (anchors[k - 1][1] if k else -1, anchors[k][1] if k < len(anchors) else float("inf"))
            groups.setdefault(bounds, []).append(line_number)
    found = {}
    for (low, high), group in groups.items():
        inside = [path for path in files if low < media_id(path) < high]
        if len(inside) == len(group):
            found.update(zip(group, inside))
    return found


def linkify(text):
    """Escape message text and turn web addresses into links."""
    parts, last = [], 0
    for match in URL.finditer(text):
        url = match[0].rstrip(".,!?;:)")
        parts += [html.escape(text[last:match.start()]), f'<a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{html.escape(url)}</a>']
        last = match.start() + len(url)
    parts.append(html.escape(text[last:]))
    return "".join(parts)


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


def time_anchors(messages, files):
    """Message/file index pairs whose only same-minute candidate is each other."""
    times = {}
    for j, item in enumerate(files):
        times.setdefault(item.kind, []).append((item.timestamp, j))
    for values in times.values():
        values.sort()
    pairs = []
    for i, message in enumerate(messages):
        values = times.get(message.kind, [])
        # The text export has no seconds. Permit only this minute, plus five seconds
        # for a cache write crossing a minute boundary.
        start = bisect_left(values, (message.timestamp, -1))
        end = bisect_right(values, (message.timestamp + timedelta(seconds=64), len(files)))
        pairs.extend((i, j) for _, j in values[start:end])
    per_message = Counter(i for i, _ in pairs)
    per_file = Counter(j for _, j in pairs)
    return [(i, j) for i, j in pairs if per_message[i] == per_file[j] == 1]


def increasing_chain(pairs):
    """Longest subset of pairs that moves forward in both chat order and cache-ID order."""
    pairs = sorted(pairs)
    tails, ends, previous = [], [], []
    for k, (_, j) in enumerate(pairs):
        position = bisect_left(tails, j)
        if position == len(tails):
            tails.append(j)
            ends.append(k)
        else:
            tails[position] = j
            ends[position] = k
        previous.append(ends[position - 1] if position else None)
    chain, k = [], ends[-1] if ends else None
    while k is not None:
        chain.append(pairs[k])
        k = previous[k]
    return chain[::-1]


def match_media(chat_media, media):
    """Pair media messages with cache files in LINE cache-ID order; file times only confirm that order."""
    messages = sorted(chat_media, key=lambda x: x.line_number)
    files = sorted((x for x in media if media_id(x.path) is not None), key=lambda x: (media_id(x.path), natural_key(x.path)))
    anchors = time_anchors(messages, files)
    # Numeric names are increasing LINE cache IDs. When every media message has one cache
    # entry of the same kind, the two lists line up, unless the time evidence mostly disagrees.
    # File times alone are unreliable: Android often writes a cache file when it is first opened.
    if [m.kind for m in messages] == [f.kind for f in files] and sum(i == j for i, j in anchors) >= 0.8 * len(anchors):
        pairs = [(i, i, "號碼順序") for i in range(len(messages))]
    else:
        chain = increasing_chain(anchors)
        pairs = [(i, j, "同分鐘") for i, j in chain]
        # Between two time-confirmed items, use ID order only when the kinds line up one to one.
        for (i0, j0), (i1, j1) in zip(chain, chain[1:]):
            between = list(zip(range(i0 + 1, i1), range(j0 + 1, j1)))
            if between and i1 - i0 == j1 - j0 and all(messages[i].kind == files[j].kind for i, j in between):
                pairs.extend((i, j, "順序推定") for i, j in between)
    matches = {messages[i].line_number: files[j] for i, j, _ in pairs}
    methods = {messages[i].line_number: method for i, _, method in pairs}
    used = set(matches.values())
    available = {"photo": [], "video": [], "audio": []}
    for item in media:
        if item not in used:
            available[item.kind].append(item)
    return matches, available, methods


def write_match_report(output_folder: Path, chat_media, matches, unmatched_media, methods, media_folder: Path):
    lines = ["LINE 媒體配對報告", "", "規則：快取檔名的數字是 LINE 依訊息先後給的號碼。若聊天記錄的每則照片、影片、語音都依序對得上同類型的快取，而且同分鐘的時間證據也大致吻合，就照號碼順序配對。否則只採用同一分鐘內唯一候選、且不違反號碼順序的配對；兩個這樣的配對之間，類型逐一對得上才照號碼順序補上。其他情況不配對。只剩預覽圖的照片或影片會以預覽圖顯示。", ""]
    matched = previews = 0
    for item in chat_media:
        media = matches.get(item.line_number)
        if media:
            delta = abs((media.timestamp - item.timestamp).total_seconds())
            method = methods[item.line_number] + ("，預覽圖" if media.preview else "")
            lines.append(f"已配對（{method}）\t{item.timestamp:%Y/%m/%d %H:%M}\t{item.sender}\t{item.kind}\t{media.path.name}\t差 {delta:.0f} 秒")
            matched += 1
            previews += media.preview
        else:
            lines.append(f"未配對\t{item.timestamp:%Y/%m/%d %H:%M}\t{item.sender}\t{item.kind}")
    for kind, files in unmatched_media.items():
        for media in files:
            lines.append(f"未使用快取\t{media.timestamp:%Y/%m/%d %H:%M:%S}\t{kind}\t{media.path.name}")
    thumbs_without_original = []
    for thumb in media_folder.rglob("*.thumb"):
        original = thumb.with_suffix("")
        if not original.exists():
            thumbs_without_original.append(thumb)
            lines.append(f"只有預覽圖，原始檔缺失\t{datetime.fromtimestamp(thumb.stat().st_mtime):%Y/%m/%d %H:%M:%S}\t{thumb.name}")
    lines.extend(["", f"摘要：已配對 {matched}（其中預覽圖 {previews}），未配對訊息 {len(chat_media) - matched}，未使用快取 {sum(map(len, unmatched_media.values()))}，只有預覽圖 {len(thumbs_without_original)}。"])
    report = output_folder / "媒體配對報告.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


# Shared by the photo and statistics pages.
PAGE_CSS = '''*{box-sizing:border-box}body{font-family:system-ui,"Microsoft JhengHei",sans-serif;margin:0}
.topbar{height:64px;background:#91b2dc;color:#172235;display:flex;align-items:center;gap:10px;padding:8px max(14px,calc((100% - 920px)/2));position:sticky;top:0;z-index:3;border-bottom:1px solid #6f95c4}
.topbar h1{font-size:20px;margin:0;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.topbar a{font-size:14px;color:#1f3554;background:#ffffffaa;border-radius:16px;padding:6px 12px;text-decoration:none;white-space:nowrap}
main{max-width:920px;margin:0 auto;padding:12px 14px 48px}'''
# Colours follow the reference data-viz palette: one series hue, hairline grid, light and dark steps.
STATS_CSS = '''.stats{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--series:#2a78d6;--ring:rgba(11,11,11,.10);--bar:#91b2dc;--chip:#ffffffaa;background:var(--page);color:var(--ink)}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .stats{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--series:#3987e5;--ring:rgba(255,255,255,.10);--bar:#1c2633;--chip:#ffffff1f}}
:root[data-theme="dark"] .stats{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--series:#3987e5;--ring:rgba(255,255,255,.10);--bar:#1c2633;--chip:#ffffff1f}
.stats .topbar{background:var(--bar);color:var(--ink);border-color:var(--grid)}.stats .topbar a{background:var(--chip);color:var(--ink)}
.stats h2{font-size:15px;color:var(--ink-2);font-weight:600;margin:28px 2px 10px}
.hero{text-align:center;padding:26px 0 6px}.hero p{margin:0}.hero .figure{font-size:56px;font-weight:700;line-height:1.15}.hero .who,.hero .period{color:var(--ink-2);font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}
.tile,.chart,.emoji li,.first{background:var(--surface);border:1px solid var(--ring);border-radius:12px}
.tile{padding:12px 14px}.tile .label{font-size:13px;color:var(--ink-2)}.tile .value{font-size:24px;font-weight:600;margin-top:4px}.tile .sub{font-size:12px;color:var(--muted);margin-top:2px}.tile a{color:inherit}
.chart{margin:0 0 12px;padding:14px 16px 12px}.chart figcaption{font-size:14px;font-weight:600}
.plot{position:relative;height:200px;margin:26px 0 0 48px}
.tick{position:absolute;left:0;right:0;border-top:1px solid var(--grid)}.tick.base{border-color:var(--axis)}
.tick span{position:absolute;right:calc(100% + 8px);top:0;transform:translateY(-50%);font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.cols{position:absolute;inset:0;display:flex;gap:2px}.col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;outline:none}
.mark{width:min(24px,72%);min-height:1px;background:var(--series);border-radius:4px 4px 0 0}
.col:hover .mark,.col:focus-visible .mark{filter:brightness(1.15)}.col:focus-visible{box-shadow:inset 0 0 0 2px var(--series);border-radius:4px}
.peak{font-size:11px;font-weight:600;margin-bottom:3px;white-space:nowrap}
.xlabels{display:flex;gap:2px;margin:6px 0 0 48px}.xlabels span{flex:1;text-align:center;font-size:11px;color:var(--muted);white-space:nowrap}
.chart details{margin-top:10px;font-size:13px;color:var(--ink-2)}.chart summary{cursor:pointer}
.chart table{border-collapse:collapse;margin-top:6px}.chart th,.chart td{padding:3px 14px 3px 0;border-bottom:1px solid var(--grid);text-align:left;font-weight:400}.chart td+td{text-align:right;font-variant-numeric:tabular-nums}
#tip{position:absolute;transform:translate(-50%,calc(-100% - 8px));background:var(--surface);border:1px solid var(--ring);box-shadow:0 2px 8px #00000026;border-radius:8px;padding:6px 10px;font-size:12px;pointer-events:none;display:flex;flex-direction:column;align-items:center;white-space:nowrap;z-index:5}
#tip[hidden]{display:none}#tip strong{font-size:14px}#tip span{color:var(--ink-2)}
.emoji{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(124px,1fr));gap:8px}
.emoji li{padding:8px 12px;display:flex;align-items:center;gap:10px}.emoji .e{font-size:26px}.emoji .n{font-size:13px;color:var(--ink-2);white-space:nowrap}
.first{padding:14px 16px}.first .when{font-size:12px;color:var(--muted)}.first .text{font-size:16px;margin-top:6px;white-space:pre-wrap;overflow-wrap:anywhere}'''
# One tooltip for every column: value first, then what it is; same on keyboard focus as on hover.
STATS_JS = '''(() => {
  const tip = document.getElementById("tip");
  const show = column => {
    const value = document.createElement("strong"), label = document.createElement("span");
    value.textContent = column.dataset.value;
    label.textContent = column.dataset.label;
    tip.replaceChildren(value, label);
    // Sit above the bar, or above its direct label when it has one.
    const mark = column.querySelector(".mark").getBoundingClientRect(), top = (column.querySelector(".peak") || column.querySelector(".mark")).getBoundingClientRect().top;
    tip.style.left = `${mark.left + mark.width / 2 + scrollX}px`;
    tip.style.top = `${top + scrollY}px`;
    tip.hidden = false;
  };
  for (const column of document.querySelectorAll(".col")) {
    column.addEventListener("pointerenter", () => show(column));
    column.addEventListener("focus", () => show(column));
    column.addEventListener("pointerleave", () => { tip.hidden = true; });
    column.addEventListener("blur", () => { tip.hidden = true; });
  }
})();'''
EMOJI = re.compile("[☀-➿\U0001F300-\U0001F3FA\U0001F400-\U0001FAFF]")


def chat_statistics(lines):
    per_day, per_month, per_hour, senders, emoji, kinds = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    calls, missed, first, date = [], 0, None, None
    for line in lines:
        if match := DATE_LINE.match(line):
            date = datetime(*map(int, match.groups())).date()
            continue
        if not (match := MESSAGE_LINE.match(line)) or not date:
            continue
        sender, content = match[3], match[4]
        first = first or (date, f"{match[1]}:{match[2]}", sender, content)
        per_day[date] += 1
        per_month[date.year, date.month] += 1
        per_hour[int(match[1])] += 1
        senders[sender] += 1
        emoji.update(EMOJI.findall(content))
        kind = next((kind for kind, label in (("photo", PHOTO), ("audio", VOICE), ("video", VIDEO), ("sticker", "[貼圖]"), ("file", FILE)) if label in content), None)
        if kind:
            kinds[kind] += 1
        if call := re.fullmatch(r"通話時間 (\d+(?::\d{2}){1,2})", content):
            calls.append(sum(int(part) * 60 ** power for power, part in enumerate(reversed(call[1].split(":")))))
        elif content == "未接來電":
            missed += 1
    streak = best = (0, None, None)
    for day in sorted(per_day):
        streak = (streak[0] + 1, streak[1], day) if streak[2] and (day - streak[2]).days == 1 else (1, day, day)
        best = max(best, streak, key=lambda run: run[0])
    return {"days": per_day, "months": per_month, "hours": per_hour, "senders": senders, "emoji": emoji,
            "kinds": kinds, "calls": calls, "missed": missed, "first": first, "streak": best}


def nice_scale(maximum):
    """A round top value with at most five equal steps from zero."""
    step = next(m * 10 ** k for k in range(12) for m in (1, 2, 5) if -(-maximum // (m * 10 ** k)) <= 5)
    top = max(step, -(-maximum // step) * step)
    return top, range(0, top + 1, step)


def column_chart(title, columns, label_every=1):
    """columns: (axis label, full label, count). The peak gets a direct label; every column a tooltip and a table row."""
    top, ticks = nice_scale(max([count for *_, count in columns] + [1]))
    peak = max(range(len(columns)), key=lambda i: columns[i][2], default=-1)
    grid = "".join(f'<div class="tick{" base" if tick == 0 else ""}" style="bottom:{tick / top * 100:.2f}%"><span>{f"{tick / 10000:g} 萬" if tick >= 10000 else f"{tick:,}"}</span></div>' for tick in ticks)
    bars = "".join(
        f'<div class="col" tabindex="0" aria-label="{html.escape(full)}：{count:,} 則" data-label="{html.escape(full)}" data-value="{count:,} 則">'
        f'{f"<b class=peak>{count:,}</b>" if i == peak else ""}<span class="mark" style="height:{count / top * 100:.2f}%"></span></div>'
        for i, (_, full, count) in enumerate(columns))
    labels = "".join(f"<span>{html.escape(short) if i % label_every == 0 else ''}</span>" for i, (short, *_) in enumerate(columns))
    rows = "".join(f"<tr><td>{html.escape(full)}</td><td>{count:,}</td></tr>" for _, full, count in columns)
    return (f'<figure class="chart"><figcaption>{html.escape(title)}</figcaption><div class="plot">{grid}<div class="cols">{bars}</div></div>'
            f'<div class="xlabels">{labels}</div><details><summary>以表格檢視</summary><table><tr><th>時間</th><th>訊息數</th></tr>{rows}</table></details></figure>')


def stats_page(title, stats):
    tile = lambda label, value, sub="": f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div>{f"<div class=sub>{sub}</div>" if sub else ""}</div>'
    day_text = lambda day: f"{day.year}/{day.month}/{day.day}"
    clock = lambda seconds: f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02d}"
    duration = lambda seconds: f"{seconds // 3600} 小時 {seconds % 3600 // 60} 分" if seconds >= 3600 else f"{seconds // 60} 分 {seconds % 60} 秒"
    days, senders, kinds, calls = stats["days"], stats["senders"], stats["kinds"], stats["calls"]
    if not days:
        return f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>聊天回憶</title><style>{PAGE_CSS}{STATS_CSS}</style></head><body class="stats"><header class="topbar"><a href="chat.html">← 聊天</a><h1>聊天回憶</h1></header><main><p>聊天記錄裡沒有可統計的訊息。</p></main></body></html>'
    total, start, end = sum(days.values()), min(days), max(days)
    busiest = max(days, key=days.get)
    length, streak_start, streak_end = stats["streak"]
    together = [
        tile("一起聊了", f"{(end - start).days + 1:,} 天", f"{day_text(start)} 到 {day_text(end)}"),
        tile("有聊天的日子", f"{len(days):,} 天"),
        tile("平均每天", f"{round(total / len(days)):,} 則", "以有聊天的日子計算"),
        tile("最多的一天", f'<a href="chat.html#d{busiest:%Y-%m-%d}">{day_text(busiest)}</a>', f"{days[busiest]:,} 則"),
        tile("最長連續聊天", f"{length:,} 天", f"{day_text(streak_start)} 到 {day_text(streak_end)}"),
    ]
    people = [tile(html.escape(name), f"{count:,} 則", f"{count / total:.1%}") for name, count in senders.most_common(8)]
    media = [tile(label, f"{kinds[kind]:,} {unit}") for kind, label, unit in (("photo", "照片", "張"), ("video", "影片", "個"), ("audio", "語音", "則"), ("sticker", "貼圖", "個"), ("file", "檔案", "個"))]
    media += [tile("通話", f"{len(calls):,} 次", f"共 {duration(sum(calls))}"), tile("最長一通", clock(max(calls, default=0))), tile("未接來電", f"{stats['missed']:,} 次")]
    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((f"{month}月" if start.year == end.year else f"{year}/{month}", f"{year} 年 {month} 月", stats["months"][year, month]))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    hours = [(str(hour), f"{hour}:00–{hour}:59", stats["hours"][hour]) for hour in range(24)]
    emoji = "".join(f'<li><span class="e">{symbol}</span><span class="n">{count:,} 次</span></li>' for symbol, count in stats["emoji"].most_common(10))
    emoji = f'<h2>最常用的表情符號</h2><ol class="emoji">{emoji}</ol>' if emoji else ""
    first_day, first_time, first_sender, first_text = stats["first"]
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>聊天回憶</title><style>{PAGE_CSS}{STATS_CSS}</style></head>
<body class="stats"><header class="topbar"><a href="chat.html">← 聊天</a><h1>聊天回憶</h1><a href="photos.html">相簿</a></header><main>
<section class="hero"><p class="who">{html.escape(title)}</p><p class="figure">{total:,}</p><p class="period">則訊息・{day_text(start)} 到 {day_text(end)}</p></section>
<h2>一起聊天</h2><div class="tiles">{"".join(together)}</div>
<h2>誰傳得多</h2><div class="tiles">{"".join(people)}</div>
<h2>照片、語音與通話</h2><div class="tiles">{"".join(media)}</div>
<h2>什麼時候聊</h2>{column_chart("每月訊息數", months)}{column_chart("一天中的時段（依訊息時間）", hours, label_every=3)}
{emoji}
<h2>第一則訊息</h2><div class="first"><div class="when">{day_text(first_day)} {first_time} · {html.escape(first_sender)}</div><div class="text">{linkify(first_text)}</div></div>
</main><div id="tip" role="tooltip" hidden></div><script>{STATS_JS}</script></body></html>'''


def gallery_page(months):
    """months: (heading, image tags) in chat order."""
    count = sum(len(images) for _, images in months)
    sections = "".join(f'<h2>{html.escape(heading)}<span>{len(images):,} 張</span></h2><div class="grid">{"".join(images)}</div>' for heading, images in months)
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>相簿</title><style>{PAGE_CSS}
body{{background:#e9eff7;color:#172235}}h2{{font-size:15px;margin:22px 2px 8px}}h2 span{{font-weight:400;font-size:13px;color:#405a78;margin-left:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:3px}}.grid img{{width:100%;aspect-ratio:1;object-fit:cover;display:block;background:#c9daee}}
</style></head><body><header class="topbar"><a href="chat.html">← 聊天</a><h1>相簿（{count:,} 張）</h1><a href="stats.html">統計</a></header>
<main>{sections or "<p>沒有照片。</p>"}</main>{PHOTO_VIEWER}</body></html>'''


OUTPUT_NAME = re.compile(r"(?:photo|video)_\d{5}\.\w+|voice_0\d{4}\.\w+")


def pick_media_folder(folder: Path, chat_media, log):
    """Accept a chat's messages folder, the chat folder above it, or the whole chats folder."""
    if any(OUTPUT_NAME.fullmatch(path.name) for path in folder.rglob("*")):
        raise ValueError("選到的是本程式之前輸出的資料夾（檔名像 photo_00001.jpg），不是手機的 LINE 快取。\n請改選從手機複製出來、檔名是一串數字的 messages 資料夾。")
    candidates = sorted(path for path in folder.rglob("messages") if path.is_dir())
    if len(candidates) <= 1:
        return candidates[0] if candidates else folder
    log(f"正在比對 {len(candidates)} 個聊天室資料夾...")
    found, best = max((len(match_media(chat_media, [x for group in index_media(path) for x in group])[0]), path) for path in candidates)
    if not found:
        raise ValueError("這個資料夾裡沒有和聊天記錄對得上的聊天室。請確認聊天文字檔和手機資料夾是同一個聊天室。")
    log(f"已找到對應的聊天室資料夾：{best.parent.name}")
    return best


def own_name(lines):
    """A one-to-one export names the other person on its first line; the remaining sender is the owner."""
    header = re.match(r"\[LINE\] ?與(.+)的聊天(?:記錄)?$", lines[0]) if lines else None
    senders = {match[3] for line in lines if (match := MESSAGE_LINE.match(line))}
    if not header or header[1] not in senders:
        return None
    others = senders - {header[1]}
    return others.pop() if len(others) == 1 else None


def convert_chat(chat_file: Path, media_folder: Path, output_folder: Path, log):
    text = chat_file.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    chat_media = parse_chat_media(text)
    media_folder = pick_media_folder(media_folder, chat_media, log)
    photos, voices, videos = index_media(media_folder)
    matches, unmatched_media, methods = match_media(chat_media, [*photos, *voices, *videos])
    files = match_files(lines, matches, index_files(media_folder))
    for _, folder, _, _ in MEDIA_OUTPUT.values():
        (output_folder / "media" / folder).mkdir(parents=True, exist_ok=True)

    rows = []
    for line_number, line in enumerate(lines, 1):
        if re.match(r"\d{4}/\d{1,2}/\d{1,2}", line):
            rows.append(("date", line))
        elif MESSAGE_LINE.match(line):
            rows.append(("message", line_number, *line.split("\t", 2), []))
        elif rows and rows[-1][0] == "message" and not re.match(r"\d{1,2}:\d{2}\t", line):
            # LINE writes the rest of a multi-line message on the following lines.
            rows[-1][-1].append(line)
        elif line.strip():
            rows.append(("notice", line))

    me = own_name(lines)
    copied, previews, missing = Counter(), Counter(), Counter()
    days = [("", [])]
    day_label = date = ""
    gallery = {}
    for row in rows:
        if row[0] == "date":
            day_label = row[1]
            date = "{:04d}-{:02d}-{:02d}".format(*map(int, re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", day_label).groups()))
            days.append((date, [f'<div class="date-divider"><span>{html.escape(day_label)}</span></div>']))
            continue
        if row[0] == "notice":
            days[-1][1].append(f'<div class="notice">{html.escape(row[1])}</div>')
            continue
        _, line_number, time, sender, content, more = row
        caption = html.escape(f"{sender} • {day_label} {time}")
        anchor = ""
        message_text = "\n".join([content, *more]).rstrip()
        escaped_content = linkify(message_text)
        if CALL.fullmatch(message_text):
            escaped_content = f'<span class="call{" missed" if message_text == "未接來電" else ""}">📞 {escaped_content}</span>'
        if line_number in files:
            suffix, label = file_type(files[line_number])
            copied["file"] += 1
            name = f"file_{copied['file']:05d}{suffix}"
            (output_folder / "media" / "files").mkdir(exist_ok=True)
            shutil.copy2(files[line_number], output_folder / "media" / "files" / name)
            escaped_content = escaped_content.replace(FILE, f'<a class="file" href="media/files/{name}" target="_blank">📎 {label}</a>', 1)
        kind = next((k for k, (label, *_) in MEDIA_OUTPUT.items() if label in content), None)
        if kind:
            media = matches.get(line_number)
            if media:
                label, folder, prefix, tag = MEDIA_OUTPUT[kind]
                copied[kind] += 1
                name = f"{prefix}_{copied[kind]:05d}{media.suffix}"
                shutil.copy2(media.path, output_folder / "media" / folder / name)
                if media.preview:
                    previews[kind] += 1
                    tag = PREVIEW_HTML.format(src=f"media/{folder}/{name}", caption=caption, note="影片檔不在快取中，只剩預覽圖" if kind == "video" else "只剩預覽圖")
                else:
                    tag = tag.format(src=f"media/{folder}/{name}", caption=caption)
                escaped_content = escaped_content.replace(label, tag, 1)
                anchor = f' id="m{line_number}"'
                if kind == "photo":
                    # The album grid uses LINE's small preview when there is one; the viewer opens the full photo.
                    thumb = f"media/{folder}/{name}"
                    if media.thumbnail and not media.preview and (thumb_type := detect_media(media.thumbnail)):
                        thumb = f"media/thumbs/{prefix}_{copied[kind]:05d}{thumb_type[1]}"
                        (output_folder / "media" / "thumbs").mkdir(exist_ok=True)
                        shutil.copy2(media.thumbnail, output_folder / thumb)
                    gallery.setdefault(date[:7], []).append(f'<img src="{thumb}" data-full="media/{folder}/{name}" data-caption="{caption}" data-link="chat.html#m{line_number}" loading="lazy" alt="">')
            else:
                missing[kind] += 1
        side = "right" if sender == me else "left"
        avatar = f'<div class="avatar">{html.escape(sender[:1])}</div>' if side == "left" else ""
        days[-1][1].append(f'<div class="message-row {side}"{anchor}>{avatar}<div class="message-content"><div class="meta"><span>{html.escape(sender)}</span><time>{html.escape(time)}</time></div><div class="bubble">{escaped_content}</div></div></div>')
    # Each day is its own section so the browser can skip laying out days that are off screen.
    body = "".join(days[0][1]) + "".join(f'<section class="day" data-date="{date}" id="d{date}" style="contain-intrinsic-size:auto {len(day) * 80}px">{"".join(day)}</section>' for date, day in days[1:])
    first_date, last_date = (days[1][0], days[-1][0]) if len(days) > 1 else ("", "")
    months = [(f"{int(month[:4])} 年 {int(month[5:])} 月" if month else "其他", images) for month, images in gallery.items()]
    (output_folder / "photos.html").write_text(gallery_page(months), encoding="utf-8")
    header = re.match(r"\[LINE\] ?(.+的聊天)(?:記錄)?$", lines[0]) if lines else None
    (output_folder / "stats.html").write_text(stats_page(header[1] if header else chat_file.stem, chat_statistics(lines)), encoding="utf-8")

    title = html.escape(chat_file.stem)
    display_name = html.escape(re.sub(r"的聊天(?:記錄)?$", "", chat_file.stem))
    page = f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
*{{box-sizing:border-box}}body{{font-family:system-ui,"Microsoft JhengHei",sans-serif;background:#86a9d6;color:#172235;margin:0}}
body:before{{content:"";position:fixed;inset:0;background:radial-gradient(circle at 18% 35%,#ffffff18 0 12%,transparent 30%),radial-gradient(circle at 82% 70%,#ffffff12 0 10%,transparent 28%);pointer-events:none}}
.topbar{{height:76px;background:#91b2dc;display:flex;align-items:center;gap:18px;padding:10px max(16px,calc((100% - 920px)/2));position:sticky;top:0;z-index:3;border-bottom:1px solid #6f95c4}}
.topbar .back{{font-size:38px;font-weight:200;line-height:1}}.topbar h1{{font-size:23px;margin:0;flex:1;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.topbar .tools{{display:flex;gap:8px;align-items:center;white-space:nowrap}}
.tools button,.tools a,.tools input{{font:inherit;font-size:14px;color:#1f3554;background:#ffffffaa;border:0;border-radius:16px;padding:6px 12px;text-decoration:none;cursor:pointer}}
.day{{scroll-margin-top:76px}}.message-row{{scroll-margin-top:96px}}.message-row:target .bubble{{outline:3px solid #f5c542;outline-offset:2px}}
main{{max-width:920px;margin:0 auto;padding:18px 14px 40px;position:relative}}.message-row{{display:flex;align-items:flex-end;gap:8px;margin:11px 0;max-width:86%}}.message-row.left{{margin-right:auto}}.message-row.right{{margin-left:auto;flex-direction:row-reverse}}
.avatar{{width:42px;height:42px;flex:0 0 42px;border-radius:50%;background:#5d7697;color:#fff;display:grid;place-items:center;font-size:18px;box-shadow:0 1px 3px #425e8055}}
.message-content{{display:flex;flex-direction:column;align-items:flex-start;min-width:0;max-width:calc(100% - 50px)}}.right .message-content{{align-items:flex-end}}.meta{{font-size:11px;color:#405a78;line-height:1.35;margin:0 8px 3px}}.right .meta{{text-align:right}}.meta span,.meta time{{display:inline-block;margin-right:8px}}
.bubble{{width:fit-content;max-width:100%;background:#fff;border-radius:4px 18px 18px 18px;padding:10px 13px;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 1px 2px #4f729955;min-width:46px;font-size:16px}}.right .bubble{{background:#9bea81;border-radius:18px 4px 18px 18px}}
.date-divider{{text-align:center;margin:18px 0 12px;color:#3e5879;font-size:12px}}.date-divider span{{background:#d0e0f2aa;padding:5px 12px;border-radius:14px}}.notice{{text-align:center;color:#3e5879;font-size:12px;margin:12px 0}}.day{{content-visibility:auto}}.note{{display:block;margin-top:4px;font-size:12px;color:#405a78}}
.bubble a{{color:#1a5fb4;overflow-wrap:anywhere}}.bubble a.file{{text-decoration:none;font-weight:600}}.call{{white-space:nowrap;color:#2f4a6b}}.call.missed{{color:#c0392b}}
img{{display:block;max-width:min(620px,70vw);max-height:620px;margin-top:5px;border-radius:10px}}audio{{max-width:100%;vertical-align:middle}}video{{display:block;max-width:min(620px,70vw);max-height:620px;margin-top:5px;border-radius:10px}}
@media(max-width:600px){{.topbar{{height:64px;padding:8px 14px}}.topbar h1{{font-size:20px}}main{{padding-left:8px;padding-right:8px}}.message-row{{max-width:96%}}.avatar{{width:34px;height:34px;flex-basis:34px;font-size:15px}}.message-content{{max-width:calc(100% - 42px)}}.meta{{font-size:10px}}img,video{{max-width:78vw}}
.topbar .tools{{gap:5px}}.tools button,.tools a,.tools input{{font-size:13px;padding:5px 8px}}.tools input{{width:118px}}.day{{scroll-margin-top:64px}}}}
</style></head><body><header class="topbar"><h1>{display_name}</h1><nav class="tools"><button type="button" id="search-open">搜尋</button><input type="date" id="jump" title="跳到日期" aria-label="跳到日期" min="{first_date}" max="{last_date}"><a href="photos.html">相簿</a><a href="stats.html">統計</a></nav></header>
<main>{body}</main>{SCROLL_DATE}{SEARCH_TOOLS}{PHOTO_VIEWER}</body></html>'''
    output_file = output_folder / "chat.html"
    output_file.write_text(page, encoding="utf-8")
    report = write_match_report(output_folder, chat_media, matches, unmatched_media, methods, media_folder)
    log(f"完成：照片 {copied['photo']} 張，影片 {copied['video']} 個，語音 {copied['audio']} 個")
    if previews:
        log(f"其中只剩預覽圖：照片 {previews['photo']} 張，影片 {previews['video']} 個")
    if copied["file"]:
        log(f"檔案 {copied['file']} 個")
    if missing:
        log(f"找不到媒體：照片 {missing['photo']} 張，影片 {missing['video']} 個，語音 {missing['audio']} 個")
    log(f"已建立配對報告：{report.name}")
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
        value = filedialog.askdirectory(title="請選擇聊天室裡的 messages 資料夾（也可以選整個 chats 資料夾）")
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
