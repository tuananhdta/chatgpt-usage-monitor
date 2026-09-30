from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_client import find_codex


class FindCodexTests(unittest.TestCase):
    def test_finds_codex_in_standard_local_install_when_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = (
                Path(temp_dir)
                / "OpenAI"
                / "Codex"
                / "bin"
                / "test-version"
            )
            install_dir.mkdir(parents=True)
            executable = install_dir / "codex.exe"
            executable.write_bytes(b"test")

            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}, clear=False):
                with patch("codex_client.shutil.which", return_value=None):
                    self.assertEqual(find_codex(), str(executable))


if __name__ == "__main__":
    unittest.main()
