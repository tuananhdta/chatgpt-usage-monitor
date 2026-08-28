# Prompt để dùng trong Codex App

Copy toàn bộ đoạn dưới đây vào Codex App sau khi mở folder project:

---

Hãy đọc toàn bộ project này, đặc biệt `README_VI.md`.

Mục tiêu của project:

- Có 4 ChatGPT Plus accounts: acc01, acc02, acc03, acc04.
- Mỗi account phải dùng một `CODEX_HOME` riêng trong `codex_profiles/<account>`.
- Dùng `codex app-server` và method `account/rateLimits/read`.
- Lấy 5-hour limit (300 phút) và weekly limit (10080 phút).
- Dùng `resetsAt` làm Unix timestamp và convert sang giờ Việt Nam UTC+7.
- Tuyệt đối không dùng Playwright, không copy cookie/token, không OCR.

Việc cần làm trước mắt:

1. Kiểm tra code hiện tại có chạy tốt trên Windows không.
2. Không đổi kiến trúc nếu không cần thiết.
3. Hướng dẫn tôi setup lần lượt acc01 → acc04.
4. Sau mỗi login, chạy verify để hiện email + plan + 5h + weekly.
5. Nếu có lỗi, sửa trực tiếp file trong project rồi nói rõ file nào đã sửa.
6. Sau khi đủ 4 account, chạy `python collect_all.py`.
7. Chưa làm Slack/dashboard cho đến khi cả 4 account đọc usage thành công.

Các requirement cuối cùng sau này:

- Chạy trên Windows cá nhân.
- Thứ 2 đến Thứ 6.
- Chạy lúc 09:00, 10:00, 11:00, 13:00, 14:00, 15:00, 16:00, 17:00.
- Mỗi lần lấy 4 account, tạo 1 dashboard PNG và gửi vào 1 Slack channel.
- Hiển thị giờ reset tuyệt đối theo Asia/Ho_Chi_Minh, không hiển thị countdown.

Bắt đầu bằng cách kiểm tra các file hiện tại và hướng dẫn tôi setup `acc01`.
---
