from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

VN_TZ = timezone(timedelta(hours=7), name="ICT")


class CodexError(RuntimeError):
    pass


def find_codex() -> str:
    exe = shutil.which("codex")
    if not exe:
        raise CodexError(
            "Không tìm thấy lệnh 'codex' trong PATH. "
            "Hãy mở terminal mới và kiểm tra: codex --version"
        )
    return exe


def _send(proc: subprocess.Popen, payload: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    proc.stdin.flush()


def _start_stdout_reader(proc: subprocess.Popen) -> queue.Queue[str]:
    assert proc.stdout is not None
    lines: queue.Queue[str] = queue.Queue()

    def read_stdout() -> None:
        for line in proc.stdout:
            lines.put(line)

    thread = threading.Thread(target=read_stdout, daemon=True)
    thread.start()
    return lines


def _read_response(
    proc: subprocess.Popen,
    lines: queue.Queue[str],
    request_id: int,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        try:
            line = lines.get(
                timeout=max(0.05, min(0.25, deadline - time.monotonic()))
            )
        except queue.Empty:
            if proc.poll() is not None:
                raise CodexError(
                    f"codex app-server thoát sớm với code {proc.returncode}"
                )
            continue

        line = line.strip()
        if not line:
            continue

        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        if message.get("id") == request_id:
            if "error" in message:
                raise CodexError(
                    f"App Server error: "
                    f"{json.dumps(message['error'], ensure_ascii=False)}"
                )
            return message

    raise CodexError(
        f"Hết thời gian chờ App Server response id={request_id}"
    )


def _format_reset(ts: Any) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(
        int(ts), tz=VN_TZ
    ).strftime("%d/%m/%Y %H:%M:%S")


def _remaining(used: Any) -> int | None:
    if used is None:
        return None
    try:
        return max(0, min(100, 100 - int(used)))
    except (TypeError, ValueError):
        return None


def _normalize_window(window: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(window, dict):
        return None

    used = window.get("usedPercent")
    ts = window.get("resetsAt")

    return {
        "used_percent": used,
        "remaining_percent": _remaining(used),
        "window_duration_mins": window.get("windowDurationMins"),
        "reset_at": ts,
        "reset_time_vn": _format_reset(ts),
    }


def collect_profile(profile_dir: Path) -> dict[str, Any]:
    codex = find_codex()
    profile_dir = profile_dir.resolve()

    if not profile_dir.exists():
        raise CodexError(f"Profile chưa tồn tại: {profile_dir}")

    env = os.environ.copy()
    env["CODEX_HOME"] = str(profile_dir)

    proc = subprocess.Popen(
        [codex, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=env,
        creationflags=(
            subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        ),
    )

    try:
        lines = _start_stdout_reader(proc)

        _send(
            proc,
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "chatgpt-usage-monitor",
                        "title": "ChatGPT Usage Monitor",
                        "version": "0.3.0",
                    },
                    "capabilities": {
                        "experimentalApi": False,
                        "optOutNotificationMethods": [],
                    },
                },
            },
        )
        _read_response(proc, lines, 1)
        _send(proc, {"method": "initialized"})

        _send(
            proc,
            {
                "id": 2,
                "method": "account/read",
                "params": {"refreshToken": True},
            },
        )
        account_response = _read_response(proc, lines, 2)
        account_result = account_response.get("result") or {}
        account = account_result.get("account")

        if not isinstance(account, dict):
            raise CodexError(
                "Không tìm thấy ChatGPT account đã login trong CODEX_HOME này."
            )

        if account.get("type") != "chatgpt":
            raise CodexError(
                f"Auth type không phải ChatGPT: {account.get('type')}"
            )

        _send(
            proc,
            {
                "id": 3,
                "method": "account/rateLimits/read",
            },
        )
        rate_response = _read_response(proc, lines, 3)
        rate_result = rate_response.get("result") or {}
        rate_limits = rate_result.get("rateLimits") or {}

        primary = _normalize_window(rate_limits.get("primary"))
        secondary = _normalize_window(rate_limits.get("secondary"))

        five_hour = None
        weekly = None

        for window in (primary, secondary):
            if not window:
                continue
            duration = window.get("window_duration_mins")
            if duration == 300:
                five_hour = window
            elif duration == 10080:
                weekly = window

        # Fallback nếu payload thay đổi nhẹ.
        if five_hour is None:
            five_hour = primary
        if weekly is None:
            weekly = secondary

        return {
            "email": account.get("email"),
            "plan_type": (
                account.get("planType")
                or rate_limits.get("planType")
            ),
            "five_hour": five_hour,
            "weekly": weekly,
            "rate_limit_reached_type": rate_limits.get(
                "rateLimitReachedType"
            ),
            "credits": rate_limits.get("credits"),
            "rate_limit_reset_credits": rate_result.get(
                "rateLimitResetCredits"
            ),
        }

    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
