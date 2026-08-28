from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from codex_client import CodexError, collect_profile, find_codex


VALID_ACCOUNTS = ("acc01", "acc02", "acc03", "acc04")


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def print_usage(account_id: str, data: dict) -> None:
    five = data.get("five_hour") or {}
    weekly = data.get("weekly") or {}

    print()
    print("=" * 68)
    print(f"Profile:   {account_id}")
    print(f"Email:     {data.get('email') or 'N/A'}")
    print(f"Plan:      {data.get('plan_type') or 'N/A'}")
    print()
    print("5 HR LIMIT")
    print(f"  Used:      {five.get('used_percent')}%")
    print(f"  Remaining: {five.get('remaining_percent')}%")
    print(f"  Reset VN:  {five.get('reset_time_vn')}")
    print()
    print("WEEKLY LIMIT")
    print(f"  Used:      {weekly.get('used_percent')}%")
    print(f"  Remaining: {weekly.get('remaining_percent')}%")
    print(f"  Reset VN:  {weekly.get('reset_time_vn')}")
    print("=" * 68)


def main() -> int:
    configure_console()

    parser = argparse.ArgumentParser(
        description="Login một ChatGPT Plus account vào CODEX_HOME riêng."
    )
    parser.add_argument(
        "--account",
        required=True,
        choices=VALID_ACCOUNTS,
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    profile_dir = (root / "codex_profiles" / args.account).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    # Ép auth được lưu trong chính CODEX_HOME này thay vì credential store dùng chung.
    config_file = profile_dir / "config.toml"
    config_file.write_text(
        'cli_auth_credentials_store = "file"\n',
        encoding="utf-8",
    )

    codex = find_codex()
    env = os.environ.copy()
    env["CODEX_HOME"] = str(profile_dir)

    print("=" * 68)
    print(f"SETUP {args.account}")
    print(f"CODEX_HOME: {profile_dir}")
    print("=" * 68)
    print()
    print("Codex sẽ mở luồng login.")
    print("Hãy đăng nhập ĐÚNG ChatGPT Plus account tương ứng.")
    print("Không paste password/token/cookie vào terminal.")
    print()

    result = subprocess.run(
        [codex, "login"],
        env=env,
    )

    if result.returncode != 0:
        print(f"\nERROR: codex login trả code {result.returncode}")
        return result.returncode

    print()
    print("Kiểm tra login status...")
    subprocess.run(
        [codex, "login", "status"],
        env=env,
        check=False,
    )

    print()
    print("Đọc rate limits để verify account...")
    try:
        data = collect_profile(profile_dir)
    except CodexError as exc:
        print(f"\nERROR: {exc}")
        return 1

    print_usage(args.account, data)

    print()
    print("Nếu Email/Plan ở trên đúng account, setup đã hoàn tất.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
