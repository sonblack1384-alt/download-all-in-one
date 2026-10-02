# Bulk Media Downloader

Dán link 1 trang web, quét toàn bộ ảnh/video trên trang, chọn và tải hàng loạt về dạng 1 file ZIP.

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

- Quét HTML của trang (`<img>`, `<video>`, `<source>`, link trực tiếp tới file ảnh/video) để tìm media.
- Nếu trang là 1 video đơn (YouTube, TikTok, Twitter/X, Vimeo...), thử thêm bằng `yt-dlp` để bắt được cả những video không nằm trong thẻ `<video>` thường.
- Chọn file muốn tải trên giao diện, bấm "Tải ZIP" — server tải từng file về rồi nén lại gửi về trình duyệt.

## Giới hạn

- Chỉ quét được nội dung có trong HTML tải về ban đầu — trang dùng JavaScript để load ảnh/video động (infinite scroll, SPA nặng React/Vue) có thể cần cuộn/tương tác trước nên quét không ra hết.
- `yt-dlp` hỗ trợ hàng nghìn site nhưng không phải tất cả — một số nền tảng có thể chặn.
- Đây là tool chạy local/cá nhân (dữ liệu job giữ trong RAM), không thiết kế để deploy public nhiều người dùng cùng lúc.
- **Chỉ dùng để tải nội dung bạn có quyền tải** (của bạn, public domain, hoặc được phép) — tôn trọng bản quyền và điều khoản dịch vụ của từng website.
