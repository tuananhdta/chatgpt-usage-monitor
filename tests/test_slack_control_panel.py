from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import slack_control_panel


class ControlPanelTests(unittest.TestCase):
    def test_blocks_have_stable_refresh_action(self) -> None:
        blocks = slack_control_panel.control_panel_blocks()
        actions = blocks[-1]["elements"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action_id"], "refresh_usage")
        self.assertEqual(actions[0]["value"], "manual")

    def test_running_blocks_show_feedback_without_button(self) -> None:
        status = slack_control_panel.control_panel_blocks(running=True)[-1]

        self.assertEqual(status["type"], "section")
        self.assertIn("Đang làm mới", status["text"]["text"])

    def test_create_saves_message_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "control_panel.json"
            with patch.object(
                slack_control_panel.slack_notify,
                "post_blocks",
                return_value={"ok": True, "ts": "123.456"},
            ) as post:
                result = slack_control_panel.publish_control_panel(
                    token="xoxb-test",
                    channel_id="C123",
                    state_path=state_path,
                )

            self.assertTrue(result["ok"])
            self.assertEqual(json.loads(state_path.read_text())["message_ts"], "123.456")
            self.assertEqual(post.call_args.args[1], "C123")

    def test_bookmark_uses_control_panel_permalink_and_saves_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "control_panel.json"
            state_path.write_text(
                json.dumps({"message_ts": "123.456", "old_field": "kept"}),
                encoding="utf-8",
            )
            with patch.object(
                slack_control_panel.slack_notify,
                "slack_api",
                side_effect=[
                    {"ok": True, "permalink": "https://example.slack.com/panel"},
                    {"ok": True, "bookmark": {"id": "Bk123"}},
                ],
            ) as api:
                result = slack_control_panel.sync_refresh_bookmark(
                    token="xoxb-test",
                    channel_id="C123",
                    state_path=state_path,
                )

            self.assertTrue(result["ok"])
            self.assertEqual([call.args[0] for call in api.call_args_list], [
                "chat.getPermalink",
                "bookmarks.add",
            ])
            fields = api.call_args_list[1].args[2]
            self.assertEqual(fields["channel_id"], "C123")
            self.assertEqual(fields["link"], "https://example.slack.com/panel")
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["bookmark_id"], "Bk123")
            self.assertEqual(saved["old_field"], "kept")

    def test_bookmark_updates_saved_bookmark_without_adding_another(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "control_panel.json"
            state_path.write_text(
                json.dumps({"message_ts": "123.456", "bookmark_id": "Bk123"}),
                encoding="utf-8",
            )
            with patch.object(
                slack_control_panel.slack_notify,
                "slack_api",
                side_effect=[
                    {"ok": True, "permalink": "https://example.slack.com/panel"},
                    {"ok": True, "bookmark": {"id": "Bk123"}},
                ],
            ) as api:
                slack_control_panel.sync_refresh_bookmark(
                    token="xoxb-test",
                    channel_id="C123",
                    state_path=state_path,
                )

            self.assertEqual(api.call_args_list[1].args[0], "bookmarks.edit")
            self.assertEqual(api.call_args_list[1].args[2]["bookmark_id"], "Bk123")


if __name__ == "__main__":
    unittest.main()
