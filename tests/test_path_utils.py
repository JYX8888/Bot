from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from corebot.path_utils import BinaryFileError, WorkspacePathError, read_text_file, resolve_workspace_path


class PathUtilsTest(unittest.TestCase):
    def _make_workspace(self, name: str) -> Path:
        workspace = Path(__file__).resolve().parent / ".tmp" / name
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(workspace, ignore_errors=True))
        return workspace

    def test_resolve_workspace_path_rejects_escape(self) -> None:
        workspace = self._make_workspace("escape")
        with self.assertRaises(WorkspacePathError):
            resolve_workspace_path(workspace, "../outside.txt")

    def test_read_text_file_rejects_binary(self) -> None:
        workspace = self._make_workspace("binary")
        path = workspace / "data.bin"
        path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaises(BinaryFileError):
            read_text_file(path)


if __name__ == "__main__":
    unittest.main()
