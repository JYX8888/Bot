"""工作区路径与文本文件处理工具。

这个文件主要解决两类问题：
1. 如何确保用户给的路径没有逃逸出工作区
2. 如何安全读取 UTF-8 文本文件，并在遇到二进制文件时给出明确错误
"""

from __future__ import annotations

from pathlib import Path


class WorkspacePathError(ValueError):
    """表示路径越界到了工作区之外。"""


class BinaryFileError(ValueError):
    """表示目标文件不是可按 UTF-8 读取的文本文件。"""


def resolve_workspace_path(workspace: Path, raw_path: str) -> Path:
    """把用户提供的路径解析成工作区内的绝对路径。

    参数：
    - workspace: 工作区根目录
    - raw_path: 用户输入的相对路径或绝对路径

    返回：
    - 解析后的绝对路径

    异常：
    - WorkspacePathError: 当路径解析后不在工作区范围内时抛出
    """
    base = workspace.resolve()
    candidate = Path(raw_path).expanduser()

    # 相对路径按工作区根目录解释。
    if not candidate.is_absolute():
        candidate = base / candidate

    resolved = candidate.resolve()

    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise WorkspacePathError(f"路径“{raw_path}”越界到了工作区之外") from exc

    return resolved


def read_text_file(path: Path) -> str:
    """按 UTF-8 读取文本文件。

    参数：
    - path: 目标文件绝对路径

    返回：
    - 文件内容字符串

    异常：
    - BinaryFileError: 当文件无法按 UTF-8 解码时抛出
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BinaryFileError(f"文件“{path}”不是有效的 UTF-8 文本") from exc
