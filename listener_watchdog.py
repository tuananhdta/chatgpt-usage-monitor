from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parent
DEFAULT_LISTENER = ROOT / "slack_listener.py"
DEFAULT_LOG_PATH = ROOT / "data" / "slack_listener.log"
DEFAULT_RESTART_DELAY = 15
LOGGER = logging.getLogger("chatgpt_usage_monitor.listener_watchdog")


def configure_logging(log_path: Path = DEFAULT_LOG_PATH) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def listener_command(
    python_executable: str | None = None,
    listener_path: Path = DEFAULT_LISTENER,
) -> list[str]:
    return [python_executable or sys.executable, str(listener_path)]


def run_watchdog(
    *,
    command: Sequence[str] | None = None,
    restart_delay: int = DEFAULT_RESTART_DELAY,
    once: bool = False,
    process_runner: Callable[[Sequence[str]], int] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Keep the listener alive and stop permanently on config errors.

    Exit code 2 is reserved by ``slack_listener.py`` for missing configuration;
    restarting in that case would create an endless log/process loop.
    """
    resolved_command = list(command or listener_command())
    delay = max(1, int(restart_delay))

    def run_process() -> int:
        if process_runner is not None:
            return int(process_runner(resolved_command))
        return int(subprocess.call(resolved_command, cwd=str(ROOT)))

    while True:
        LOGGER.info("Starting Slack listener watchdog child process")
        try:
            exit_code = run_process()
        except KeyboardInterrupt:
            LOGGER.info("Slack listener watchdog stopped")
            return 0

        if once or exit_code == 2:
            if exit_code == 2:
                LOGGER.error(
                    "Listener stopped because required configuration is missing; "
                    "not restarting."
                )
            else:
                LOGGER.info("Listener watchdog completed one run")
            return exit_code

        LOGGER.warning(
            "Listener exited with code %s; restarting in %ss",
            exit_code,
            delay,
        )
        try:
            sleep(delay)
        except KeyboardInterrupt:
            LOGGER.info("Slack listener watchdog stopped during restart delay")
            return 0


def run_listener_in_process(
    *,
    restart_delay: int = DEFAULT_RESTART_DELAY,
    once: bool = False,
) -> int:
    """Run the listener in this process so Task Scheduler stops it cleanly."""
    import slack_listener

    delay = max(1, int(restart_delay))
    while True:
        LOGGER.info("Starting Slack listener in watchdog process")
        try:
            exit_code = int(slack_listener.main())
        except KeyboardInterrupt:
            LOGGER.info("Slack listener watchdog stopped")
            return 0
        except Exception:
            LOGGER.exception("Slack listener crashed; it will be restarted")
            exit_code = 1

        if once or exit_code in {0, 2}:
            if exit_code == 2:
                LOGGER.error(
                    "Listener stopped because required configuration is missing; "
                    "not restarting."
                )
            return exit_code

        LOGGER.warning(
            "Slack listener exited with code %s; restarting in %ss",
            exit_code,
            delay,
        )
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            LOGGER.info("Slack listener watchdog stopped during restart delay")
            return 0


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Keep the Slack Socket Mode listener running."
    )
    parser.add_argument("--delay", type=int, default=DEFAULT_RESTART_DELAY)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--python", dest="python_executable")
    parser.add_argument("--listener", default=str(DEFAULT_LISTENER))
    args = parser.parse_args()
    return run_listener_in_process(
        restart_delay=args.delay,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
