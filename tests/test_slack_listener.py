from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from slack_sdk.socket_mode.request import SocketModeRequest

import slack_listener


class FakeSocketClient:
    def __init__(self) -> None:
        self.responses = []

    def send_socket_mode_response(self, response) -> None:
        self.responses.append(response)


def config() -> slack_listener.ListenerConfig:
    return slack_listener.ListenerConfig(
        app_token="xapp-test",
        bot_token="xoxb-test",
        channel_id="C123",
        team_id="T123",
        allowed_user_ids=frozenset({"U123"}),
    )


class SlackListenerTests(unittest.TestCase):
    def test_valid_refresh_is_acked_and_scheduled(self) -> None:
        runner = Mock()
        listener = slack_listener.SlackRefreshListener(config(), refresh_runner=runner)
        listener.executor.submit = Mock()
        client = FakeSocketClient()
        request = SocketModeRequest(
            type="interactive",
            envelope_id="env-1",
            payload={
                "team": {"id": "T123"},
                "channel": {"id": "C123"},
                "user": {"id": "U123", "name": "TuanAnh"},
                "actions": [{"action_id": "refresh_usage"}],
            },
            accepts_response_payload=True,
        )

        listener.handle_request(client, request)

        self.assertEqual(len(client.responses), 1)
        self.assertIn("Đang làm mới", client.responses[0].payload["text"])
        listener.executor.submit.assert_called_once()
        listener.close()

    def test_valid_refresh_disables_control_panel_immediately(self) -> None:
        runner = Mock()
        listener = slack_listener.SlackRefreshListener(config(), refresh_runner=runner)
        listener.executor.submit = Mock()
        client = FakeSocketClient()
        request = SocketModeRequest(
            type="interactive",
            envelope_id="env-running",
            payload={
                "team": {"id": "T123"},
                "channel": {"id": "C123"},
                "container": {"message_ts": "123.456"},
                "user": {"id": "U123", "name": "TuanAnh"},
                "actions": [{"action_id": "refresh_usage"}],
            },
            accepts_response_payload=True,
        )

        with patch.object(slack_listener.slack_notify, "slack_api") as api:
            listener.handle_request(client, request)

        api.assert_called_once()
        fields = api.call_args.args[2]
        self.assertEqual(api.call_args.args[0], "chat.update")
        self.assertEqual(fields["ts"], "123.456")
        self.assertIn("Đang làm mới", fields["blocks"])
        listener.close()

    def test_unauthorized_user_is_acked_without_scheduling(self) -> None:
        listener = slack_listener.SlackRefreshListener(config())
        listener.executor.submit = Mock()
        client = FakeSocketClient()
        request = SocketModeRequest(
            type="interactive",
            envelope_id="env-2",
            payload={
                "team": {"id": "T123"},
                "channel": {"id": "C123"},
                "user": {"id": "U999"},
                "actions": [{"action_id": "refresh_usage"}],
            },
            accepts_response_payload=True,
        )

        listener.handle_request(client, request)

        self.assertIn("không có quyền", client.responses[0].payload["text"])
        listener.executor.submit.assert_not_called()
        listener.close()

    def test_wildcard_allows_any_user_in_configured_channel(self) -> None:
        wildcard_config = slack_listener.ListenerConfig(
            app_token="xapp-test",
            bot_token="xoxb-test",
            channel_id="C123",
            team_id="T123",
            allowed_user_ids=frozenset({"*"}),
        )
        listener = slack_listener.SlackRefreshListener(wildcard_config)
        listener.executor.submit = Mock()
        client = FakeSocketClient()
        request = SocketModeRequest(
            type="interactive",
            envelope_id="env-wildcard",
            payload={
                "team": {"id": "T123"},
                "channel": {"id": "C123"},
                "user": {"id": "U999"},
                "actions": [{"action_id": "refresh_usage"}],
            },
            accepts_response_payload=True,
        )

        listener.handle_request(client, request)

        self.assertIn("Đang làm mới", client.responses[0].payload["text"])
        listener.executor.submit.assert_called_once()
        listener.close()

    def test_listener_config_requires_allowlist_and_app_token(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SLACK_APP_TOKEN": "",
                "SLACK_BOT_TOKEN": "xoxb-test",
                "SLACK_CHANNEL_ID": "C123",
                "SLACK_TEAM_ID": "T123",
                "SLACK_ALLOWED_USER_IDS": "",
            },
            clear=False,
        ):
            with self.assertRaises(slack_listener.ListenerConfigurationError):
                slack_listener.ListenerConfig.from_env()

    def test_background_failure_posts_channel_error(self) -> None:
        listener = slack_listener.SlackRefreshListener(
            config(),
            refresh_runner=Mock(side_effect=RuntimeError("render failed")),
        )
        with patch.object(slack_listener.slack_notify, "post_message") as post:
            listener._run_refresh("C123", "U123", {"name": "TuanAnh"})

        post.assert_called_once()
        self.assertIn("Không có bảng dữ liệu mới được gửi", post.call_args.args[2])
        self.assertFalse(listener._job_in_flight)
        listener.close()

    def test_background_cooldown_sends_ephemeral_retry_message(self) -> None:
        listener = slack_listener.SlackRefreshListener(
            config(),
            refresh_runner=Mock(
                side_effect=slack_listener.refresh_pipeline.RefreshCooldownError(12)
            ),
        )
        with patch.object(slack_listener.slack_notify, "post_ephemeral") as post:
            listener._run_refresh("C123", "U123", {"name": "TuanAnh"})

        post.assert_called_once_with(
            "xoxb-test",
            "C123",
            "U123",
            "Đang trong thời gian chờ. Vui lòng thử lại sau 12 giây.",
        )
        self.assertFalse(listener._job_in_flight)
        listener.close()

    def test_non_interactive_socket_event_is_acknowledged(self) -> None:
        listener = slack_listener.SlackRefreshListener(config())
        client = FakeSocketClient()
        request = SocketModeRequest(
            type="events_api",
            envelope_id="env-3",
            payload={},
        )

        listener.handle_request(client, request)

        self.assertEqual(len(client.responses), 1)
        self.assertEqual(client.responses[0].envelope_id, "env-3")
        self.assertIsNone(client.responses[0].payload)
        listener.close()


if __name__ == "__main__":
    unittest.main()
