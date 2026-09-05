from __future__ import annotations

import argparse
import sys

import collect_all
import render_dashboard
import slack_notify


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
    args = parser.parse_args()

    collect_all.main()
    dashboard = render_dashboard.render_dashboard()
    print(f"Dashboard PNG: {dashboard}")

    if args.skip_slack:
        print("Slack skipped by --skip-slack.")
        return 0

    alert_sent = slack_notify.send_usage_error_alert()
    if alert_sent:
        print("Sent Slack alert for accounts with data collection errors.")

    return slack_notify.main()


if __name__ == "__main__":
    raise SystemExit(main())
