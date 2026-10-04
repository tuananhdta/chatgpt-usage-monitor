from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from render_dashboard import (
    dashboard_height,
    filter_dashboard_accounts,
    render_dashboard,
    reset_credit_lines,
)


class DashboardAccountFilterTests(unittest.TestCase):
    def test_excludes_explicit_free_plan_accounts(self) -> None:
        accounts = [
            {"id": "acc01", "label": "Acc 01", "plan_type": "plus"},
            {"id": "acc02", "label": "Acc 02", "plan_type": "free"},
            {"id": "acc03", "label": "Acc 03", "plan_type": "PLUS"},
        ]

        self.assertEqual(
            [account["id"] for account in filter_dashboard_accounts(accounts)],
            ["acc01", "acc03"],
        )

    def test_keeps_accounts_when_plan_is_unknown(self) -> None:
        accounts = [
            {"id": "acc01", "label": "Acc 01", "plan_type": None},
            {"id": "acc02", "label": "Acc 02"},
        ]

        self.assertEqual(
            [account["id"] for account in filter_dashboard_accounts(accounts)],
            ["acc01", "acc02"],
        )


class DashboardHeightTests(unittest.TestCase):
    def test_height_shrinks_with_three_visible_accounts(self) -> None:
        self.assertEqual(dashboard_height(3), 757)

    def test_height_keeps_header_when_no_accounts_are_visible(self) -> None:
        self.assertEqual(dashboard_height(0), 265)


class RenderDashboardLayoutTests(unittest.TestCase):
    def test_rendered_dashboard_uses_only_visible_accounts(self) -> None:
        account_template = {
            "status": "ok",
            "five_hour": {"remaining_percent": 80, "reset_time_vn": "N/A"},
            "weekly": {"remaining_percent": 90, "reset_time_vn": "N/A"},
            "rate_limit_reset_credits": {"credits": []},
        }
        payload = {
            "collected_at_vn": "21/09/2026 10:00:00",
            "accounts": [
                {**account_template, "id": "acc01", "label": "Acc 01", "plan_type": "plus"},
                {**account_template, "id": "acc02", "label": "Acc 02", "plan_type": "free"},
                {**account_template, "id": "acc03", "label": "Acc 03", "plan_type": "plus"},
                {**account_template, "id": "acc04", "label": "Acc 04", "plan_type": "plus"},
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            usage_path = temp_path / "usage.json"
            output_path = temp_path / "dashboard.png"
            usage_path.write_text(json.dumps(payload), encoding="utf-8")

            render_dashboard(usage_path, output_path)

            with Image.open(output_path) as image:
                self.assertEqual(image.size, (1688, 757))


class ResetCreditLinesTests(unittest.TestCase):
    def test_lists_every_available_reset_credit(self) -> None:
        account = {
            "rate_limit_reset_credits": {
                "availableCount": 3,
                "credits": [
                    {
                        "status": "available",
                        "expiresAt": 1789948211,
                        "title": "Full reset (Weekly + 5 hr)",
                    },
                    {
                        "status": "available",
                        "expiresAt": 1791077633,
                        "title": "Full reset (Weekly + 5 hr)",
                    },
                    {
                        "status": "available",
                        "expiresAt": 1791157056,
                        "title": "Full reset (Weekly + 5 hr)",
                    },
                ],
            }
        }

        self.assertEqual(
            reset_credit_lines(account),
            [
                "3 Lượt đặt lại đầy đủ",
                "Hết hạn 1 VN 21/09/2026 06:50",
                "Hết hạn 2 VN 04/10/2026 08:33",
                "Hết hạn 3 VN 05/10/2026 06:37",
            ],
        )


if __name__ == "__main__":
    unittest.main()
