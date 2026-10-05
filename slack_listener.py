from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

import refresh_pipeline
import slack_control_panel
import slack_notify


ROOT = Path(__file__).resolve().parent
DEFAULT_LOG_PATH = ROOT / "data" / "slack_listener.log"
LOGGER = logging.getLogger("chatgpt_usage_monitor.slack_listener")


class ListenerConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ListenerConfig:
    app_token: str
    bot_token: str
    channel_id: str
    team_id: str
    allowed_user_ids: frozenset[str]

    @classmethod
    def from_env(cls) -> "ListenerConfig":
        slack_notify.load_dotenv()
        required = {
            "SLACK_APP_TOKEN": os.environ.get("SLACK_APP_TOKEN"),
            "SLACK_BOT_TOKEN": os.environ.get("SLACK_BOT_TOKEN"),
            "SLACK_CHANNEL_ID": os.environ.get("SLACK_CHANNEL_ID"),
            "SLACK_TEAM_ID": os.environ.get("SLACK_TEAM_ID"),
        }
        missing = [name for name, value in required.items() if not value]
        raw_allowed = os.environ.get("SLACK_ALLOWED_USER_IDS", "")
        allowed_user_ids = frozenset(
            item.strip() for item in raw_allowed.split(",") if item.strip()
        )
        if not allowed_user_ids:
            missing.append("SLACK_ALLOWED_USER_IDS")
        if missing:
            raise ListenerConfigurationError(
                "Missing required Slack listener configuration: "
                + ", ".join(missing)
            )

        return cls(
            app_token=required["SLACK_APP_TOKEN"],
            bot_token=required["SLACK_BOT_TOKEN"],
            channel_id=required["SLACK_CHANNEL_ID"],
            team_id=required["SLACK_TEAM_ID"],
            allowed_user_ids=allowed_user_ids,
        )


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


def _display_name(user: dict[str, Any], user_id: str) -> str:
    return str(
        user.get("real_name")
        or user.get("display_name")
        or user.get("name")
        or f"<@{user_id}>"
    )


class SlackRefreshListener:
    def __init__(
        self,
        config: ListenerConfig,
        *,
        refresh_runner: Callable[..., refresh_pipeline.RefreshResult]
        = refresh_pipeline.refresh_usage,
    ) -> None:
        self.config = config
        self.refresh_runner = refresh_runner
        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="slack-refresh",
        )
        self._job_state_lock = threading.Lock()
        self._job_in_flight = False

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _ack(
        self,
        client: Any,
        request: SocketModeRequest,
        text: str,
    ) -> None:
        payload: dict[str, Any] | None = None
        if request.accepts_response_payload is not False:
            payload = {"response_type": "ephemeral", "text": text}
        client.send_socket_mode_response(
            SocketModeResponse(request.envelope_id, payload=payload)
        )

    def _interaction_context(
        self,
        payload: dict[str, Any],
    ) -> tuple[
        str | None,
        str | None,
        str | None,
        str | None,
        dict[str, Any],
    ]:
        user = payload.get("user") or {}
        container = payload.get("container") or {}
        channel = payload.get("channel") or {}
        user_id = user.get("id") or payload.get("user_id")
        channel_id = (
            container.get("channel_id")
            or channel.get("id")
            or payload.get("channel_id")
        )
        team_id = payload.get("team_id") or (payload.get("team") or {}).get("id")
        message_ts = (
            container.get("message_ts")
            or (payload.get("message") or {}).get("ts")
        )
        return team_id, channel_id, user_id, message_ts, user

    def _validate_refresh(
        self,
        payload: dict[str, Any],
    ) -> tuple[
        bool,
        str,
        str | None,
        str | None,
        str | None,
        dict[str, Any],
    ]:
        actions = payload.get("actions") or []
        if not any(action.get("action_id") == "refresh_usage" for action in actions):
            return False, "Thao tác Slack không được hỗ trợ.", None, None, None, {}

        team_id, channel_id, user_id, message_ts, user = self._interaction_context(payload)
        if team_id != self.config.team_id:
            return False, "Không gian làm việc Slack này không được cấp quyền.", channel_id, user_id, message_ts, user
        if channel_id != self.config.channel_id:
            return False, "Kênh này không được phép làm mới dữ liệu.", channel_id, user_id, message_ts, user
        # An explicit wildcard allows every user in the configured workspace
        # and channel. Keep the workspace/channel checks above in place.
        if (
            "*" not in self.config.allowed_user_ids
            and user_id not in self.config.allowed_user_ids
        ):
            return False, "Bạn không có quyền làm mới dữ liệu này.", channel_id, user_id, message_ts, user
        return (
            True,
            "Đang làm mới. Bảng dữ liệu mới sẽ được gửi vào kênh này.",
            channel_id,
            user_id,
            message_ts,
            user,
        )

    def _set_control_panel_running(
        self,
        channel_id: str | None,
        message_ts: str | None,
        running: bool,
    ) -> None:
        if not channel_id or not message_ts:
            return
        try:
            slack_notify.slack_api(
                "chat.update",
                self.config.bot_token,
                {
                    "channel": channel_id,
                    "ts": message_ts,
                    "text": slack_control_panel.CONTROL_PANEL_TEXT,
                    "blocks": json.dumps(
                        slack_control_panel.control_panel_blocks(running=running),
                        ensure_ascii=False,
                    ),
                },
            )
        except Exception:
            LOGGER.exception(
                "Could not update the Slack control panel running=%s",
                running,
            )

    def _run_refresh(
        self,
        channel_id: str,
        user_id: str,
        user: dict[str, Any],
        message_ts: str | None = None,
    ) -> None:
        requested_by = _display_name(user, user_id)
        try:
            self.refresh_runner("manual", requested_by)
            LOGGER.info("Manual refresh completed for Slack user %s", user_id)
        except refresh_pipeline.RefreshCooldownError as exc:
            LOGGER.info("Manual refresh rejected by cooldown for Slack user %s", user_id)
            try:
                slack_notify.post_ephemeral(
                    self.config.bot_token,
                    channel_id,
                    user_id,
                    f"Đang trong thời gian chờ. Vui lòng thử lại sau {exc.retry_after} giây.",
                )
            except Exception:
                LOGGER.exception("Could not send cooldown response to Slack")
        except refresh_pipeline.RefreshBusyError:
            LOGGER.info("Manual refresh rejected because another job is running")
            try:
                slack_notify.post_ephemeral(
                    self.config.bot_token,
                    channel_id,
                    user_id,
                    "Đang có một lần làm mới khác. Vui lòng chờ bảng dữ liệu mới.",
                )
            except Exception:
                LOGGER.exception("Could not send busy response to Slack")
        except Exception as exc:
            LOGGER.exception("Manual refresh failed for Slack user %s", user_id)
            try:
                slack_notify.post_message(
                    self.config.bot_token,
                    channel_id,
                    slack_notify.format_refresh_failure(exc),
                )
            except Exception:
                LOGGER.exception("Could not send refresh failure to Slack")
        finally:
            self._set_control_panel_running(channel_id, message_ts, running=False)
            with self._job_state_lock:
                self._job_in_flight = False

    def handle_request(self, client: Any, request: SocketModeRequest) -> None:
        if request.type != "interactive":
            client.send_socket_mode_response(
                SocketModeResponse(request.envelope_id)
            )
            return

        payload = request.payload if isinstance(request.payload, dict) else {}
        valid, message, channel_id, user_id, message_ts, user = self._validate_refresh(payload)
        if not valid:
            self._ack(client, request, message)
            return

        with self._job_state_lock:
            if self._job_in_flight:
                self._ack(client, request, "Đang có một lần làm mới khác. Vui lòng chờ.")
                return
            self._job_in_flight = True
        self._ack(client, request, message)
        self._set_control_panel_running(channel_id, message_ts, running=True)
        self.executor.submit(
            self._run_refresh,
            channel_id,
            user_id,
            user,
            message_ts,
        )

    def start(self) -> None:
        web_client = WebClient(token=self.config.bot_token)
        client = SocketModeClient(
            app_token=self.config.app_token,
            web_client=web_client,
        )
        client.socket_mode_request_listeners.append(self.handle_request)
        LOGGER.info("Starting Slack Socket Mode listener")
        client.connect()
        try:
            while True:
                threading.Event().wait(1)
        finally:
            client.close()


def main() -> int:
    slack_notify.configure_console()
    parser = argparse.ArgumentParser(
        description="Listen for Slack Refresh button interactions via Socket Mode."
    )
    parser.add_argument("--log", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()

    configure_logging(Path(args.log))
    try:
        config = ListenerConfig.from_env()
    except ListenerConfigurationError as exc:
        LOGGER.error("%s", exc)
        return 2

    if args.check_config:
        allowed_summary = (
            "all" if "*" in config.allowed_user_ids else str(len(config.allowed_user_ids))
        )
        LOGGER.info(
            "Slack listener configuration is ready for channel %s and %s allowed user(s).",
            config.channel_id,
            allowed_summary,
        )
        return 0

    listener = SlackRefreshListener(config)
    try:
        listener.start()
    except KeyboardInterrupt:
        LOGGER.info("Slack listener stopped")
    finally:
        listener.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
