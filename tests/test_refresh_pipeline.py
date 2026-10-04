from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import refresh_pipeline
from slack_notify import format_dashboard_caption


class RefreshPipelineTests(unittest.TestCase):
    def test_cross_process_lock_rejects_second_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "refresh.lock"
            with refresh_pipeline.RefreshLock(lock_path):
                with self.assertRaises(refresh_pipeline.RefreshBusyError):
                    with refresh_pipeline.RefreshLock(lock_path):
                        pass

    def test_manual_refresh_writes_metadata_and_uploads_top_level_caption(self) -> None:
        payload = {
            "collected_at_vn": "04/10/2026 10:15:00",
            "accounts": [
                {"id": "acc01", "label": "Acc 01", "status": "ok"},
                {
                    "id": "acc02",
                    "label": "Acc 02",
                    "status": "error",
                    "error": "logout",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            usage_path = root / "usage.json"
            dashboard_path = root / "dashboard.png"
            state_path = root / "state.json"
            lock_path = root / "refresh.lock"

            def fake_collect_all(*, output_path: Path, metadata: dict[str, object]):
                saved = {**payload, **metadata}
                output_path.write_text(json.dumps(saved), encoding="utf-8")
                return saved

            def fake_render(input_path: Path, output_path: Path) -> Path:
                self.assertEqual(input_path, usage_path)
                output_path.write_bytes(b"png")
                return output_path

            with (
                patch.object(refresh_pipeline.collect_all, "collect_all", fake_collect_all),
                patch.object(
                    refresh_pipeline.render_dashboard,
                    "render_dashboard",
                    fake_render,
                ),
                patch.object(
                    refresh_pipeline.slack_notify,
                    "send_usage_error_alert",
                    return_value=True,
                ),
                patch.object(
                    refresh_pipeline.slack_notify,
                    "upload_image",
                    return_value={"ok": True},
                ) as upload,
            ):
                result = refresh_pipeline.refresh_usage(
                    "manual",
                    "TuanAnh",
                    usage_path=usage_path,
                    dashboard_path=dashboard_path,
                    state_path=state_path,
                    lock_path=lock_path,
                    publish_slack=True,
                )

            saved = json.loads(usage_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["source"], "manual")
            self.assertEqual(saved["requested_by"], "TuanAnh")
            self.assertEqual(result.account_errors[0]["id"], "acc02")
            caption = upload.call_args.args[3]
            self.assertEqual(
                caption,
                f"Cập nhật: {result.requested_at_vn} (giờ Việt Nam)",
            )
            self.assertNotIn("thread_ts", upload.call_args.kwargs)

    def test_cooldown_blocks_second_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_path = root / "state.json"
            state_path.write_text(
                json.dumps({"last_started_at_epoch": time.time()}),
                encoding="utf-8",
            )

            with patch.object(refresh_pipeline, "cooldown_seconds", return_value=45):
                with patch.object(refresh_pipeline.collect_all, "collect_all") as collect:
                    with self.assertRaises(refresh_pipeline.RefreshCooldownError):
                        refresh_pipeline.refresh_usage(
                            "manual",
                            "TuanAnh",
                            state_path=state_path,
                            lock_path=root / "refresh.lock",
                            publish_slack=False,
                        )
            collect.assert_not_called()


class DashboardCaptionTests(unittest.TestCase):
    def test_caption_contains_only_update_time(self) -> None:
        caption = format_dashboard_caption(
            "automation",
            "Task Scheduler",
            "04/10/2026 10:15:00",
        )
        self.assertEqual(caption, "Cập nhật: 04/10/2026 10:15:00 (giờ Việt Nam)")


if __name__ == "__main__":
    unittest.main()
