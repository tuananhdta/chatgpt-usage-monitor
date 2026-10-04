from __future__ import annotations

import unittest
from unittest.mock import Mock

import listener_watchdog


class ListenerWatchdogTests(unittest.TestCase):
    def test_restarts_after_unexpected_exit(self) -> None:
        process = Mock(side_effect=[1, 2])
        sleep = Mock()

        result = listener_watchdog.run_watchdog(
            command=["python", "slack_listener.py"],
            restart_delay=15,
            process_runner=process,
            sleep=sleep,
        )

        self.assertEqual(result, 2)
        self.assertEqual(process.call_count, 2)
        sleep.assert_called_once_with(15)

    def test_configuration_error_stops_without_restart(self) -> None:
        process = Mock(return_value=2)
        sleep = Mock()

        result = listener_watchdog.run_watchdog(
            command=["python", "slack_listener.py"],
            process_runner=process,
            sleep=sleep,
        )

        self.assertEqual(result, 2)
        process.assert_called_once()
        sleep.assert_not_called()

    def test_once_mode_does_not_restart(self) -> None:
        process = Mock(return_value=1)
        sleep = Mock()

        result = listener_watchdog.run_watchdog(
            command=["python", "slack_listener.py"],
            once=True,
            process_runner=process,
            sleep=sleep,
        )

        self.assertEqual(result, 1)
        process.assert_called_once()
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
