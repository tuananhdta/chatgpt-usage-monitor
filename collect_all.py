from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_client import collect_profile

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "accounts.json"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "usage.json"
VN_TZ = timezone(timedelta(hours=7), name="ICT")
COLLECT_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (15, 30)


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def is_transient_error(error: Exception) -> bool:
    text = str(error).lower()
    markers = (
        "503 service unavailable",
        "502 bad gateway",
        "504 gateway timeout",
        "500 internal server error",
        "429 too many requests",
        "upstream connect error",
        "reset reason: overflow",
        "hết thời gian chờ",
        "timeout",
        "network error",
    )
    return any(marker in text for marker in markers)


def is_environment_error(error: Exception) -> bool:
    text = str(error).lower()
    markers = (
        "không tìm thấy lệnh 'codex'",
        "codex.exe",
        "no such file or directory: codex",
    )
    return any(marker in text for marker in markers)


def collect_profile_with_retry(profile_dir: Path) -> tuple[dict[str, object], int]:
    last_error: Exception | None = None

    for attempt in range(1, COLLECT_ATTEMPTS + 1):
        try:
            return collect_profile(profile_dir), attempt
        except Exception as exc:
            last_error = exc
            if attempt >= COLLECT_ATTEMPTS or not is_transient_error(exc):
                raise

            delay = RETRY_DELAYS_SECONDS[min(attempt - 1, len(RETRY_DELAYS_SECONDS) - 1)]
            print(
                f"  Lỗi tạm thời, thử lại lần {attempt + 1}/"
                f"{COLLECT_ATTEMPTS} sau {delay}s: {exc}"
            )
            time.sleep(delay)

    assert last_error is not None
    raise last_error


def collect_all(
    config_path: Path = DEFAULT_CONFIG_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Collect every configured account and save one complete usage payload.

    Account-level failures are represented in the payload so rendering and
    Slack publishing can still proceed with the accounts that did succeed.
    """
    configure_console()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    root = config_path.parent

    results = []

    print("=" * 80)
    print("THU THẬP DỮ LIỆU SỬ DỤNG CHATGPT - 4 TÀI KHOẢN")
    print("=" * 80)

    for item in config["accounts"]:
        account_id = item["id"]
        label = item["label"]
        profile_dir = root / "codex_profiles" / account_id

        print()
        print(f"[{label}]")

        try:
            usage, attempts = collect_profile_with_retry(profile_dir)
            five = usage.get("five_hour") or {}
            weekly = usage.get("weekly") or {}

            result = {
                "id": account_id,
                "label": label,
                "status": "ok",
                "attempts": attempts,
                **usage,
            }

            print(f"  Email:   {usage.get('email') or 'Không có'}")
            print(
                f"  5 giờ:   còn {five.get('remaining_percent')}%"
                f" | đặt lại {five.get('reset_time_vn')}"
            )
            print(
                f"  Hàng tuần: còn {weekly.get('remaining_percent')}%"
                f" | đặt lại {weekly.get('reset_time_vn')}"
            )

        except Exception as exc:
            result = {
                "id": account_id,
                "label": label,
                "status": "error",
                "error": str(exc),
                "error_type": (
                    "transient_service_error"
                    if is_transient_error(exc)
                    else "environment_error"
                    if is_environment_error(exc)
                    else "account_auth_error"
                ),
                "attempts": COLLECT_ATTEMPTS if is_transient_error(exc) else 1,
            }
            print(f"  LỖI: {exc}")

        results.append(result)

    payload = {
        "collected_at_vn": datetime.now(VN_TZ).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
        "accounts": results,
    }

    if metadata:
        payload.update(metadata)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print(f"Đã lưu: {output_path}")
    print("=" * 80)
    return payload


def main() -> None:
    configure_console()
    collect_all()


if __name__ == "__main__":
    main()
