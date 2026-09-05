from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_IMAGE_PATH = ROOT / "data" / "dashboard.png"
DEFAULT_USAGE_PATH = ROOT / "data" / "usage.json"
DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_ALERT_MENTION = "@TuanAnh"


class SlackError(RuntimeError):
    pass


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_dotenv(path: Path = DEFAULT_ENV_PATH) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def slack_api(method: str, token: str, fields: dict[str, Any]) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SlackError(f"Slack HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SlackError(f"Slack network error: {exc}") from exc

    if not payload.get("ok"):
        raise SlackError(f"Slack API {method} failed: {payload.get('error') or payload}")
    return payload


def post_message(token: str, channel_id: str, text: str) -> dict[str, Any]:
    return slack_api(
        "chat.postMessage",
        token,
        {
            "channel": channel_id,
            "text": text,
            "mrkdwn": "true",
            "link_names": "1",
        },
    )


def _truncate(text: str, max_length: int = 500) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _is_service_error(item: dict[str, Any]) -> bool:
    if item.get("error_type") == "transient_service_error":
        return True

    text = str(item.get("error") or "").lower()
    markers = (
        "503 service unavailable",
        "502 bad gateway",
        "504 gateway timeout",
        "500 internal server error",
        "429 too many requests",
        "upstream connect error",
        "reset reason: overflow",
        "timeout",
    )
    return any(marker in text for marker in markers)


def _is_login_error(item: dict[str, Any]) -> bool:
    if item.get("error_type") == "account_auth_error":
        return True

    text = str(item.get("error") or "").lower()
    markers = (
        "không tìm thấy chatgpt account",
        "profile chưa tồn tại",
        "auth type",
        "login",
        "logged",
        "unauthorized",
        "401",
        "403",
    )
    return any(marker in text for marker in markers)


def _account_line(item: dict[str, Any]) -> str:
    label = item.get("label") or item.get("id") or "Không rõ"
    account_id = item.get("id") or "N/A"
    attempts = item.get("attempts")
    suffix = f" sau {attempts} lần thử" if attempts else ""
    return f"- {label} ({account_id}){suffix}"


def format_usage_error_alert(
    errors: list[dict[str, Any]],
    collected_at_vn: str | None,
    mention: str = DEFAULT_ALERT_MENTION,
) -> str:
    lines = [
        f"{mention} Cảnh báo: ChatGPT Usage Monitor chưa lấy được dữ liệu.",
    ]
    if collected_at_vn:
        lines.append(f"Thời gian ghi nhận: {collected_at_vn} (giờ Việt Nam).")

    service_errors = [item for item in errors if _is_service_error(item)]
    login_errors = [
        item
        for item in errors
        if item not in service_errors and _is_login_error(item)
    ]
    other_errors = [
        item
        for item in errors
        if item not in service_errors and item not in login_errors
    ]

    if service_errors:
        lines.extend(
            [
                "",
                "Nhóm lỗi hệ thống/API ChatGPT:",
                (
                    "Khả năng cao backend ChatGPT đang tạm thời quá tải "
                    "hoặc trả lỗi 503; chưa cần đăng nhập lại ngay."
                ),
            ]
        )
        lines.extend(_account_line(item) for item in service_errors)

    if login_errors:
        lines.extend(["", "Nhóm cần kiểm tra đăng nhập:"])
        lines.extend(_account_line(item) for item in login_errors)

    if other_errors:
        lines.extend(["", "Nhóm lỗi khác:"])
        for item in other_errors:
            detail = _truncate(str(item.get("error") or "Không rõ lỗi"), 220)
            lines.append(f"{_account_line(item)}: {detail}")

    if login_errors:
        lines.append("")
        lines.append(
            "Hành động đề xuất: đăng nhập lại các tài khoản trong nhóm cần kiểm tra."
        )

    if service_errors:
        lines.append("")
        lines.append(
            "Hành động đề xuất: chờ lần chạy kế tiếp hoặc chạy lại sau vài phút."
        )
    return "\n".join(lines)


def send_usage_error_alert(
    usage_path: Path = DEFAULT_USAGE_PATH,
    token: str | None = None,
    channel_id: str | None = None,
    mention: str | None = None,
) -> bool:
    load_dotenv()
    payload = json.loads(usage_path.read_text(encoding="utf-8"))
    errors = [
        item
        for item in payload.get("accounts", [])
        if item.get("status") == "error"
    ]
    if not errors:
        return False

    token = token or os.environ.get("SLACK_BOT_TOKEN")
    channel_id = channel_id or os.environ.get("SLACK_CHANNEL_ID")
    mention = (
        mention
        or os.environ.get("SLACK_ALERT_MENTION")
        or DEFAULT_ALERT_MENTION
    )

    if not token or not channel_id:
        raise SlackError(
            "Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID before sending Slack alert."
        )

    text = format_usage_error_alert(
        errors,
        payload.get("collected_at_vn"),
        mention,
    )
    post_message(token, channel_id, text)
    return True


def upload_bytes(upload_url: str, image_bytes: bytes) -> None:
    request = urllib.request.Request(
        upload_url,
        data=image_bytes,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status < 200 or response.status >= 300:
                raise SlackError(f"Slack upload returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SlackError(f"Slack upload HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SlackError(f"Slack upload network error: {exc}") from exc


def upload_image(
    image_path: Path,
    token: str,
    channel_id: str,
    initial_comment: str,
) -> dict[str, Any]:
    image_bytes = image_path.read_bytes()
    filename = image_path.name

    start = slack_api(
        "files.getUploadURLExternal",
        token,
        {
            "filename": filename,
            "length": str(len(image_bytes)),
        },
    )

    upload_url = start.get("upload_url")
    file_id = start.get("file_id")
    if not upload_url or not file_id:
        raise SlackError("Slack did not return upload_url/file_id.")

    upload_bytes(upload_url, image_bytes)

    return slack_api(
        "files.completeUploadExternal",
        token,
        {
            "files": json.dumps([{"id": file_id, "title": "ChatGPT Usage Dashboard"}]),
            "channel_id": channel_id,
            "initial_comment": initial_comment,
        },
    )


def main() -> int:
    configure_console()
    load_dotenv()
    parser = argparse.ArgumentParser(description="Upload dashboard PNG to Slack.")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE_PATH))
    parser.add_argument("--comment", default="ChatGPT usage dashboard")
    parser.add_argument("--token", default=os.environ.get("SLACK_BOT_TOKEN"))
    parser.add_argument("--channel", default=os.environ.get("SLACK_CHANNEL_ID"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"ERROR: Image not found: {image_path}")
        return 1

    if args.dry_run:
        print(f"Dry run OK. Would upload: {image_path}")
        return 0

    if not args.token or not args.channel:
        print("ERROR: Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID before sending Slack.")
        return 2

    result = upload_image(image_path, args.token, args.channel, args.comment)
    files = result.get("files") or []
    print(f"Uploaded dashboard to Slack. Files: {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
