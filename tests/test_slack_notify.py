from __future__ import annotations

import unittest

from slack_notify import format_usage_error_alert


class UsageErrorAlertTests(unittest.TestCase):
    def test_environment_errors_are_not_reported_as_login_errors(self) -> None:
        message = format_usage_error_alert(
            [
                {
                    "id": "acc01",
                    "label": "Acc 01",
                    "error_type": "environment_error",
                    "error": "Không tìm thấy Codex CLI trong PATH",
                    "attempts": 1,
                }
            ],
            "30/09/2026 10:00:01",
            mention="@TuanAnh",
        )

        self.assertIn("Nhóm lỗi môi trường máy tính", message)
        self.assertIn("kiểm tra/cài lại Codex CLI", message)
        self.assertNotIn("Nhóm cần kiểm tra đăng nhập", message)


if __name__ == "__main__":
    unittest.main()
