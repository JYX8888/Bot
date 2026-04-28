"""受保护的 Shell 工具。

这个模块允许 bot 在工作区内执行 PowerShell 命令，但会做两层保护：
1. 工作目录不能越出工作区
2. 高风险命令会被正则规则直接拦截
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from corebot.bootstrap import bootstrap_local_langchain
from corebot.path_utils import WorkspacePathError, resolve_workspace_path

bootstrap_local_langchain()

from langchain_core.tools import tool


# 这些模式用于阻止高风险命令，例如强制删除、硬重置、关机等。
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
    """截断过长的 Shell 输出。"""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n... 输出已截断 ..."


def build_shell_tool(workspace: Path, timeout_seconds: int, max_chars: int):
    """构造受保护的 Shell 工具。"""
    workspace = workspace.resolve()

    @tool
    def run_shell(command: str, working_dir: str = ".", timeout: int | None = None) -> str:
        """在工作区内执行受保护的 Shell 命令。

        参数：
        - command: 要执行的 PowerShell 命令
        - working_dir: 命令执行目录，必须位于工作区内
        - timeout: 可选超时秒数；为空时使用默认超时
        """
        for pattern in _DENY_PATTERNS:
            if re.search(pattern, command, flags=re.IGNORECASE):
                return f"错误：命令被安全规则拦截：{pattern}"

        try:
            cwd = resolve_workspace_path(workspace, working_dir)
        except WorkspacePathError as exc:
            return f"错误：{exc}"

        if not cwd.exists() or not cwd.is_dir():
            return f"错误：不是目录：{working_dir}"

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
            return f"错误：命令在 {effective_timeout} 秒后超时"

        output = completed.stdout or ""
        if completed.stderr:
            output = f"{output}\n标准错误输出：\n{completed.stderr}".strip()

        output = output.strip() or "(无输出)"
        output = _truncate(output, max_chars)
        return f"{output}\n\n退出码：{completed.returncode}"

    return run_shell
