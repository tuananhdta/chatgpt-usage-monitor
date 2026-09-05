# ChatGPT Usage Monitor — bản dùng với Codex App

## Mục tiêu cuối cùng

Quản lý 4 ChatGPT Plus accounts:

- Acc 01
- Acc 02
- Acc 03
- Acc 04

Lấy:

- 5-hour remaining
- 5-hour reset time chính xác
- Weekly remaining
- Weekly reset time chính xác

Sau đó (Phase 3):

- render dashboard PNG
- gửi vào 1 Slack channel
- tự chạy Thứ 2 → Thứ 6 tại:
  - 09:00
  - 10:00
  - 11:00
  - 13:00
  - 14:00
  - 15:00
  - 16:00
  - 17:00

## Điều đã xác nhận hoạt động

Codex App Server trả đúng:

- primary = 300 phút (5 giờ)
- secondary = 10080 phút (7 ngày)
- usedPercent
- resetsAt

Do đó KHÔNG cần:

- Playwright
- Chrome profile automation
- OCR
- countdown
- copy cookie/token

## Cấu trúc

```text
chatgpt-usage-monitor-codex-app/
├── README_VI.md
├── PROMPT_FOR_CODEX_APP.md
├── accounts.json
├── codex_client.py
├── setup_account.py
├── collect_all.py
├── run_setup_acc01.cmd
├── run_setup_acc02.cmd
├── run_setup_acc03.cmd
├── run_setup_acc04.cmd
├── run_collect_all.cmd
├── codex_profiles/
└── data/
```

## Cách dễ nhất: dùng Codex App

1. Giải nén project.
2. Mở Codex App.
3. Open Folder → chọn thư mục project.
4. Mở file `PROMPT_FOR_CODEX_APP.md`.
5. Copy prompt trong đó vào Codex App.
6. Yêu cầu Codex đọc project và hỗ trợ chạy từng bước.

## Setup Acc01

Trong terminal của Codex App hoặc Windows Terminal:

```powershell
python setup_account.py --account acc01
```

Hoặc double-click:

```text
run_setup_acc01.cmd
```

Codex sẽ mở login flow.

Đăng nhập đúng ChatGPT Account 01.

Sau login, script tự verify:

```text
Profile:   acc01
Email:     ...
Plan:      plus

5 HR LIMIT
  Used:      ...
  Remaining: ...
  Reset VN:  ...

WEEKLY LIMIT
  Used:      ...
  Remaining: ...
  Reset VN:  ...
```

Kiểm tra EMAIL đúng account rồi mới sang Acc02.

## Setup Acc02-04

```powershell
python setup_account.py --account acc02
python setup_account.py --account acc03
python setup_account.py --account acc04
```

Hoặc double-click các `.cmd` tương ứng.

## Test cả 4

```powershell
python collect_all.py
```

Hoặc:

```text
run_collect_all.cmd
```

Kết quả được lưu tại:

```text
data\usage.json
```

## Quan trọng

Không chia sẻ:

```text
codex_profiles/
```

Nó có authentication state của 4 account.

Không upload thư mục đó lên GitHub/Drive.

## Khi đủ 4 account

Khi `collect_all.py` đọc đủ 4 account thành công, chuyển sang Phase 3:

1. tạo dashboard PNG
2. Slack App / token
3. upload ảnh vào channel
4. Windows Task Scheduler theo 8 mốc giờ đã chốt

## Phase 3: dashboard PNG + Slack + lịch Windows

### Render dashboard PNG

Chạy:

```powershell
python render_dashboard.py
```

Kết quả:

```text
data\dashboard.png
```

### Chạy một lần: collect + render + Slack

Test không gửi Slack:

```powershell
python run_report_once.py --skip-slack
```

Gửi Slack thật cần biến môi trường:

```powershell
setx SLACK_BOT_TOKEN "xoxb-..."
setx SLACK_CHANNEL_ID "C0123456789"
```

Nếu có tài khoản bị logout hoặc lỗi không lấy được data, script sẽ gửi cảnh báo
trực tiếp vào Slack bằng tiếng Việt và tag `@TuanAnh`. Để tag chắc chắn theo
Slack user ID, có thể cấu hình thêm:

```powershell
setx SLACK_ALERT_MENTION "<@U0123456789>"
```

Với lỗi tạm thời từ ChatGPT như `503 Service Unavailable`, script sẽ tự thử lại
3 lần trước khi báo Slack và message sẽ ghi rõ đây là lỗi hệ thống/API, không
phải lỗi logout.

Mở terminal mới sau khi `setx`, rồi chạy:

```powershell
python run_report_once.py
```

Slack App cần quyền tối thiểu:

```text
files:write
chat:write
channels:join
```

Script dùng Slack Web API upload flow mới:

```text
files.getUploadURLExternal
files.completeUploadExternal
```

### Cài lịch Windows Task Scheduler

Double-click:

```text
install_task_scheduler.cmd
```

Lịch được tạo cho Thứ 2 đến Thứ 6:

```text
09:00
10:00
11:00
13:00
14:00
15:00
16:00
17:00
```

Task chạy nền qua:

```text
run_report_once_scheduled.cmd
```

Log:

```text
data\scheduled.log
```

Gỡ lịch:

```text
uninstall_task_scheduler.cmd
```
