# Bulk Media Downloader

Dán 1 hoặc nhiều link, quét toàn bộ ảnh/video/audio, chọn và tải hàng loạt về dạng 1 file ZIP.

**Tính năng:**
- Dán nhiều link cùng lúc (mỗi dòng 1 link) — quét và tải gộp 1 lần.
- **TikTok: tự động tải bản KHÔNG watermark** (lấy thẳng link gốc từ API công khai, không phải xử lý ảnh xoá logo) + tải kèm nhạc nền nếu muốn.
- Video khác (YouTube, Twitter/X, Vimeo...): chọn tải nguyên video hoặc chỉ tách lấy âm thanh MP3.
- Giao diện báo rõ khi nào đã lấy được bản không watermark (nhãn xanh).

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

## Giới hạn

- Tối đa 20 link/lần quét, 60 file/lần tải — tránh vô tình tải quá tải máy hoặc gây tải nặng cho site đích.
- TikTok: nếu API `tikwm.com` tạm thời lỗi/quá tải, tool tự rơi về cách quét thường (không đảm bảo chắc chắn còn bản không watermark trong trường hợp này).
- Chỉ quét được nội dung có trong HTML tải về ban đầu (với các link không phải TikTok) — trang dùng JavaScript để load ảnh/video động (infinite scroll, SPA nặng React/Vue) có thể cần cuộn/tương tác trước nên quét không ra hết.
- `yt-dlp` hỗ trợ hàng nghìn site nhưng không phải tất cả — một số nền tảng có thể chặn hoặc cần đăng nhập.
- Đây là tool chạy local/cá nhân (dữ liệu job giữ trong RAM), không thiết kế để deploy public nhiều người dùng cùng lúc.
- **Chỉ dùng để tải nội dung bạn có quyền tải** (của bạn, public domain, hoặc được phép) — tôn trọng bản quyền và điều khoản dịch vụ của từng website.
