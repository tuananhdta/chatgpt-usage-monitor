from __future__ import annotations

import unittest

from render_dashboard import reset_credit_lines


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
                "3 Full resets",
                "Exp 1 VN 21/09/2026 06:50",
                "Exp 2 VN 04/10/2026 08:33",
                "Exp 3 VN 05/10/2026 06:37",
            ],
        )


if __name__ == "__main__":
    unittest.main()
