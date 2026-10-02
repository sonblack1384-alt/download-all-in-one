#!/usr/bin/env python3
"""Bulk media downloader -- dán 1 hoặc nhiều link, quét ảnh/video/audio, chọn
và tải hàng loạt về 1 file ZIP. Có xử lý riêng cho TikTok/Douyin để tải bản KHÔNG
watermark (lấy thẳng link gốc từ API công khai, không phải xử lý ảnh xoá logo).

Run:
    pip install -r requirements.txt
    python3 app.py
    -> mo http://localhost:5000
"""
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, send_file, render_template

app = Flask(__name__)

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
TIKTOK_HOSTS = ("tiktok.com", "douyin.com")  # cùng công ty (ByteDance), tikwm.com hỗ trợ cả 2

MAX_URLS_PER_SCAN = 20
MAX_ITEMS_PER_DOWNLOAD = 60


class ScanFailed(Exception):
    pass


def is_media_url(url: str, exts: tuple[str, ...]) -> bool:
    return urlparse(url).path.lower().endswith(exts)


def is_tiktok_url(url: str) -> bool:
    return any(h in urlparse(url).netloc.lower() for h in TIKTOK_HOSTS)


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


def scan_page(page_url: str) -> dict:
    """Trả về {images, videos, audios, ytdlp_video, source, title}.
    - images/videos/audios: link tải trực tiếp (GET thẳng là ra file).
    - ytdlp_video: {page_url, title} khi cần yt-dlp xử lý riêng lúc tải
      (một số site không cho hotlink trực tiếp CDN).
    - source: "tiktok_no_watermark" | "html" | "ytdlp" -- để giao diện báo
      rõ đã dùng cách nào (đặc biệt để xác nhận đã tải được bản không logo).
    """
    found: dict[str, str] = {}  # url -> "image" | "video" | "audio"

    def add(raw_url: str | None, kind: str):
        if not raw_url or raw_url.startswith("data:"):
            return
        full = urljoin(page_url, raw_url)
        found.setdefault(full, kind)

    # TikTok/Douyin: ưu tiên API không-watermark trước, đáng tin hơn và
    # nhanh hơn parse HTML (cả 2 là SPA nặng JS, parse HTML thô gần như vô
    # ích). Douyin chưa test được thật (mạng môi trường dev chặn douyin.com)
    # -- nếu tikwm không hỗ trợ Douyin, code tự rơi về nhánh thường bên dưới.
    if is_tiktok_url(page_url):
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
                "ytdlp_video": None,
                "source": "tiktok_no_watermark",
                "title": tk["title"],
            }
        # tikwm lỗi/hết hạn -> rơi xuống nhánh thường bên dưới (vẫn thử
        # yt-dlp, nhưng không đảm bảo chắc chắn không watermark nữa).

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
    ytdlp_video = None
    ytdlp_error = None
    try:
        import yt_dlp

        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(page_url, download=False)
            if info and info.get("url"):
                title = re.sub(r"[^\w\-. ]", "_", info.get("title") or "video")[:80]
                ytdlp_video = {"page_url": page_url, "title": title}
    except Exception as e:  # noqa: BLE001
        ytdlp_error = str(e)

    if not images and not videos and not audios and not ytdlp_video:
        reason = fetch_error or ytdlp_error or "trang không có ảnh/video nào đọc được"
        raise ScanFailed(reason)

    return {
        "images": images, "videos": videos, "audios": audios,
        "ytdlp_video": ytdlp_video, "source": "ytdlp" if ytdlp_video else "html",
        "title": None,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan_batch", methods=["POST"])
def api_scan_batch():
    """Quét 1 hoặc nhiều link cùng lúc (mỗi dòng 1 link ở giao diện)."""
    raw_urls = (request.json or {}).get("urls", [])
    urls = [u.strip() for u in raw_urls if u and u.strip()][:MAX_URLS_PER_SCAN]
    if not urls:
        return jsonify({"error": "Chưa nhập link nào."}), 400

    results = []
    for u in urls:
        if not u.startswith(("http://", "https://")):
            results.append({"url": u, "error": "URL không hợp lệ -- phải bắt đầu bằng http:// hoặc https://"})
            continue
        try:
            r = scan_page(u)
            r["url"] = u
            results.append(r)
        except ScanFailed as e:
            results.append({"url": u, "error": str(e)})
    return jsonify({"results": results})


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.json or {}
    urls: list[str] = data.get("urls", [])
    ytdlp_items: list[dict] = data.get("ytdlp_items", [])  # [{page_url, title, mode}]
    total = len(urls) + len(ytdlp_items)
    if total == 0:
        return jsonify({"error": "Chưa chọn file nào để tải."}), 400
    if total > MAX_ITEMS_PER_DOWNLOAD:
        return jsonify({"error": f"Tối đa {MAX_ITEMS_PER_DOWNLOAD} file mỗi lần tải -- chọn ít lại."}), 400

    job_id = uuid.uuid4().hex
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"bmd_{job_id}_"))

    try:
        for i, url in enumerate(urls):
            try:
                _download_one(url, tmp_dir, i)
            except Exception as e:  # noqa: BLE001 - 1 file lỗi không chặn các file khác
                (tmp_dir / f"LOI_{i:03d}.txt").write_text(f"{url}\n{e}", encoding="utf-8")

        for j, item in enumerate(ytdlp_items):
            try:
                _download_with_ytdlp(item["page_url"], tmp_dir, audio_only=(item.get("mode") == "audio"))
            except Exception as e:  # noqa: BLE001
                (tmp_dir / f"LOI_video_{j:03d}.txt").write_text(f"{item['page_url']}\n{e}", encoding="utf-8")

        if not any(tmp_dir.iterdir()):
            return jsonify({"error": "Tải thất bại hết, không có file nào."}), 500

        zip_base = tmp_dir.parent / f"bmd_{job_id}"
        zip_path = shutil.make_archive(str(zip_base), "zip", root_dir=tmp_dir)
        return send_file(zip_path, as_attachment=True, download_name="media.zip")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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

    opts = {
        "outtmpl": str(tmp_dir / "%(title).80s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
    }
    if audio_only:
        # Cần có ffmpeg trong PATH của máy -- nếu thiếu, yt-dlp báo lỗi rõ
        # ràng, được ghi vào file LOI_*.txt trong ZIP kết quả thay vì crash.
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = "best"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([page_url])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
