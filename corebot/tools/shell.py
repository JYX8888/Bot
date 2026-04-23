from __future__ import annotations

import re
import subprocess
from pathlib import Path

from corebot.bootstrap import bootstrap_local_langchain
from corebot.path_utils import WorkspacePathError, resolve_workspace_path

bootstrap_local_langchain()

from langchain_core.tools import tool


_DENY_PATTERNS = [
    r"(^|\s)rm\s+-rf",
    r"(^|\s)del\s+/",
    r"(^|\s)rmdir\s+/s",
    r"Remove-Item\b",
    r"git\s+reset\s+--hard",
    r"git\s+checkout\s+--",
    r"shutdown\b",
    r"reboot\b",
    r"format\b",
]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n... truncated ..."


def build_shell_tool(workspace: Path, timeout_seconds: int, max_chars: int):
    workspace = workspace.resolve()

    @tool
    def run_shell(command: str, working_dir: str = ".", timeout: int | None = None) -> str:
        """Run a guarded shell command inside the workspace."""
        for pattern in _DENY_PATTERNS:
            if re.search(pattern, command, flags=re.IGNORECASE):
                return f"Error: Command blocked by safety rule: {pattern}"
        try:
            cwd = resolve_workspace_path(workspace, working_dir)
        except WorkspacePathError as exc:
            return f"Error: {exc}"
        if not cwd.exists() or not cwd.is_dir():
            return f"Error: Not a directory: {working_dir}"
        effective_timeout = timeout or timeout_seconds
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoLogo",
                    "-NoProfile",
                    "-Command",
                    command,
                ],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {effective_timeout} seconds"
        output = completed.stdout or ""
        if completed.stderr:
            output = f"{output}\nSTDERR:\n{completed.stderr}".strip()
        output = output.strip() or "(no output)"
        output = _truncate(output, max_chars)
        return f"{output}\n\nExit code: {completed.returncode}"

    return run_shell
