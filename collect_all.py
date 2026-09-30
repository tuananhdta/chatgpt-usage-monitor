from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_client import collect_profile

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


def main() -> None:
    configure_console()

    root = Path(__file__).resolve().parent
    config = json.loads(
        (root / "accounts.json").read_text(encoding="utf-8")
    )

    results = []

    print("=" * 80)
    print("COLLECT CHATGPT USAGE - 4 ACCOUNTS")
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

            print(f"  Email:   {usage.get('email') or 'N/A'}")
            print(
                f"  5h:      {five.get('remaining_percent')}% remaining"
                f" | reset {five.get('reset_time_vn')}"
            )
            print(
                f"  Weekly:  {weekly.get('remaining_percent')}% remaining"
                f" | reset {weekly.get('reset_time_vn')}"
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
            print(f"  ERROR: {exc}")

        results.append(result)

    payload = {
        "collected_at_vn": datetime.now(VN_TZ).strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
        "accounts": results,
    }

    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)

    output = data_dir / "usage.json"
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print(f"Saved: {output}")
    print("=" * 80)


if __name__ == "__main__":
    main()
