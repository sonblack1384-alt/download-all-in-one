# Lịch sử làm việc — Bulk Media Downloader

> Đọc file này trước nếu tiếp tục dự án ở phiên Claude/tài khoản khác — ghi lại trạng thái hiện tại, quyết định kỹ thuật, và việc đang chờ xử lý.

## Dự án là gì
Tool web local (Flask) để dán 1 hoặc nhiều link, quét ảnh/video/audio trên trang, chọn và tải hàng loạt về 1 file ZIP. Chạy trên máy Windows của người dùng (không phải server công cộng).

Repo: https://github.com/sonblack1384-alt/download-all-in-one

## Trạng thái hiện tại (2026-10-02)

### Đã làm, đã test thật
- **Quét HTML cơ bản** (`<img>`, `<video>`, `<audio>`, `<source>`, link trực tiếp tới file ảnh/video/audio) — test thật với pypi.org, ra đúng kết quả.
- **Dán nhiều link cùng lúc** (textarea, mỗi dòng 1 link) — `/api/scan_batch`, mỗi link ra 1 nhóm kết quả riêng, gộp tải chung 1 ZIP.
- **TikTok: tải bản KHÔNG watermark** — gọi thẳng API công khai `tikwm.com`, lấy link gốc (không qua yt-dlp). Đúng kỹ thuật chuẩn các tool "tải TikTok không logo" dùng. **Chưa test được thật trong môi trường dev** (mạng sandbox chặn tiktok.com/tikwm.com) — cần người dùng xác nhận trên máy thật.
- **Tải cả playlist/kênh/trang cá nhân khi dán 1 link** (checkbox, tối đa 30 video): YouTube playlist/channel qua yt-dlp (`extract_flat`), trang cá nhân TikTok qua `tikwm.com/api/user/posts`. Logic đã test bằng mock (giả lập response), chưa test với dữ liệu thật.
- **Tách audio MP3** từ video (yt-dlp + ffmpeg) — cần người dùng tự cài `ffmpeg` (đã ghi trong README).
- **Hỗ trợ `cookies.txt`** (định dạng Netscape) cho site cần đăng nhập/chặn bot — tự nhận nếu đặt file cùng thư mục `app.py`.
- **Nâng `yt-dlp` lên bản mới nhất** (`>=2026.8.19`, trước đó bị pin cứng bản 2024.8.6 cũ 2 năm).
- Script tự chạy khi mở Windows (`run_silent.vbs` + hướng dẫn đặt vào thư mục Startup), `run.bat` chạy thủ công.

### Vấn đề đã gặp và đã xử lý
- **Môi trường dev (Claude Code Remote) có chính sách mạng giới hạn domain** — chỉ gọi được `pypi.org`/`files.pythonhosted.org` (bypass proxy) và vài domain khác đã allowlist từ trước; **không** gọi được `tiktok.com`, `douyin.com`, `tikwm.com`, `youtube.com`, `facebook.com`... Hệ quả: nhiều tính năng chỉ kiểm chứng được logic/code path (qua mock hoặc test với site thay thế như pypi.org), KHÔNG kiểm chứng được hành vi thật với các platform đích. Luôn nói rõ điều này với người dùng, không nhận là "đã test" khi chỉ test được logic.
- **File mẫu test hỏng do thiếu header** (bài học từ dự án khác, áp dụng chung): luôn kiểm tra output file thật (`file`, `unzip -l`, ffprobe...) trước khi báo đã xong.
- **Douyin báo lỗi "Fresh cookies (not necessarily logged in) are needed"** dù đã đặt đúng `cookies.txt` — đã xác minh root cause thật bằng cách đọc thẳng mã nguồn `yt-dlp` (`extractor/tiktok.py`, class `DouyinIE`): Douyin yêu cầu cookie `s_v_web_id` được **JavaScript chống bot của chính trang tạo ra tại thời điểm truy cập**, cookie tĩnh copy từ trình duyệt không đáp ứng được. Đã thêm lớp dự phòng `douyin_via_browser()` dùng Playwright + Chromium headless (mở trang thật, để JS tự giải bài toán chống bot, đọc link video từ thẻ `<video>`). **CHƯA kiểm chứng được với Douyin thật** — chỉ xác nhận Playwright hoạt động đúng cú pháp qua trang khác (pypi.org), do môi trường dev bị chặn mạng tới douyin.com. Cần người dùng tự thử trên máy và báo lại.

### Chuỗi dự phòng hiện tại cho TikTok/Douyin (theo thứ tự thử)
1. `tiktok_no_watermark()` — API `tikwm.com`, nhanh, tin cậy cho TikTok, chưa chắc hỗ trợ Douyin.
2. Nếu là Douyin và (1) thất bại: `douyin_via_browser()` — Playwright, chậm hơn (vài giây/link), cần cài thêm (`pip install playwright && playwright install chromium`), chưa test thật.
3. Nếu cả 2 trên đều thất bại: quét HTML thường + `yt-dlp` — với Douyin gần như chắc chắn cũng lỗi cùng nguyên nhân cookie.

## Việc đang chờ / cần làm tiếp
1. **Người dùng cần xác nhận**: link TikTok thường (`tiktok.com`, không phải Douyin) đã tải được bản không watermark thật chưa — đây là tính năng lõi, cần xác nhận hoạt động trước khi tin các tính năng khác dựa trên cùng cơ chế (tikwm).
2. **Người dùng cần thử lớp dự phòng Douyin** (`pip install playwright && playwright install chromium`, tải lại code mới nhất) và báo kết quả thật — nếu vẫn lỗi, cần xem Douyin có đổi thêm cơ chế gì mới (ví dụ chặn luôn cả trình duyệt headless qua việc phát hiện dấu hiệu automation — `navigator.webdriver`) thì cần thêm bước che giấu dấu hiệu headless (`playwright-stealth` hoặc tự set thêm init script).
3. Chưa test thật tính năng playlist/kênh YouTube và trang cá nhân TikTok với dữ liệu thật — chỉ test bằng mock.
4. Chưa test thật tính năng tách MP3 (cần ffmpeg, cũng cần yt-dlp gọi được site thật).
5. Nếu Douyin vẫn không tải được sau khi thử lớp trình duyệt thật: cân nhắc tìm thư viện Python chuyên biệt cho Douyin (ví dụ dự án mã nguồn mở "f2" — chưa tích hợp, chưa đánh giá độ ổn định/bảo trì).

## Quyết định kỹ thuật đáng ghi nhớ
- **Không pin cứng version `yt-dlp`** (dùng `>=`) vì đây là package cần cập nhật thường xuyên để theo kịp các site đổi cơ chế chống bot — khác với các package khác (Flask, requests...) nên pin cứng để ổn định.
- **`playwright` là dependency tuỳ chọn** (import graceful-fail trong code) — không bắt buộc cài cho người dùng không cần tải Douyin, tránh ép tải thêm ~300MB Chromium không cần thiết.
- **`cookies.txt` không commit lên git** (`.gitignore`) — chứa phiên đăng nhập thật của người dùng.
- Giới hạn an toàn: 20 link/lần quét, 100 file/lần tải, 30 video/lần khi bật playlist — tránh vô tình tải quá tải máy hoặc gây tải nặng cho site đích.
- Nguyên tắc xuyên suốt: **không báo "đã xong"/"✓" khi chưa test được thật** — nếu môi trường dev không gọi được network tới platform đích, phải nói rõ "chưa kiểm chứng được, cần bạn thử" thay vì nhận vơ là đã hoạt động.
