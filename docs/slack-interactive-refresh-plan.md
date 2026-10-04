# Kế hoạch tích hợp Refresh tương tác trên Slack

## 1. Mục tiêu

Cho phép user bấm nút `Refresh` trực tiếp trên Slack để cập nhật limit của cả 4 tài khoản ngoài các khung giờ automation cố định.

Mỗi lần refresh thành công sẽ:

- thu thập usage mới của 4 tài khoản;
- lưu dữ liệu vào `data/usage.json`;
- render lại `data/dashboard.png`;
- gửi `dashboard.png` mới trực tiếp vào channel Slack như một message/file riêng;
- không gửi dashboard vào Thread reply;
- không cập nhật đè hoặc xóa các dashboard cũ trên Slack.

## 2. Trạng thái hiện tại

Project hiện đã có pipeline một lần gồm:

```text
collect_all.py
    -> data/usage.json
    -> render_dashboard.py
    -> data/dashboard.png
    -> upload dashboard lên Slack
```

Automation theo lịch đang gọi pipeline này. Slack hiện chủ yếu được dùng để nhận file dashboard; chưa có listener xử lý nút bấm tương tác.

## 3. Kiến trúc mục tiêu

```text
Slack Control Panel
        |
        | user bấm Refresh
        v
Slack listener chạy nền
        |
        | gọi pipeline dùng chung
        v
Collect usage -> Render PNG -> Upload file mới vào channel
```

### 3.1. Control Panel

Tạo một Block Kit message cố định trong channel:

```text
ChatGPT Usage Monitor Control

[Refresh]
```

Message này chỉ dùng để điều khiển. Dashboard PNG sẽ được gửi thành message/file độc lập sau mỗi lần chạy.

### 3.2. Pipeline dùng chung

Tách phần xử lý thành một hàm hoặc service dùng chung cho cả automation và thao tác thủ công:

```text
refresh_usage(source, requested_by)
    -> collect 4 accounts
    -> save usage.json
    -> render dashboard.png
    -> upload dashboard.png trực tiếp vào channel
```

Hai nguồn gọi pipeline:

- `source=automation`: chạy theo Task Scheduler;
- `source=manual`: user bấm nút `Refresh` trên Slack.

## 4. Các phase triển khai

### Phase 0 — Chốt hành vi và chuẩn bị cấu hình

Mục tiêu: xác nhận các quy tắc trước khi code.

Việc cần làm:

- xác nhận channel đích;
- xác nhận user Slack được phép bấm `Refresh`;
- xác nhận giữ lại toàn bộ dashboard cũ trên Slack;
- xác nhận cooldown giữa hai lần refresh, đề xuất 30–60 giây;
- kiểm tra bot token hiện tại có quyền `chat:write` và `files:write`;
- chuẩn bị app-level token với `connections:write` nếu dùng Socket Mode.

Kết quả:

- có channel ID;
- có danh sách Slack user ID được phép;
- có cấu hình token và cooldown rõ ràng.

### Phase 1 — Chuẩn hóa pipeline refresh

Mục tiêu: automation và manual refresh dùng cùng một logic.

Việc cần làm:

- gom collect, render và upload vào một pipeline dùng chung;
- thêm metadata `source`, `requested_by`, `requested_at`;
- bảo đảm lỗi của một account không làm mất kết quả của các account còn lại;
- chuẩn hóa caption khi upload dashboard;
- giữ nguyên hành vi automation hiện tại.

Caption đề xuất:

```text
ChatGPT Usage Monitor
Source: Manual refresh
Requested by: TuanAnh
Updated: 04/10/2026 10:15
```

Kết quả:

- chạy manual hoặc automation đều tạo cùng một loại dashboard;
- dashboard được upload trực tiếp vào channel, không vào thread.

### Phase 2 — Tạo Slack Control Panel

Mục tiêu: tạo message có nút `Refresh`.

Việc cần làm:

- tạo Block Kit message;
- thêm button với `action_id` cố định, ví dụ `refresh_usage`;
- lưu message timestamp nếu cần quản lý hoặc tái tạo Control Panel;
- chỉ để Control Panel làm nơi điều khiển, không dùng nó để chứa dashboard PNG.

Kết quả:

- user nhìn thấy nút `Refresh` trong Slack;
- nút chưa cần chạy logic thật cho đến khi listener được kết nối.

### Phase 3 — Kết nối tương tác Slack

Mục tiêu: nhận được sự kiện khi user bấm nút.

Phương án đề xuất cho máy Windows local: **Socket Mode**.

Việc cần làm:

- bật Socket Mode trong Slack App;
- tạo app-level token với scope `connections:write`;
- tạo listener chạy nền, ví dụ `slack_listener.py`;
- nhận interaction payload từ Slack;
- xác thực workspace và Slack user ID;
- phản hồi ngay trạng thái `Refresh đang chạy`.

Socket Mode phù hợp vì không cần mở public HTTP endpoint cho máy Windows local.

Kết quả:

- Slack listener nhận được nút bấm;
- user được phản hồi ngay cả khi pipeline cập nhật mất nhiều thời gian.

### Phase 4 — Chạy refresh background và upload dashboard mới

Mục tiêu: xử lý việc refresh sau khi đã phản hồi nhanh cho Slack.

Việc cần làm:

- đưa pipeline refresh vào background job;
- dùng lock để không chạy đồng thời hai refresh;
- kiểm tra cooldown trước khi chạy;
- gọi collect usage cho cả 4 account;
- render lại `data/dashboard.png`;
- upload file mới trực tiếp vào channel;
- giữ lại các dashboard cũ;
- ghi log kết quả manual refresh.

Luồng thành công:

```text
User bấm Refresh
    -> Slack nhận phản hồi ngay
    -> Background job chạy
    -> dashboard.png được render lại
    -> dashboard.png mới xuất hiện trực tiếp trong channel
```

Luồng lỗi:

```text
User bấm Refresh
    -> Slack nhận phản hồi ngay
    -> Background job lỗi
    -> gửi thông báo lỗi riêng trực tiếp vào channel
    -> ghi chi tiết vào log
```

### Phase 5 — Tích hợp với Windows Task Scheduler

Mục tiêu: giữ automation hiện tại và cho phép hai nguồn chạy song song an toàn.

Việc cần làm:

- cập nhật task automation để gọi pipeline dùng chung;
- không để task Scheduler chạy trùng với manual refresh;
- ghi rõ `source=automation` trong caption và log;
- kiểm tra quyền chạy khi task khởi động cùng Windows;
- bảo đảm listener tự khởi động cùng Windows hoặc được khôi phục sau lỗi.

Kết quả:

- automation tiếp tục gửi dashboard trực tiếp theo lịch;
- user có thể bấm `Refresh` ngoài lịch;
- không có hai job cùng ghi hoặc upload dữ liệu đồng thời.

### Phase 6 — Kiểm thử và vận hành

Mục tiêu: xác nhận toàn bộ luồng thực tế.

Các test bắt buộc:

1. Bấm `Refresh` khi không có automation đang chạy.
2. Bấm liên tiếp hai lần trong thời gian cooldown.
3. Bấm `Refresh` trong lúc automation đang chạy.
4. Một account bị lỗi hoặc logout.
5. Slack listener bị restart.
6. Máy Windows restart.
7. Slack API hoặc ChatGPT API tạm thời lỗi.
8. Xác nhận dashboard mới nằm trực tiếp trong channel, không nằm trong thread.
9. Xác nhận dashboard cũ vẫn còn.
10. Xác nhận caption thể hiện đúng `manual` hoặc `automation`.

## 5. Quy tắc chống lỗi và bảo mật

- Chỉ Slack user trong allowlist mới được refresh.
- Không log bot token, app token hoặc authentication state.
- Dùng lock cho pipeline.
- Có cooldown để tránh spam Slack và ChatGPT API.
- Phản hồi interaction ngay, không chờ collect hoàn tất.
- Nếu refresh lỗi, không upload dashboard cũ với timestamp mới.
- Nếu một account lỗi, caption phải ghi rõ account lỗi.
- Giữ authentication state trong `codex_profiles/` và không đưa lên GitHub.

## 6. Tiêu chí nghiệm thu

Tính năng được xem là hoàn thành khi:

- user bấm `Refresh` trực tiếp trên Slack;
- không cần mở terminal;
- limit của 4 account được cập nhật;
- `data/usage.json` và `data/dashboard.png` được tạo lại;
- một `dashboard.png` mới được gửi trực tiếp vào channel;
- dashboard mới không nằm trong Thread reply;
- dashboard cũ không bị xóa hoặc ghi đè trên Slack;
- automation theo lịch vẫn hoạt động;
- thao tác refresh trùng hoặc không hợp lệ bị chặn an toàn;
- lỗi được báo rõ ràng trong Slack và log.

## 7. Thứ tự triển khai đề xuất

```text
Phase 0
   -> Phase 1
   -> Phase 2
   -> Phase 3
   -> Phase 4
   -> Phase 5
   -> Phase 6
```

Ưu tiên triển khai đến hết Phase 4 trước để có tính năng Refresh hoạt động thực tế. Phase 5 và Phase 6 dùng để hoàn thiện độ ổn định khi vận hành lâu dài.
