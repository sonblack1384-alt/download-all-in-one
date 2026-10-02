# Bulk Media Downloader

Dán 1 hoặc nhiều link, quét toàn bộ ảnh/video/audio, chọn và tải hàng loạt về dạng 1 file ZIP.

**Tính năng:**
- Dán nhiều link cùng lúc (mỗi dòng 1 link) — quét và tải gộp 1 lần.
- **TikTok: tự động tải bản KHÔNG watermark** (lấy thẳng link gốc từ API công khai, không phải xử lý ảnh xoá logo) + tải kèm nhạc nền nếu muốn.
- **Tải cả playlist/kênh/trang cá nhân khi dán 1 link** (bật checkbox tương ứng): YouTube playlist/channel, trang cá nhân TikTok — tối đa 30 video/lần để tránh quá tải.
- Video khác (YouTube, Twitter/X, Vimeo...): chọn tải nguyên video hoặc chỉ tách lấy âm thanh MP3.
- Giao diện báo rõ khi nào đã lấy được bản không watermark (nhãn xanh).
- Hỗ trợ cookie đăng nhập (`cookies.txt`) cho site chặn bot mạnh.

## Chạy

```
pip install -r requirements.txt
python3 app.py
```

Mở `http://localhost:5000`.

> **Lưu ý:** phải chạy lệnh `python3 app.py` (hoặc `run.bat`) **ngay trên máy Windows của bạn** rồi mới mở được `localhost:5000` trên trình duyệt máy đó — không chạy hộ được từ xa.

## Tự chạy mỗi khi mở máy Windows (không cần mở terminal gõ lệnh)

**Cách 1 — tự chạy khi đăng nhập Windows (đơn giản nhất):**
1. Cài Python từ [python.org](https://www.python.org/downloads/) nếu máy chưa có (khi cài, tick **"Add python.exe to PATH"**).
2. Mở Command Prompt tại thư mục này, chạy 1 lần: `pip install -r requirements.txt`
3. Nhấn `Win + R`, gõ `shell:startup`, Enter — mở thư mục Startup của Windows.
4. Copy file `run_silent.vbs` (trong thư mục này) vào thư mục Startup đó.
5. Từ lần đăng nhập Windows sau, server tự chạy ngầm (không hiện cửa sổ đen) — chỉ cần mở `http://localhost:5000`.

Muốn tắt: mở Task Manager → tìm tiến trình `pythonw.exe` → End Task. Muốn hết tự chạy: xoá file `run_silent.vbs` khỏi thư mục Startup.

**Cách 2 — chạy thủ công khi cần:** double-click `run.bat` (hiện cửa sổ đen có log, đóng cửa sổ là tắt server).

**Về "chạy 24/7":** 2 cách trên chỉ tự chạy *khi bạn đăng nhập Windows* — nếu tắt máy/ngủ đông thì server cũng tắt theo. Muốn thật sự 24/7 kể cả lúc không đăng nhập, cần: (a) vào Windows Settings → System → Power → tắt chế độ Sleep (không tắt máy), và (b) tạo task trong **Task Scheduler** với trigger "At startup" + tick "Run whether user is logged on or not" (nâng cao hơn, cần máy luôn bật nguồn). Đơn giản hơn nếu cần 24/7 thật: chạy tool này trên 1 VPS/server giá rẻ thay vì máy cá nhân — hỏi lại nếu muốn tôi hướng dẫn deploy lên VPS.

## Cách hoạt động

1. **Link TikTok** → gọi API công khai `tikwm.com` lấy thẳng link video gốc KHÔNG watermark (+ bản HD, + nhạc nền nếu có) — tải trực tiếp, không cần xử lý gì thêm.
2. **Các link khác** → quét HTML của trang (`<img>`, `<video>`, `<audio>`, `<source>`, link trực tiếp tới file ảnh/video/audio) để tìm media.
3. Nếu trang là 1 video đơn mà bước 2 không bắt được (YouTube, Twitter/X, Vimeo, Facebook công khai...), thử thêm bằng `yt-dlp`. Có thể chọn tải nguyên video hoặc chỉ tách âm thanh MP3 (cần cài `ffmpeg`, xem bên dưới).
4. Chọn file muốn tải trên giao diện, bấm "Tải ZIP" — server tải từng file về rồi nén lại gửi về trình duyệt.

## Cài thêm `ffmpeg` nếu muốn dùng tính năng tách MP3

Chỉ cần cho tính năng "chỉ lấy âm thanh (MP3)" của video YouTube/... (không cần cho TikTok hay tải video thường). Trên Windows: tải `ffmpeg` tại [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) (bản "release essentials"), giải nén, thêm thư mục `bin` bên trong vào PATH của Windows (Settings → System → About → Advanced system settings → Environment Variables → Path → New). Mở lại Command Prompt để nhận PATH mới, gõ `ffmpeg -version` để kiểm tra đã nhận chưa. Không cài thì tool vẫn tải video thường bình thường, chỉ riêng nút MP3 báo lỗi.

## Tải được site cần đăng nhập / chặn bot mạnh (Douyin, Instagram riêng tư...)

Một số site (ví dụ Douyin, Instagram riêng tư) báo lỗi kiểu `Fresh cookies needed`/`login required` — cần "cookie" (giống phiên đăng nhập trình duyệt) mới tải được, kể cả nội dung công khai. Tool xử lý theo đúng thứ tự ưu tiên (học từ kinh nghiệm thực tế dự án khác đã test thành công):

1. **Nếu có file `cookies.txt`** (định dạng Netscape, cùng thư mục `app.py`) → dùng file này, ưu tiên cao nhất.
2. **Nếu không có** → tool **tự lấy cookie SỐNG từ trình duyệt Firefox** đang cài trên máy (không cần làm gì thêm, tự động). Chỉ cần đã mở site đó (vd douyin.com) trong Firefox ít nhất 1 lần (không cần đăng nhập, chỉ cần có cookie phiên).

**Vì sao chọn Firefox làm mặc định:** Chrome/Edge khoá file cookie khi trình duyệt đang mở (lỗi "Could not copy Chrome cookie database") và có thể lỗi giải mã DPAPI trên một số máy Windows — Firefox không gặp vấn đề này. Muốn đổi sang trình duyệt khác: sửa dòng `COOKIES_BROWSER = "firefox"` ở đầu `app.py` thành `"chrome"`/`"edge"`/`"brave"`.

Nếu vẫn muốn dùng `cookies.txt` thủ công: cài extension **"Get cookies.txt LOCALLY"**, mở trang đó, xuất file, copy vào thư mục chứa `app.py`.

**Cảnh báo bảo mật:** `cookies.txt` (nếu dùng) = phiên đăng nhập thật của bạn (như mật khẩu) — **không gửi/chia sẻ cho ai, không commit lên GitHub** (đã tự động bị bỏ qua qua `.gitignore`).

### Douyin: vì sao cookie thôi chưa chắc đủ — lớp dự phòng trình duyệt thật

Đã xác minh bằng cách đọc thẳng mã nguồn `yt-dlp` (`extractor/tiktok.py`, class `DouyinIE`): Douyin yêu cầu 1 cookie (`s_v_web_id`) được **chính JavaScript chống bot của trang tạo ra tại thời điểm truy cập** — một số trường hợp cookie tĩnh/copy không đáp ứng được vì Douyin còn kiểm tra trình duyệt có "giải" đúng bài toán JS đó không.

Vì vậy tool có thêm 1 lớp dự phòng CUỐI dành riêng cho Douyin, chạy **lúc tải** (không phải lúc quét, để không mở trình duyệt 2 lần): dùng **trình duyệt thật chạy ngầm** (Playwright + Chromium headless) mở trang, bắt cả link video **và audio** (Douyin phát 2 luồng tách riêng, khác TikTok gộp chung), tải từng luồng rồi **ghép bằng ffmpeg** thành 1 file hoàn chỉnh. Tự thử lại tối đa 3 lần (chờ lâu hơn mỗi lần) nếu Douyin tạm chặn/chậm. Link Douyin dạng `?modal_id=<id>` (từ trang tìm kiếm) được tự động chuẩn hoá về `/video/<id>` trước khi xử lý.

Cần cài thêm (1 lần) để dùng lớp dự phòng này:
```
pip install playwright
playwright install chromium
```
(Tải khoảng 150-300MB cho Chromium, chỉ 1 lần.) Không cài thì tool vẫn hoạt động bình thường cho mọi link khác, chỉ riêng lớp dự phòng này cho Douyin bị bỏ qua.

**Lưu ý thành thật:** cơ chế bắt link video+audio qua trình duyệt **chưa được kiểm chứng với Douyin thật** (môi trường phát triển công cụ bị chặn mạng tới douyin.com) — chỉ xác nhận: (a) logic chuỗi dự phòng đúng, (b) cơ chế tải+ghép ffmpeg hoạt động đúng khi test với file giả lập, (c) Playwright chạy đúng cú pháp trên trang khác. Cần bạn tự thử trên máy và báo lại kết quả.

## Giới hạn (nói thật, không hứa suông "tải được mọi thứ")

- Tối đa 20 link/lần quét, 100 file/lần tải, 30 video/lần khi bật playlist/kênh — tránh vô tình tải quá tải máy hoặc gây tải nặng cho site đích.
- TikTok: nếu API `tikwm.com` tạm thời lỗi/quá tải, tool tự rơi về cách quét thường (không đảm bảo chắc chắn còn bản không watermark trong trường hợp này).
- **Douyin là site khó nhất hiện tại** — 3 lớp thử lần lượt (tikwm → trình duyệt thật, 3 lần thử → yt-dlp) nhưng Douyin đổi cơ chế chống bot liên tục nên không có gì đảm bảo 100%. Chạy `pip install -U yt-dlp` định kỳ để cập nhật bản vá mới nhất.
- Không ai tải được "mọi trang" tuyệt đối — đây là giới hạn công nghệ (yt-dlp hỗ trợ ~1750 trình nhận dạng trang, không phải vô hạn), không phải giới hạn riêng của tool này. Trang không có trình nhận dạng chỉ tải được nếu là link file trực tiếp (`.mp4`, `.m3u8`...) hoặc có `<video>`/`<img>` nhúng chuẩn.
- Chỉ quét được nội dung có trong HTML tải về ban đầu (với các link không phải TikTok) — trang dùng JavaScript để load ảnh/video động (infinite scroll, SPA nặng React/Vue) có thể cần cuộn/tương tác trước nên quét không ra hết.
- `yt-dlp` hỗ trợ hàng nghìn site nhưng không phải tất cả — một số nền tảng có thể chặn hoặc cần đăng nhập (dùng `cookies.txt`, xem mục trên).
- Đây là tool chạy local/cá nhân (dữ liệu job giữ trong RAM), không thiết kế để deploy public nhiều người dùng cùng lúc.
- **Chỉ dùng để tải nội dung bạn có quyền tải** (của bạn, public domain, hoặc được phép) — tôn trọng bản quyền và điều khoản dịch vụ của từng website.

## Cập nhật `yt-dlp` định kỳ

`yt-dlp` sửa lỗi extractor liên tục (site đổi cơ chế chống bot gần như hàng tuần). Nên chạy định kỳ:
```
pip install -U yt-dlp
```
