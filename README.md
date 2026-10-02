# Bulk Media Downloader

Dán link 1 trang web, quét toàn bộ ảnh/video trên trang, chọn và tải hàng loạt về dạng 1 file ZIP.

## Chạy

```
pip install -r requirements.txt
python3 app.py
```

Mở `http://localhost:5000`.

## Cách hoạt động

- Quét HTML của trang (`<img>`, `<video>`, `<source>`, link trực tiếp tới file ảnh/video) để tìm media.
- Nếu trang là 1 video đơn (YouTube, TikTok, Twitter/X, Vimeo...), thử thêm bằng `yt-dlp` để bắt được cả những video không nằm trong thẻ `<video>` thường.
- Chọn file muốn tải trên giao diện, bấm "Tải ZIP" — server tải từng file về rồi nén lại gửi về trình duyệt.

## Giới hạn

- Chỉ quét được nội dung có trong HTML tải về ban đầu — trang dùng JavaScript để load ảnh/video động (infinite scroll, SPA nặng React/Vue) có thể cần cuộn/tương tác trước nên quét không ra hết.
- `yt-dlp` hỗ trợ hàng nghìn site nhưng không phải tất cả — một số nền tảng có thể chặn.
- Đây là tool chạy local/cá nhân (dữ liệu job giữ trong RAM), không thiết kế để deploy public nhiều người dùng cùng lúc.
- **Chỉ dùng để tải nội dung bạn có quyền tải** (của bạn, public domain, hoặc được phép) — tôn trọng bản quyền và điều khoản dịch vụ của từng website.
