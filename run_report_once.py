from __future__ import annotations

import argparse
import sys

import refresh_pipeline


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(
        description="Collect usage, render dashboard PNG, and optionally send Slack."
    )
    parser.add_argument("--skip-slack", action="store_true")
    parser.add_argument(
        "--source",
        choices=sorted(refresh_pipeline.VALID_SOURCES),
        default="manual",
    )
    parser.add_argument("--requested-by", default="Command line")
    args = parser.parse_args()

    result = refresh_pipeline.refresh_usage(
        args.source,
        args.requested_by,
        publish_slack=not args.skip_slack,
    )
    print(f"Ảnh bảng giám sát: {result.dashboard_path}")
    if args.skip_slack:
        print("Slack skipped by --skip-slack.")
    elif result.upload_response is not None:
        print("Đã gửi bảng giám sát lên kênh Slack dưới dạng tin nhắn chính.")
    if result.alert_sent:
        print("Sent Slack alert for accounts with data collection errors.")
    if result.alert_error:
        print(f"WARNING: Slack error alert failed: {result.alert_error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
