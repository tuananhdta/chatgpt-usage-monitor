from __future__ import annotations

import json
import os
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import collect_all
import render_dashboard
import slack_notify


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DEFAULT_STATE_PATH = DATA_DIR / "refresh_state.json"
DEFAULT_LOCK_PATH = DATA_DIR / "refresh.lock"
DEFAULT_COOLDOWN_SECONDS = 45
VN_TZ = timezone(timedelta(hours=7), name="ICT")
VALID_SOURCES = {"automation", "manual"}


class RefreshError(RuntimeError):
    """Base exception for refresh orchestration failures."""


class RefreshBusyError(RefreshError):
    """Raised when another refresh owns the cross-process lock."""


class RefreshCooldownError(RefreshError):
    """Raised when the cooldown has not elapsed yet."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(
            f"Đang trong thời gian chờ làm mới. Vui lòng thử lại sau {self.retry_after} giây."
        )


@dataclass(frozen=True)
class RefreshResult:
    source: str
    requested_by: str
    requested_at_vn: str
    usage_path: Path
    dashboard_path: Path
    account_errors: tuple[dict[str, Any], ...]
    alert_sent: bool
    alert_error: str | None
    upload_response: dict[str, Any] | None


class RefreshLock(AbstractContextManager["RefreshLock"]):
    """A small cross-process lock that works on Windows and POSIX hosts."""

    def __init__(self, path: Path = DEFAULT_LOCK_PATH) -> None:
        self.path = path
        self._handle: Any = None

    def __enter__(self) -> "RefreshLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+b")
        try:
            if self._handle.tell() == 0:
                self._handle.write(b"0")
                self._handle.flush()
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            self._handle.close()
            self._handle = None
            raise RefreshBusyError("Đang có một lần làm mới khác.") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def cooldown_seconds() -> int:
    raw = os.environ.get(
        "SLACK_REFRESH_COOLDOWN_SECONDS",
        str(DEFAULT_COOLDOWN_SECONDS),
    )
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_COOLDOWN_SECONDS


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _requested_times() -> tuple[float, str, str]:
    now = datetime.now(timezone.utc)
    now_vn = now.astimezone(VN_TZ)
    return (
        now.timestamp(),
        now.isoformat(timespec="seconds"),
        now_vn.strftime("%d/%m/%Y %H:%M:%S"),
    )


def _check_cooldown(state: dict[str, Any], now: float) -> None:
    last_started = state.get("last_started_at_epoch")
    try:
        elapsed = now - float(last_started)
    except (TypeError, ValueError):
        return
    remaining = cooldown_seconds() - int(elapsed)
    if remaining > 0:
        raise RefreshCooldownError(remaining)


def refresh_usage(
    source: str,
    requested_by: str,
    *,
    usage_path: Path = collect_all.DEFAULT_OUTPUT_PATH,
    dashboard_path: Path = render_dashboard.DEFAULT_OUTPUT_PATH,
    state_path: Path = DEFAULT_STATE_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
    publish_slack: bool = True,
) -> RefreshResult:
    """Run collect -> render -> optional Slack publication as one job."""
    if source not in VALID_SOURCES:
        raise ValueError(f"Nguồn làm mới không được hỗ trợ: {source}")

    slack_notify.load_dotenv()
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_CHANNEL_ID")
    if publish_slack and (not token or not channel_id):
        raise slack_notify.SlackError(
            "Hãy đặt SLACK_BOT_TOKEN và SLACK_CHANNEL_ID trước khi gửi lên Slack."
        )

    requested_epoch, requested_at, requested_at_vn = _requested_times()
    metadata: dict[str, object] = {
        "source": source,
        "requested_by": requested_by or "Không rõ",
        "requested_at": requested_at,
        "requested_at_vn": requested_at_vn,
    }

    with RefreshLock(lock_path):
        state = _read_state(state_path)
        _check_cooldown(state, requested_epoch)
        state.update(
            {
                "status": "running",
                "source": source,
                "requested_by": requested_by or "Không rõ",
                "requested_at": requested_at,
                "last_started_at_epoch": requested_epoch,
            }
        )
        _write_state(state_path, state)

        try:
            payload = collect_all.collect_all(
                output_path=usage_path,
                metadata=metadata,
            )
            rendered_path = render_dashboard.render_dashboard(
                usage_path,
                dashboard_path,
            )

            errors = tuple(
                item
                for item in payload.get("accounts", [])
                if item.get("status") == "error"
            )
            alert_sent = False
            alert_error: str | None = None
            upload_response: dict[str, Any] | None = None

            if publish_slack:
                try:
                    alert_sent = slack_notify.send_usage_error_alert(
                        usage_path=usage_path,
                        token=token,
                        channel_id=channel_id,
                    )
                except Exception as exc:
                    # An alert failure must not prevent a fresh dashboard from
                    # being uploaded. The account errors remain in its caption.
                    alert_error = str(exc)
                    print(f"CẢNH BÁO: Không thể gửi cảnh báo lỗi tài khoản: {exc}")

                caption = slack_notify.format_dashboard_caption(
                    source,
                    requested_by,
                    requested_at_vn,
                    list(errors),
                )
                upload_response = slack_notify.upload_image(
                    rendered_path,
                    token,
                    channel_id,
                    caption,
                )

            completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            state.update(
                {
                    "status": "success",
                    "last_finished_at": completed_at,
                    "last_success_at": completed_at,
                    "last_error": None,
                }
            )
            _write_state(state_path, state)
            return RefreshResult(
                source=source,
                requested_by=requested_by,
                requested_at_vn=requested_at_vn,
                usage_path=usage_path,
                dashboard_path=rendered_path,
                account_errors=errors,
                alert_sent=alert_sent,
                alert_error=alert_error,
                upload_response=upload_response,
            )
        except Exception as exc:
            state.update(
                {
                    "status": "error",
                    "last_finished_at": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "last_error": str(exc),
                }
            )
            _write_state(state_path, state)
            raise


def main() -> int:
    """Small CLI used by scheduled jobs and local manual verification."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect usage, render dashboard, and publish to Slack."
    )
    parser.add_argument("--source", choices=sorted(VALID_SOURCES), default="manual")
    parser.add_argument("--requested-by", default="Dòng lệnh")
    parser.add_argument("--skip-slack", action="store_true")
    args = parser.parse_args()
    result = refresh_usage(
        args.source,
        args.requested_by,
        publish_slack=not args.skip_slack,
    )
    print(f"Ảnh bảng giám sát: {result.dashboard_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
