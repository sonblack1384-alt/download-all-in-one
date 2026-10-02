#!/usr/bin/env python3
"""Bulk media downloader -- scan a web page for images/videos, pick which
ones to grab, download them all as a single ZIP.

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

# Jobs in progress / finished, keyed by job_id. Kept in memory only -- fine
# for a single-user local tool, not meant for multi-user production use.
JOBS: dict[str, dict] = {}


def is_media_url(url: str, exts: tuple[str, ...]) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(exts)


def best_srcset_url(srcset: str) -> str | None:
    """srcset="a.jpg 480w, b.jpg 960w" -> pick the largest (last) candidate."""
    candidates = [c.strip() for c in srcset.split(",") if c.strip()]
    if not candidates:
        return None
    return candidates[-1].split()[0]


def scan_page(page_url: str) -> dict:
    found: dict[str, str] = {}  # url -> "image" | "video"
    fetch_error: str | None = None

    def add(raw_url: str | None, kind: str):
        if not raw_url or raw_url.startswith("data:"):
            return
        full = urljoin(page_url, raw_url)
        found.setdefault(full, kind)

    # Bước 1: thử tải HTML thô (nhanh, không cần trình duyệt). Nhiều trang
    # (Facebook, Instagram, TikTok...) chặn request kiểu này (403/400) hoặc
    # trả về trang rỗng vì nội dung load bằng JavaScript -- KHÔNG bỏ cuộc ở
    # đây, ghi lại lỗi rồi vẫn thử yt-dlp ở bước 2 (yt-dlp có cách lấy dữ
    # liệu riêng, không phụ thuộc vào việc parse HTML này).
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
    except requests.RequestException as e:
        fetch_error = str(e)

    images = sorted(u for u, k in found.items() if k == "image")
    videos = sorted(u for u, k in found.items() if k == "video")

    # Bước 2: luôn thử yt-dlp (chạy dù bước 1 lỗi hay không) -- hỗ trợ
    # hàng nghìn site video (YouTube, TikTok, Twitter/X, Vimeo, Facebook
    # công khai...), có cơ chế bắt dữ liệu riêng mạnh hơn request thường.
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

    if not images and not videos and not ytdlp_video:
        # Cả 2 cách đều không ra gì -- báo lỗi rõ ràng thay vì chỉ "không tìm thấy".
        reason = fetch_error or ytdlp_error or "trang không có ảnh/video nào đọc được"
        raise ScanFailed(reason)

    return {"images": images, "videos": videos, "ytdlp_video": ytdlp_video}


class ScanFailed(Exception):
    pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    page_url = (request.json or {}).get("url", "").strip()
    if not page_url.startswith(("http://", "https://")):
        return jsonify({"error": "URL không hợp lệ -- phải bắt đầu bằng http:// hoặc https://"}), 400
    try:
        result = scan_page(page_url)
    except ScanFailed as e:
        return jsonify({"error": f"Không quét được trang này: {e}"}), 400
    return jsonify(result)


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.json or {}
    urls: list[str] = data.get("urls", [])
    ytdlp_video = data.get("ytdlp_video")
    if not urls and not ytdlp_video:
        return jsonify({"error": "Chưa chọn file nào để tải."}), 400

    job_id = uuid.uuid4().hex
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"bmd_{job_id}_"))

    try:
        for i, url in enumerate(urls):
            try:
                _download_one(url, tmp_dir, i)
            except Exception as e:  # noqa: BLE001 - 1 file lỗi không chặn các file khác
                (tmp_dir / f"LOI_{i:03d}.txt").write_text(f"{url}\n{e}", encoding="utf-8")

        if ytdlp_video:
            try:
                _download_with_ytdlp(ytdlp_video["page_url"], tmp_dir)
            except Exception as e:  # noqa: BLE001
                (tmp_dir / "LOI_video.txt").write_text(f"{ytdlp_video['page_url']}\n{e}", encoding="utf-8")

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
        name += ".bin"
    out_path = tmp_dir / f"{index:03d}_{name}"
    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


def _download_with_ytdlp(page_url: str, tmp_dir: Path):
    import yt_dlp

    opts = {
        "outtmpl": str(tmp_dir / "%(title).80s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "format": "best",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([page_url])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
