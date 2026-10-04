from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import slack_notify


ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = ROOT / "data" / "control_panel.json"
CONTROL_PANEL_TEXT = "Điều khiển giám sát mức sử dụng ChatGPT"
REFRESH_ACTION_ID = "refresh_usage"
BOOKMARK_TITLE = "Manual refresh"
BOOKMARK_EMOJI = ":arrows_counterclockwise:"


def control_panel_blocks(*, running: bool = False) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": CONTROL_PANEL_TEXT},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Bấm *Làm mới* để lấy dữ liệu mới cho cả 4 tài khoản.",
            },
        },
    ]
    if running:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⏳ *Đang làm mới…* Vui lòng chờ bảng dữ liệu mới trong kênh.",
                },
            }
        )
    else:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "action_id": REFRESH_ACTION_ID,
                        "value": "manual",
                        "text": {"type": "plain_text", "text": "Làm mới"},
                        "style": "primary",
                    }
                ],
            }
        )
    return blocks


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _credentials(
    token: str | None,
    channel_id: str | None,
) -> tuple[str, str]:
    slack_notify.load_dotenv()
    resolved_token = token or os.environ.get("SLACK_BOT_TOKEN")
    resolved_channel = channel_id or os.environ.get("SLACK_CHANNEL_ID")
    if not resolved_token or not resolved_channel:
        raise slack_notify.SlackError(
            "Hãy đặt SLACK_BOT_TOKEN và SLACK_CHANNEL_ID trước khi tạo bảng điều khiển."
        )
    return resolved_token, resolved_channel


def publish_control_panel(
    *,
    token: str | None = None,
    channel_id: str | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
    update_existing: bool = False,
) -> dict[str, Any]:
    """Create the panel, or update the saved panel message when requested."""
    resolved_token, resolved_channel = _credentials(token, channel_id)
    blocks = control_panel_blocks()
    state = _read_state(state_path)
    existing_ts = state.get("message_ts")

    if update_existing:
        if not existing_ts:
            raise slack_notify.SlackError(
                f"Không tìm thấy thời điểm bảng điều khiển đã lưu tại {state_path}."
            )
        result = slack_notify.slack_api(
            "chat.update",
            resolved_token,
            {
                "channel": resolved_channel,
                "ts": existing_ts,
                "text": CONTROL_PANEL_TEXT,
                "blocks": json.dumps(blocks, ensure_ascii=False),
            },
        )
        message_ts = existing_ts
    else:
        result = slack_notify.post_blocks(
            resolved_token,
            resolved_channel,
            CONTROL_PANEL_TEXT,
            blocks,
        )
        message = result.get("message") or {}
        message_ts = result.get("ts") or message.get("ts")
        if not message_ts:
            raise slack_notify.SlackError(
                "Slack không trả về thời điểm của tin nhắn bảng điều khiển."
            )

    state.update(
        {
            "channel_id": resolved_channel,
            "message_ts": message_ts,
            "action_id": REFRESH_ACTION_ID,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    _write_state(state_path, state)
    return result


def sync_refresh_bookmark(
    *,
    token: str | None = None,
    channel_id: str | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    """Add or update the channel-header bookmark for the saved Control Panel."""
    resolved_token, resolved_channel = _credentials(token, channel_id)
    state = _read_state(state_path)
    message_ts = state.get("message_ts")
    if not message_ts:
        raise slack_notify.SlackError(
            f"Không tìm thấy thời điểm bảng điều khiển đã lưu tại {state_path}. "
            "Hãy tạo bảng điều khiển trước khi thêm bookmark."
        )

    permalink_response = slack_notify.slack_api(
        "chat.getPermalink",
        resolved_token,
        {"channel": resolved_channel, "message_ts": message_ts},
    )
    permalink = permalink_response.get("permalink")
    if not permalink:
        raise slack_notify.SlackError(
            "Slack không trả về liên kết cố định cho tin nhắn bảng điều khiển."
        )

    bookmark_fields: dict[str, Any] = {
        "channel_id": resolved_channel,
        "title": BOOKMARK_TITLE,
        "type": "link",
        "link": permalink,
        "emoji": BOOKMARK_EMOJI,
    }
    bookmark_id = state.get("bookmark_id")
    if bookmark_id:
        method = "bookmarks.edit"
        bookmark_fields["bookmark_id"] = bookmark_id
    else:
        method = "bookmarks.add"

    result = slack_notify.slack_api(method, resolved_token, bookmark_fields)
    bookmark = result.get("bookmark") or {}
    saved_bookmark_id = bookmark.get("id") or bookmark_id
    if not saved_bookmark_id:
        raise slack_notify.SlackError(
            "Slack không trả về mã bookmark; không lưu trạng thái chưa đầy đủ."
        )

    state.update(
        {
            "channel_id": resolved_channel,
            "bookmark_id": saved_bookmark_id,
            "bookmark_title": BOOKMARK_TITLE,
            "bookmark_link": permalink,
            "bookmark_updated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }
    )
    _write_state(state_path, state)
    return result


def main() -> int:
    slack_notify.configure_console()
    parser = argparse.ArgumentParser(
        description="Create or update the Slack Usage Monitor control panel."
    )
    parser.add_argument("--update", action="store_true")
    parser.add_argument(
        "--bookmark",
        action="store_true",
        help="Add or update the channel-header bookmark for the saved Control Panel.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    args = parser.parse_args()

    if args.dry_run:
        if args.bookmark:
            print(
                json.dumps(
                    {
                        "title": BOOKMARK_TITLE,
                        "type": "link",
                        "emoji": BOOKMARK_EMOJI,
                        "source": "saved Control Panel permalink",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(json.dumps(control_panel_blocks(), ensure_ascii=False, indent=2))
        return 0

    if args.bookmark:
        try:
            result = sync_refresh_bookmark(state_path=Path(args.state))
            print("Đã đồng bộ bookmark bảng điều khiển lên Slack.")
            print(f"Phản hồi Slack thành công: {result.get('ok', False)}")
            return 0
        except slack_notify.SlackError as exc:
            print(f"LỖI: {exc}")
            return 1

    try:
        result = publish_control_panel(
            state_path=Path(args.state),
            update_existing=args.update,
        )
    except slack_notify.SlackError as exc:
        print(f"LỖI: {exc}")
        return 1
    print(
        f"Đã {'cập nhật' if args.update else 'tạo'} bảng điều khiển trên Slack."
    )
    print(f"Phản hồi Slack thành công: {result.get('ok', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
