#!/usr/bin/env python3
"""Bulk media downloader -- dán 1 hoặc nhiều link, quét ảnh/video/audio, chọn
và tải hàng loạt về 1 file ZIP. Có xử lý riêng cho TikTok/Douyin để tải bản KHÔNG
watermark (lấy thẳng link gốc từ API công khai, không phải xử lý ảnh xoá logo).
Tuỳ chọn tải cả playlist/kênh/trang cá nhân khi dán 1 link (giới hạn
PLAYLIST_CAP video/lần để tránh quá tải).

Run:
    pip install -r requirements.txt
    python3 app.py
    -> mo http://localhost:5000
"""
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, send_file, render_template

app = Flask(__name__)

# Hàng đợi tải chạy NỀN (threading.Thread) để giao diện có thể: (1) hiện log
# tiến trình theo thời gian thực (poll /api/download/status/<job_id>), (2) có
# nút Huỷ giữa chừng, (3) có nút Thử lại khi lỗi -- vì lớp Douyin qua trình
# duyệt thật có thể mất tới ~2 phút (3 lần thử), request đồng bộ cũ khiến
# giao diện trông như treo không biết đang chạy hay đã chết.
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


class CancelledError(Exception):
    pass


def new_job() -> str:
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "running", "logs": [], "zip_path": None, "error": None, "cancel": False}
    return job_id


def job_log(job_id: str, msg: str):
    print(msg, flush=True)
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["logs"].append(msg)


def job_is_cancelled(job_id: str) -> bool:
    with JOBS_LOCK:
        return JOBS.get(job_id, {}).get("cancel", False)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
REQUEST_TIMEOUT = 30
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif")
VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")
TIKTOK_HOSTS = ("tiktok.com", "douyin.com")  # cùng công ty (ByteDance) -- tikwm.com xác nhận hỗ trợ TikTok, Douyin thì chưa chắc (API không công bố rõ), nên có thêm lớp dự phòng douyin_via_browser() bên dưới

MAX_URLS_PER_SCAN = 20
MAX_ITEMS_PER_DOWNLOAD = 100
PLAYLIST_CAP = 30  # trần an toàn khi dán link playlist/kênh/trang cá nhân -- tránh treo máy/quá tải site đích

# Nếu đặt 1 file cookies.txt (định dạng Netscape, xuất bằng extension trình
# duyệt như "Get cookies.txt LOCALLY") cùng thư mục với app.py, yt-dlp sẽ
# dùng để tải các trang cần đăng nhập / chống bot nghiêm (Douyin, Instagram
# riêng tư...). KHÔNG commit file này lên git -- đã thêm vào .gitignore vì
# nó chứa phiên đăng nhập thật của bạn, lộ ra là người khác đăng nhập được
# tài khoản của bạn.
COOKIES_FILE = Path(__file__).resolve().parent / "cookies.txt"

# Nếu KHÔNG có cookies.txt tĩnh, thử tự lấy cookie SỐNG từ trình duyệt (yt-dlp
# cookiesfrombrowser) cho các site chặn bot nghiêm (Douyin, Instagram). Theo
# kinh nghiệm thực tế đã kiểm chứng (dự án DichPhimPro, đã tải thành công
# Douyin/Instagram thật): FIREFOX đáng tin cậy nhất vì Chrome/Edge khoá file
# cookie khi trình duyệt đang mở ("Could not copy Chrome cookie database")
# và có thể lỗi giải mã DPAPI trên một số máy Windows. Đổi tên ở đây nếu
# muốn ưu tiên trình duyệt khác: "chrome" / "edge" / "brave".
COOKIES_BROWSER = "firefox"
# Domain thật sự cần cookie -- chỉ bật cookiesfrombrowser (chậm hơn, phải đọc
# DB trình duyệt) cho các site này, không áp dụng tràn lan cho mọi link.
COOKIE_REQUIRED_HOSTS = ("douyin.com", "instagram.com")


def needs_browser_cookies(url: str) -> bool:
    return any(h in urlparse(url).netloc.lower() for h in COOKIE_REQUIRED_HOSTS)


def ytdlp_base_opts(url: str = "") -> dict:
    opts = {"quiet": True, "noplaylist": True}
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)  # cookies.txt tĩnh luôn được ưu tiên nếu có
    elif COOKIES_BROWSER and needs_browser_cookies(url):
        opts["cookiesfrombrowser"] = (COOKIES_BROWSER,)
    return opts


def normalize_douyin_url(url: str) -> str:
    """douyin.com/<bất kỳ>?modal_id=<id> -> douyin.com/video/<id>. Link chia
    sẻ/link trong trang tìm kiếm Douyin thường ở dạng modal overlay (query
    param modal_id), nhưng extractor của yt-dlp chỉ nhận dạng link chuẩn
    /video/<id> -- không đổi thì bị báo "Unsupported URL". Đã kiểm chứng
    (dự án DichPhimPro, đang chạy thật)."""
    parsed = urlparse(url)
    if "douyin.com" not in parsed.netloc.lower() or "/video/" in parsed.path:
        return url
    modal_id = parse_qs(parsed.query).get("modal_id", [None])[0]
    return f"https://www.douyin.com/video/{modal_id}" if modal_id else url


class ScanFailed(Exception):
    pass


def is_media_url(url: str, exts: tuple[str, ...]) -> bool:
    return urlparse(url).path.lower().endswith(exts)


def is_tiktok_url(url: str) -> bool:
    return any(h in urlparse(url).netloc.lower() for h in TIKTOK_HOSTS)


def tiktok_profile_username(url: str) -> str | None:
    """Nếu url là trang cá nhân TikTok (vd tiktok.com/@ten, không phải 1
    video cụ thể), trả về username. Dùng để tải hàng loạt video của 1 kênh.
    """
    if "tiktok.com" not in urlparse(url).netloc.lower():
        return None
    m = re.match(r"^/@([\w.\-]+)/?$", urlparse(url).path)
    return m.group(1) if m else None


def fetch_og_image(url: str, timeout: float = 8.0) -> str | None:
    """Lấy nhanh ảnh thumbnail từ thẻ <meta property="og:image"> của trang --
    hầu hết site (kể cả SPA nặng JS như Douyin/TikTok) vẫn render thẻ này ở
    HTML gốc để mạng xã hội hiện preview khi chia sẻ link, nên lấy được mà
    KHÔNG cần mở trình duyệt thật (nhanh, rẻ). Best-effort, graceful-fail."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        return tag.get("content") if tag else None
    except Exception:
        return None


def tiktok_profile_videos(username: str, cap: int) -> list[dict]:
    """Gọi API tikwm.com/api/user/posts -- lấy danh sách video KHÔNG
    watermark của 1 trang cá nhân TikTok. Best-effort: tikwm có thể đổi
    cấu trúc response, nên luôn trả [] thay vì crash nếu không khớp.
    """
    try:
        resp = requests.get(
            "https://www.tikwm.com/api/user/posts",
            params={"unique_id": f"@{username}", "count": min(cap, 30)},
            headers=HEADERS, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0:
            return []
        videos = (payload.get("data") or {}).get("videos") or []
        return [
            {"video": v["play"], "title": v.get("title") or "tiktok"}
            for v in videos[:cap] if v.get("play")
        ]
    except Exception:
        return []


def best_srcset_url(srcset: str) -> str | None:
    """srcset="a.jpg 480w, b.jpg 960w" -> pick the largest (last) candidate."""
    candidates = [c.strip() for c in srcset.split(",") if c.strip()]
    if not candidates:
        return None
    return candidates[-1].split()[0]


def tiktok_no_watermark(url: str) -> dict | None:
    """Gọi API công khai tikwm.com -- trả thẳng link video TikTok KHÔNG
    watermark (và bản HD, nhạc nền nếu có), tải được bằng GET bình thường,
    không cần yt-dlp. Đây là kỹ thuật chuẩn các tool "tải TikTok không logo"
    đều dùng: TikTok phục vụ sẵn 1 bản gốc không watermark qua API nội bộ,
    watermark chỉ được dán khi tải qua nút "Lưu video" trong app chính thức.
    """
    try:
        resp = requests.get(
            "https://www.tikwm.com/api/", params={"url": url},
            headers=HEADERS, timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 0 or not payload.get("data"):
            return None
        d = payload["data"]
        if not d.get("play"):
            return None
        return {
            "title": d.get("title") or "tiktok",
            "video": d["play"],
            "video_hd": d.get("hdplay") if d.get("hdplay") and d.get("hdplay") != d["play"] else None,
            "music": d.get("music"),
            "cover": d.get("cover"),
        }
    except Exception:
        return None


def _douyin_probe_via_browser(url: str, log=print) -> dict:
    """Mở trang Douyin bằng trình duyệt thật (Playwright + Chromium headless)
    để JS của trang tự giải bài toán chống bot như người dùng thật, rồi bắt
    link CDN video/audio. Douyin phát video+audio thành 2 luồng TÁCH RIÊNG
    (không như TikTok gộp chung) -- phải bắt cả 2 qua network response rồi
    ghép bằng ffmpeg sau, không chỉ đọc src của thẻ <video> (thường chỉ có
    hình, không tiếng). Raise lỗi (không nuốt exception) để hàm gọi retry
    được -- xử lý graceful-fail ở tầng gọi, không phải ở đây.

    Root cause (đã xác nhận bằng cách đọc mã nguồn yt-dlp extractor/tiktok.py
    class DouyinIE): Douyin cần cookie s_v_web_id do JS chống bot của trang
    tạo ra tại thời điểm truy cập -- cookie tĩnh không đủ, cookiesfrombrowser
    cũng có thể không đủ nếu Douyin đòi thêm bước giải mã JS runtime. Trình
    duyệt thật là cách duy nhất chắc chắn "giải" được bài toán đó.
    """
    from playwright.sync_api import sync_playwright

    video_url = None
    audio_url = None

    def on_response(response):
        nonlocal video_url, audio_url
        try:
            ctype = response.headers.get("content-type", "")
        except Exception:  # noqa: BLE001 -- response có thể đã đóng, bỏ qua
            return
        if "video" in ctype and not video_url:
            video_url = response.url
        elif "audio" in ctype and not audio_url:
            audio_url = response.url

    log(f"[douyin] Đang mở trình duyệt thật -> {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
                locale="vi-VN",
            )
            # Trang Douyin hiện đại luôn có request nền chạy liên tục (quảng
            # cáo, đo lường...) nên KHÔNG BAO GIỜ đạt "networkidle" -- dùng
            # networkidle làm điều kiện chờ sẽ timeout 100% mọi lần, bất kể
            # mạng nhanh/chậm. Chỉ chờ DOM dựng xong, phần video do JS chèn
            # vào sau được chờ riêng bằng wait_for_selector bên dưới.
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page.on("response", on_response)
            log("[douyin] Đang mở trang (tối đa 25s)...")
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            log("[douyin] Trang đã mở, đang tìm thẻ <video> (tối đa 20s)...")
            try:
                page.wait_for_selector("video", timeout=20000)
            except Exception:
                raise RuntimeError(
                    f"Không tìm thấy thẻ <video> sau khi tải trang "
                    f"(tiêu đề trang lúc đó: \"{page.title()}\", "
                    f"url thực tế: {page.url}) -- có thể Douyin chặn bot "
                    f"hoặc chuyển hướng sang trang xác minh."
                )
            page.wait_for_timeout(1500)  # chờ thêm chút để network response video/audio kịp bắt
            if not video_url:
                video_url = page.eval_on_selector("video", "el => el.currentSrc || el.src")
            title = page.title() or "douyin"
        finally:
            browser.close()

    if not video_url:
        raise RuntimeError("Tìm thấy thẻ <video> nhưng không lấy được link -- có thể Douyin yêu cầu đăng nhập hoặc đổi cơ chế phát video")
    log(f"[douyin] Lấy link thành công: video={'co' if video_url else 'khong'}, audio={'co' if audio_url else 'khong'}")
    return {"video": video_url, "audio": audio_url, "title": title}


def _with_retries(fn, attempts: int = 3, base_delay: float = 3.0, log=print, should_cancel=None):
    """Thử lại tối đa `attempts` lần, mỗi lần chờ lâu hơn (3s, 6s, 9s...) --
    Douyin có thể tạm chặn/chậm khi vừa quét, theo kinh nghiệm thực tế đã
    kiểm chứng (dự án DichPhimPro). `should_cancel`: callable kiểm tra giữa
    các lần thử/khi đang chờ -- raise CancelledError ngay nếu người dùng
    bấm Huỷ, không đợi hết thời gian chờ."""
    last_exc = None
    for i in range(attempts):
        if should_cancel and should_cancel():
            raise CancelledError("Đã huỷ theo yêu cầu")
        log(f"[douyin] Lần thử {i + 1}/{attempts}...")
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            log(f"[douyin] Lần {i + 1} lỗi: {e}")
            if i < attempts - 1:
                wait_s = base_delay * (i + 1)
                log(f"[douyin] Chờ {wait_s:.0f}s rồi thử lại...")
                slept = 0.0
                while slept < wait_s:
                    if should_cancel and should_cancel():
                        raise CancelledError("Đã huỷ theo yêu cầu")
                    step = min(0.5, wait_s - slept)
                    time.sleep(step)
                    slept += step
    raise last_exc


def scan_page(page_url: str, allow_playlist: bool = False) -> dict:
    """Trả về {images, videos, audios, ytdlp_videos, douyin_items, source, title}.
    - images/videos/audios: link tải trực tiếp (GET thẳng là ra file).
    - ytdlp_videos: list [{page_url, title}, ...] -- 1 phần tử cho 1 video
      đơn, NHIỀU phần tử nếu link là playlist/kênh và allow_playlist=True
      (yt-dlp tự liệt kê, giới hạn PLAYLIST_CAP video để tránh quá tải).
    - douyin_items: list [{page_url, title}, ...] -- Douyin cần mở trình
      duyệt thật để lấy video, CHỈ làm việc đó lúc TẢI thật (không phải lúc
      quét) để tránh mở trình duyệt 2 lần (quét xong rồi tải lại mở lần nữa).
    - source: "tiktok_no_watermark" | "html" | "ytdlp" -- để giao diện báo
      rõ đã dùng cách nào (đặc biệt để xác nhận đã tải được bản không logo).
    """
    page_url = normalize_douyin_url(page_url)
    found: dict[str, str] = {}  # url -> "image" | "video" | "audio"

    def add(raw_url: str | None, kind: str):
        if not raw_url or raw_url.startswith("data:"):
            return
        full = urljoin(page_url, raw_url)
        found.setdefault(full, kind)

    # TikTok/Douyin: ưu tiên API không-watermark trước, đáng tin hơn và
    # nhanh hơn parse HTML (cả 2 là SPA nặng JS, parse HTML thô gần như vô
    # ích). Douyin: extractor yt-dlp hiện hay gãy do site đổi cơ chế chống
    # bot liên tục -- tikwm thường vẫn ổn hơn vì không phụ thuộc yt-dlp.
    if is_tiktok_url(page_url):
        if allow_playlist:
            username = tiktok_profile_username(page_url)
            if username:
                profile_videos = tiktok_profile_videos(username, PLAYLIST_CAP)
                if profile_videos:
                    for v in profile_videos:
                        add(v["video"], "video")
                    return {
                        "images": [], "videos": sorted(u for u, k in found.items() if k == "video"),
                        "audios": [], "ytdlp_videos": [], "douyin_items": [],
                        "source": "tiktok_no_watermark",
                        "title": f"@{username} ({len(profile_videos)} video)",
                    }
        tk = tiktok_no_watermark(page_url)
        if tk:
            add(tk["video"], "video")
            if tk["video_hd"]:
                add(tk["video_hd"], "video")
            if tk["music"]:
                add(tk["music"], "audio")
            if tk["cover"]:
                add(tk["cover"], "image")
            return {
                "images": sorted(u for u, k in found.items() if k == "image"),
                "videos": sorted(u for u, k in found.items() if k == "video"),
                "audios": sorted(u for u, k in found.items() if k == "audio"),
                "ytdlp_videos": [], "douyin_items": [],
                "source": "tiktok_no_watermark",
                "title": tk["title"],
            }
        # tikwm lỗi/hết hạn: nếu là Douyin, để lại cho lớp trình duyệt thật
        # xử lý LÚC TẢI (không mở trình duyệt ở bước quét -- chậm và không
        # cần thiết nếu cuối cùng người dùng không chọn tải item này).
        if "douyin.com" in urlparse(page_url).netloc.lower():
            thumb = fetch_og_image(page_url)  # best-effort, không cần trình duyệt
            return {
                "images": [], "videos": [], "audios": [],
                "ytdlp_videos": [],
                "douyin_items": [{"page_url": page_url, "title": "Douyin (qua trình duyệt thật)", "thumbnail": thumb}],
                "source": "douyin_browser",
                "title": None,
            }
        # Không phải Douyin (TikTok edge-case khác) -> rơi xuống nhánh
        # thường bên dưới (parse HTML + yt-dlp).

    # Bước 1: thử tải HTML thô. Nhiều trang (Facebook, Instagram...) chặn
    # kiểu request này hoặc cần JavaScript mới render ra nội dung -- KHÔNG
    # bỏ cuộc ở đây, ghi lại lỗi rồi vẫn thử yt-dlp ở bước 2.
    fetch_error: str | None = None
    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for img in soup.find_all("img"):
            add(img.get("src"), "image")
            add(img.get("data-src"), "image")
            srcset = img.get("srcset")
            if srcset:
                add(best_srcset_url(srcset), "image")

        for video in soup.find_all("video"):
            add(video.get("src"), "video")
            add(video.get("poster"), "image")
            for source in video.find_all("source"):
                add(source.get("src"), "video")

        for audio in soup.find_all("audio"):
            add(audio.get("src"), "audio")
            for source in audio.find_all("source"):
                add(source.get("src"), "audio")

        for source in soup.find_all("source"):
            add(source.get("src"), "video")

        for a in soup.find_all("a"):
            href = a.get("href")
            if not href:
                continue
            full = urljoin(page_url, href)
            if is_media_url(full, IMAGE_EXTS):
                add(full, "image")
            elif is_media_url(full, VIDEO_EXTS):
                add(full, "video")
            elif is_media_url(full, AUDIO_EXTS):
                add(full, "audio")
    except requests.RequestException as e:
        fetch_error = str(e)

    images = sorted(u for u, k in found.items() if k == "image")
    videos = sorted(u for u, k in found.items() if k == "video")
    audios = sorted(u for u, k in found.items() if k == "audio")

    # Bước 2: luôn thử yt-dlp (chạy dù bước 1 lỗi hay không) -- hỗ trợ hàng
    # nghìn site video (YouTube, Twitter/X, Vimeo, Facebook công khai...).
    # allow_playlist=True: nếu link là playlist/kênh, liệt kê tối đa
    # PLAYLIST_CAP video thay vì chỉ lấy 1 video đầu.
    ytdlp_videos: list[dict] = []
    ytdlp_error = None
    try:
        import yt_dlp

        opts = {**ytdlp_base_opts(page_url), "skip_download": True, "noplaylist": not allow_playlist}
        if allow_playlist:
            opts["playlistend"] = PLAYLIST_CAP
            opts["extract_flat"] = "in_playlist"  # chỉ liệt kê, không phân tích từng video -- nhanh hơn nhiều
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(page_url, download=False)
            entries = info.get("entries") if info else None
            if entries:
                for entry in list(entries)[:PLAYLIST_CAP]:
                    if not entry:
                        continue
                    vid_url = entry.get("webpage_url") or entry.get("url")
                    if not vid_url:
                        continue
                    title = re.sub(r"[^\w\-. ]", "_", entry.get("title") or "video")[:80]
                    thumb = entry.get("thumbnail") or (entry.get("thumbnails") or [{}])[-1].get("url")
                    ytdlp_videos.append({"page_url": vid_url, "title": title, "thumbnail": thumb})
            elif info and (info.get("url") or info.get("webpage_url") or info.get("formats")):
                title = re.sub(r"[^\w\-. ]", "_", info.get("title") or "video")[:80]
                thumb = info.get("thumbnail") or (info.get("thumbnails") or [{}])[-1].get("url")
                ytdlp_videos.append({"page_url": page_url, "title": title, "thumbnail": thumb})
    except Exception as e:  # noqa: BLE001
        ytdlp_error = str(e)

    if not images and not videos and not audios and not ytdlp_videos:
        reason = fetch_error or ytdlp_error or "trang không có ảnh/video nào đọc được"
        raise ScanFailed(reason)

    return {
        "images": images, "videos": videos, "audios": audios,
        "ytdlp_videos": ytdlp_videos, "douyin_items": [],
        "source": "ytdlp" if ytdlp_videos else "html",
        "title": f"{len(ytdlp_videos)} video" if len(ytdlp_videos) > 1 else None,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan_batch", methods=["POST"])
def api_scan_batch():
    """Quét 1 hoặc nhiều link cùng lúc (mỗi dòng 1 link ở giao diện)."""
    body = request.json or {}
    raw_urls = body.get("urls", [])
    allow_playlist = bool(body.get("allow_playlist"))
    urls = [u.strip() for u in raw_urls if u and u.strip()][:MAX_URLS_PER_SCAN]
    if not urls:
        return jsonify({"error": "Chưa nhập link nào."}), 400

    results = []
    for u in urls:
        if not u.startswith(("http://", "https://")):
            results.append({"url": u, "error": "URL không hợp lệ -- phải bắt đầu bằng http:// hoặc https://"})
            continue
        try:
            r = scan_page(u, allow_playlist=allow_playlist)
            r["url"] = u
            results.append(r)
        except ScanFailed as e:
            results.append({"url": u, "error": str(e)})
    return jsonify({"results": results})


@app.route("/api/download/start", methods=["POST"])
def api_download_start():
    """Bắt đầu 1 job tải NỀN, trả về job_id ngay (không đợi tải xong) --
    giao diện poll /api/download/status/<job_id> để xem log + trạng thái."""
    data = request.json or {}
    urls: list[str] = data.get("urls", [])
    ytdlp_items: list[dict] = data.get("ytdlp_items", [])  # [{page_url, title, mode}]
    douyin_items: list[dict] = data.get("douyin_items", [])  # [{page_url, title}]
    total = len(urls) + len(ytdlp_items) + len(douyin_items)
    if total == 0:
        return jsonify({"error": "Chưa chọn file nào để tải."}), 400
    if total > MAX_ITEMS_PER_DOWNLOAD:
        return jsonify({"error": f"Tối đa {MAX_ITEMS_PER_DOWNLOAD} file mỗi lần tải -- chọn ít lại."}), 400

    job_id = new_job()
    thread = threading.Thread(target=_run_download_job, args=(job_id, urls, ytdlp_items, douyin_items), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/download/status/<job_id>")
def api_download_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Không tìm thấy job (có thể đã tải xong và dọn dẹp)."}), 404
        return jsonify({"status": job["status"], "logs": job["logs"], "error": job["error"]})


@app.route("/api/download/cancel/<job_id>", methods=["POST"])
def api_download_cancel(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Không tìm thấy job."}), 404
        job["cancel"] = True
    return jsonify({"ok": True})


@app.route("/api/download/result/<job_id>")
def api_download_result(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job or job["status"] != "done" or not job["zip_path"]:
            return jsonify({"error": "Job chưa xong hoặc không tồn tại."}), 404
        zip_path = job["zip_path"]

    resp = send_file(zip_path, as_attachment=True, download_name="media.zip")

    @resp.call_on_close
    def _cleanup():
        Path(zip_path).unlink(missing_ok=True)
        with JOBS_LOCK:
            JOBS.pop(job_id, None)

    return resp


def _run_download_job(job_id: str, urls: list[str], ytdlp_items: list[dict], douyin_items: list[dict]):
    """Chạy trong thread nền. Ghi log + trạng thái vào JOBS[job_id] để
    /api/download/status poll được, kiểm tra cancel giữa mỗi item để nút
    Huỷ có tác dụng ngay (không cần đợi hết hàng đợi)."""
    def log(msg: str):
        job_log(job_id, msg)

    def cancelled() -> bool:
        return job_is_cancelled(job_id)

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"bmd_{job_id}_"))
    total = len(urls) + len(ytdlp_items) + len(douyin_items)
    done = 0
    was_cancelled = False

    try:
        for i, url in enumerate(urls):
            if cancelled():
                was_cancelled = True
                break
            done += 1
            log(f"[{done}/{total}] Tải trực tiếp: {url[:80]}")
            try:
                _download_one(url, tmp_dir, i)
                log("  -> Xong.")
            except Exception as e:  # noqa: BLE001 - 1 file lỗi không chặn các file khác
                log(f"  -> Lỗi: {e}")
                (tmp_dir / f"LOI_{i:03d}.txt").write_text(f"{url}\n{e}", encoding="utf-8")

        if not was_cancelled:
            for j, item in enumerate(ytdlp_items):
                if cancelled():
                    was_cancelled = True
                    break
                done += 1
                log(f"[{done}/{total}] Tải video (yt-dlp): {item['page_url'][:80]}")
                try:
                    _download_with_ytdlp(item["page_url"], tmp_dir, audio_only=(item.get("mode") == "audio"))
                    log("  -> Xong.")
                except Exception as e:  # noqa: BLE001
                    log(f"  -> Lỗi: {e}")
                    (tmp_dir / f"LOI_video_{j:03d}.txt").write_text(f"{item['page_url']}\n{e}", encoding="utf-8")

        if not was_cancelled:
            for k, item in enumerate(douyin_items):
                if cancelled():
                    was_cancelled = True
                    break
                done += 1
                log(f"[{done}/{total}] Tải Douyin qua trình duyệt thật: {item['page_url'][:80]}")
                try:
                    _with_retries(
                        lambda u=item["page_url"]: _download_douyin_via_browser(u, tmp_dir, log=log),
                        log=log, should_cancel=cancelled,
                    )
                    log("  -> Xong.")
                except CancelledError:
                    was_cancelled = True
                    break
                except Exception as e:  # noqa: BLE001
                    log(f"  -> Lỗi: {e}")
                    (tmp_dir / f"LOI_douyin_{k:03d}.txt").write_text(f"{item['page_url']}\n{e}", encoding="utf-8")

        if was_cancelled:
            log("Đã huỷ theo yêu cầu.")
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["status"] = "cancelled"
            return

        if not any(tmp_dir.iterdir()):
            log("Tải thất bại hết, không có file nào.")
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["status"] = "error"
                    JOBS[job_id]["error"] = "Tải thất bại hết, không có file nào."
            return

        zip_base = tmp_dir.parent / f"bmd_{job_id}"
        zip_path = shutil.make_archive(str(zip_base), "zip", root_dir=tmp_dir)
        log("Hoàn tất! Bấm \"Tải ZIP\" để lưu file về máy.")
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["zip_path"] = zip_path
    except Exception as e:  # noqa: BLE001 -- lỗi không lường trước, không để thread chết âm thầm
        log(f"Lỗi không mong đợi: {e}")
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["status"] = "error"
                JOBS[job_id]["error"] = str(e)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _stream_download(url: str, out_path: Path):
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


def _download_one(url: str, tmp_dir: Path, index: int):
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
    resp.raise_for_status()
    name = Path(urlparse(url).path).name or f"file_{index}"
    if "." not in name:
        # Link kiểu tikwm/CDN hay không có đuôi file trong path (query string
        # mới chứa thông tin) -- đoán đuôi từ Content-Type trả về.
        ctype = resp.headers.get("Content-Type", "")
        ext = {"video/mp4": ".mp4", "audio/mpeg": ".mp3", "image/jpeg": ".jpg", "image/png": ".png"}.get(ctype.split(";")[0].strip(), ".bin")
        name += ext
    out_path = tmp_dir / f"{index:03d}_{name}"
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


def _download_with_ytdlp(page_url: str, tmp_dir: Path, audio_only: bool = False):
    import yt_dlp

    opts = {**ytdlp_base_opts(page_url), "outtmpl": str(tmp_dir / "%(title).80s.%(ext)s")}
    if audio_only:
        # Cần có ffmpeg trong PATH của máy -- nếu thiếu, yt-dlp báo lỗi rõ
        # ràng, được ghi vào file LOI_*.txt trong ZIP kết quả thay vì crash.
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = "best"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([page_url])


def _download_douyin_via_browser(page_url: str, tmp_dir: Path, log=print):
    """Tải Douyin qua trình duyệt thật: mở trang, bắt link CDN video + audio
    (2 luồng tách riêng), tải từng cái rồi ghép bằng ffmpeg. Gọi hàm này qua
    `_with_retries()` ở nơi gọi -- không tự retry bên trong, để tầng gọi
    quyết định số lần thử."""
    result = _douyin_probe_via_browser(page_url, log=log)
    title = re.sub(r"[^\w\-. ]", "_", result["title"])[:80] or "douyin"

    log(f"[douyin] Đang tải video: {result['video'][:80]}...")
    video_path = tmp_dir / f"{title}_video.mp4"
    _stream_download(result["video"], video_path)

    if result["audio"] and result["audio"] != result["video"]:
        log(f"[douyin] Đang tải audio riêng: {result['audio'][:80]}...")
        audio_path = tmp_dir / f"{title}_audio.m4a"
        _stream_download(result["audio"], audio_path)
        log("[douyin] Đang ghép video+audio bằng ffmpeg...")
        out_path = tmp_dir / f"{title}.mp4"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path), "-c", "copy", str(out_path)],
                check=True, capture_output=True,
            )
        except FileNotFoundError:
            raise RuntimeError("Thiếu ffmpeg -- cài ffmpeg và thêm vào PATH (xem README) rồi thử lại.")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg lỗi khi ghép: {e.stderr.decode(errors='replace')[-500:]}")
        video_path.unlink(missing_ok=True)
        audio_path.unlink(missing_ok=True)
    else:
        video_path.rename(tmp_dir / f"{title}.mp4")
    log(f"[douyin] Xong: {title}.mp4")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
