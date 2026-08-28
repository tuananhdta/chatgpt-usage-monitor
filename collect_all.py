from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_client import collect_profile

VN_TZ = timezone(timedelta(hours=7), name="ICT")


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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
            usage = collect_profile(profile_dir)
            five = usage.get("five_hour") or {}
            weekly = usage.get("weekly") or {}

            result = {
                "id": account_id,
                "label": label,
                "status": "ok",
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
