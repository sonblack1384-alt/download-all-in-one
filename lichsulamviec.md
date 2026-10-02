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
- **Hỗ trợ `cookies.txt`** (định dạng Netscape) cho site cần đăng nhập/chặn bot — tự nhận nếu đặt file cùng thư mục `app.py`, ƯU TIÊN CAO NHẤT nếu có.
- **Tự lấy cookie SỐNG từ trình duyệt Firefox** (yt-dlp `cookiesfrombrowser`) khi không có `cookies.txt` tĩnh — chỉ bật cho site thật sự cần (Douyin, Instagram), không áp dụng tràn lan. Kỹ thuật lấy từ tài liệu `CAU_HINH_QUET_TAI_LINK.md` của dự án DichPhimPro (đã test thật thành công) — Firefox được chọn vì Chrome/Edge khoá file cookie khi đang mở + lỗi DPAPI trên 1 số máy Windows.
- **Nâng `yt-dlp` lên bản mới nhất** (`>=2026.8.19`, trước đó bị pin cứng bản 2024.8.6 cũ 2 năm).
- **Chuẩn hoá link Douyin dạng `?modal_id=<id>`** (từ trang tìm kiếm) thành `/video/<id>` trước khi xử lý — yt-dlp chỉ nhận dạng link chuẩn.
- Script tự chạy khi mở Windows (`run_silent.vbs` + hướng dẫn đặt vào thư mục Startup), `run.bat` chạy thủ công.
- **Tải nền + bảng nhật ký tiến trình + Huỷ/Thử lại** (2026-10-02, theo yêu cầu người dùng: "tạo tiến trình log để bit dag thực hiện tới đâu..." rồi "có bảng log nhật ký, chạy tiến trình từng khâu trong bảng đấy, để bit lỗi ở đâu lun"):
  - Backend: tải chạy trong `threading.Thread` riêng (không chặn request HTTP), job lưu trong `JOBS` dict (bộ nhớ, khoá bằng `threading.Lock`). 4 route mới thay cho `/api/download` cũ: `POST /api/download/start` (trả `job_id` ngay), `GET /api/download/status/<job_id>` (trạng thái `running`/`done`/`error`/`cancelled` + toàn bộ log dòng theo thời gian thực), `POST /api/download/cancel/<job_id>` (đặt cờ huỷ, kiểm tra giữa mỗi file và trong lúc Douyin đang chờ thử lại), `GET /api/download/result/<job_id>` (gửi file ZIP, tự xoá ZIP + dọn job sau khi gửi xong qua `call_on_close`).
  - Mỗi file tải lỗi KHÔNG làm hỏng cả job — ghi file `LOI_*.txt` mô tả lỗi vào trong ZIP, dòng log tương ứng hiện rõ `-> Lỗi: <chi tiết>` để biết đúng bước nào hỏng.
  - Frontend: bảng "Nhật ký tiến trình" (`#logPanel`) hiện dưới nút Tải ZIP, poll `status` mỗi 1 giây, tô đỏ dòng có "lỗi", tô xanh dòng "xong"/"hoàn tất". Nút **Huỷ** hiện khi đang chạy, nút **Thử lại** hiện khi lỗi/huỷ (gọi lại đúng danh sách file đã chọn, không cần chọn lại).
  - Flask chạy `threaded=True` để xử lý được song song: 1 thread tải nền + nhiều request poll status liên tục.
  - **Đã test thật bằng curl** (giả lập đúng chuỗi gọi fetch của JS): start → poll status thấy log tăng dần đúng thứ tự → done → GET result trả ZIP thật mở được; test riêng ca lỗi (link 404) → log hiện đúng dòng lỗi, job vẫn "done" với ZIP chứa file `LOI_*.txt`; test riêng nút Huỷ (job Douyin giả, đang ở vòng thử lại) → gọi cancel → status chuyển `cancelled` kèm log "Đã huỷ theo yêu cầu." — xác nhận cơ chế huỷ hoạt động đúng ở cả bước đang chờ (sleep) giữa các lần thử. Chưa test được việc bấm nút trên trình duyệt thật (không có browser trong sandbox) — logic JS chỉ soát qua `node -e "new Function(...)"` để chắc không lỗi cú pháp.

### Vấn đề đã gặp và đã xử lý
- **Môi trường dev (Claude Code Remote) có chính sách mạng giới hạn domain** — chỉ gọi được `pypi.org`/`files.pythonhosted.org` (bypass proxy) và vài domain khác đã allowlist từ trước; **không** gọi được `tiktok.com`, `douyin.com`, `tikwm.com`, `youtube.com`, `facebook.com`... Hệ quả: nhiều tính năng chỉ kiểm chứng được logic/code path (qua mock hoặc test với site thay thế như pypi.org), KHÔNG kiểm chứng được hành vi thật với các platform đích. Luôn nói rõ điều này với người dùng, không nhận là "đã test" khi chỉ test được logic.
- **File mẫu test hỏng do thiếu header** (bài học từ dự án khác, áp dụng chung): luôn kiểm tra output file thật (`file`, `unzip -l`, ffprobe...) trước khi báo đã xong.
- **Douyin báo lỗi "Fresh cookies (not necessarily logged in) are needed"** dù đã đặt đúng `cookies.txt` — đã xác minh root cause thật bằng cách đọc thẳng mã nguồn `yt-dlp` (`extractor/tiktok.py`, class `DouyinIE`): Douyin yêu cầu cookie `s_v_web_id` được **JavaScript chống bot của chính trang tạo ra tại thời điểm truy cập**, cookie tĩnh copy từ trình duyệt không đáp ứng được trong mọi trường hợp. Đã thêm lớp dự phòng dùng Playwright + Chromium headless. **CHƯA kiểm chứng được với Douyin thật** (môi trường dev bị chặn mạng tới douyin.com) — chỉ xác nhận logic/cơ chế đúng qua test với mock + trang khác. Cần người dùng tự thử trên máy và báo lại.
- **Người dùng gửi `CAU_HINH_QUET_TAI_LINK.md`** — tài liệu cấu hình từ dự án khác (`DichPhimPro`) đã test thật thành công cả YouTube/TikTok/Douyin/Facebook/Instagram. Áp dụng ngay 4 kỹ thuật đã kiểm chứng: chuẩn hoá link Douyin `modal_id`, tự lấy cookie Firefox, bắt + ghép audio/video riêng cho Douyin (khác TikTok gộp chung 1 luồng), thử lại 3 lần khi Douyin tạm chặn. Xem repo đó (nếu có quyền truy cập) để tham khảo thêm cấu trúc API đầy đủ hơn (hàng đợi tải, quét kênh chạy nền, tìm theo từ khoá) nếu muốn nâng cấp tool này lên mức tương đương.

### Chuỗi dự phòng hiện tại cho TikTok/Douyin (theo thứ tự thử)
1. `tiktok_no_watermark()` — API `tikwm.com`, nhanh, tin cậy cho TikTok, chưa chắc hỗ trợ Douyin.
2. Nếu là Douyin và (1) thất bại: trả về `douyin_items` ở bước quét (KHÔNG mở trình duyệt lúc này) → lúc người dùng bấm tải, `_download_douyin_via_browser()` mới thật sự mở Playwright, bắt link video+audio riêng, ghép ffmpeg, thử lại tối đa 3 lần. Cần cài thêm (`pip install playwright && playwright install chromium`), chưa test thật với Douyin.
3. Nếu cả 2 trên đều thất bại (hoặc không phải Douyin): quét HTML thường + `yt-dlp` (tự thử cookie Firefox nếu là site cần, xem `needs_browser_cookies`).

## Việc đang chờ / cần làm tiếp
1. **Người dùng cần xác nhận**: link TikTok thường (`tiktok.com`, không phải Douyin) đã tải được bản không watermark thật chưa — đây là tính năng lõi, cần xác nhận hoạt động trước khi tin các tính năng khác dựa trên cùng cơ chế (tikwm).
2. **Người dùng cần thử lớp dự phòng Douyin** (`pip install playwright && playwright install chromium`, tải lại code mới nhất) và báo kết quả thật — nếu vẫn lỗi, cần xem Douyin có đổi thêm cơ chế gì mới (ví dụ chặn luôn cả trình duyệt headless qua việc phát hiện dấu hiệu automation — `navigator.webdriver`) thì cần thêm bước che giấu dấu hiệu headless (`playwright-stealth` hoặc tự set thêm init script).
3. Chưa test thật tính năng playlist/kênh YouTube và trang cá nhân TikTok với dữ liệu thật — chỉ test bằng mock.
4. Chưa test thật tính năng tách MP3 (cần ffmpeg, cũng cần yt-dlp gọi được site thật).
5. Chưa test thật `cookiesfrombrowser` (Firefox) — chỉ xác nhận logic chọn đúng khi nào bật/tắt, chưa xác nhận yt-dlp đọc được cookie Firefox thật trên Windows.
6. Nếu Douyin vẫn không tải được sau khi thử lớp trình duyệt thật: cân nhắc tìm thư viện Python chuyên biệt cho Douyin (ví dụ dự án mã nguồn mở "f2" — chưa tích hợp, chưa đánh giá độ ổn định/bảo trì), hoặc xem cách `DichPhimPro` (`core/douyin_grab.py`) đã làm để tham khảo thêm chi tiết.

## Quyết định kỹ thuật đáng ghi nhớ
- **Không pin cứng version `yt-dlp`** (dùng `>=`) vì đây là package cần cập nhật thường xuyên để theo kịp các site đổi cơ chế chống bot — khác với các package khác (Flask, requests...) nên pin cứng để ổn định.
- **`playwright` là dependency tuỳ chọn** (import graceful-fail trong code) — không bắt buộc cài cho người dùng không cần tải Douyin, tránh ép tải thêm ~300MB Chromium không cần thiết.
- **`cookies.txt` không commit lên git** (`.gitignore`) — chứa phiên đăng nhập thật của người dùng.
- Giới hạn an toàn: 20 link/lần quét, 100 file/lần tải, 30 video/lần khi bật playlist — tránh vô tình tải quá tải máy hoặc gây tải nặng cho site đích.
- Nguyên tắc xuyên suốt: **không báo "đã xong"/"✓" khi chưa test được thật** — nếu môi trường dev không gọi được network tới platform đích, phải nói rõ "chưa kiểm chứng được, cần bạn thử" thay vì nhận vơ là đã hoạt động.
