"""文件工具集合。

这个文件把常见的工作区文件操作封装成 LangChain 工具：
- 列目录
- 读文件
- 写文件
- 替换文本
- glob 搜索文件
- 正则搜索文件内容

这些工具是 bot 处理本地代码仓库时最常用的一批能力。
"""

from __future__ import annotations

import re
from pathlib import Path

from corebot.bootstrap import bootstrap_local_langchain
from corebot.path_utils import (
    BinaryFileError,
    WorkspacePathError,
    read_text_file,
    resolve_workspace_path,
)

bootstrap_local_langchain()

from langchain_core.tools import tool


def _truncate(text: str, limit: int) -> str:
    """把过长的工具输出截断到指定长度。"""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2) :]
    return f"{head}\n\n... 输出已截断 ...\n\n{tail}"


def build_file_tools(workspace: Path, max_chars: int) -> list:
    """构造所有文件相关工具。

    参数：
    - workspace: 工作区根目录
    - max_chars: 单次工具输出最大字符数

    返回：
    - LangChain 工具对象列表
    """
    workspace = workspace.resolve()

    @tool
    def list_dir(path: str = ".") -> str:
        """列出工作区路径下的文件和目录。"""
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"错误：{exc}"

        if not target.exists():
            return f"错误：路径不存在：{path}"
        if not target.is_dir():
            return f"错误：不是目录：{path}"

        lines = []
        for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            prefix = "[D]" if child.is_dir() else "[F]"
            rel = child.relative_to(workspace)
            lines.append(f"{prefix} {rel}")
        return "\n".join(lines) if lines else "(空目录)"

    @tool
    def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
        """读取 UTF-8 文本文件并显示行号。

        参数：
        - path: 文件路径
        - offset: 起始行号，从 1 开始
        - limit: 最多读取多少行
        """
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"错误：{exc}"

        if not target.exists():
            return f"错误：文件不存在：{path}"
        if not target.is_file():
            return f"错误：不是文件：{path}"

        try:
            text = read_text_file(target)
        except BinaryFileError as exc:
            return f"错误：{exc}"

        lines = text.replace("\r\n", "\n").split("\n")
        start = max(offset - 1, 0)
        end = min(start + max(limit, 1), len(lines))
        body = [f"{index + 1}| {lines[index]}" for index in range(start, end)]
        suffix = f"\n\n（显示第 {start + 1}-{end} 行，共 {len(lines)} 行）"
        return _truncate("\n".join(body) + suffix, max_chars)

    @tool
    def write_file(path: str, content: str) -> str:
        """在工作区内创建或覆盖 UTF-8 文本文件。"""
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"错误：{exc}"

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"已写入 {target.relative_to(workspace)}（{len(content)} 字符）"

    @tool
    def replace_in_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        """在 UTF-8 文件中替换文本。

        参数：
        - path: 文件路径
        - old_text: 要被替换的文本
        - new_text: 替换后的文本
        - replace_all: 是否替换全部匹配；默认只允许替换一个匹配项
        """
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"错误：{exc}"

        if not target.exists():
            return f"错误：文件不存在：{path}"

        try:
            text = read_text_file(target)
        except BinaryFileError as exc:
            return f"错误：{exc}"

        count = text.count(old_text)
        if count == 0:
            return "错误：未找到 old_text"
        if not replace_all and count != 1:
            return f"错误：old_text 匹配了 {count} 次；请缩小范围或设置 replace_all=true"

        updated = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
        target.write_text(updated, encoding="utf-8")
        return f"已更新 {target.relative_to(workspace)}"

    @tool
    def glob_search(pattern: str, path: str = ".") -> str:
        """在工作区内按 glob 模式查找文件。"""
        try:
            base = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"错误：{exc}"

        if not base.exists() or not base.is_dir():
            return f"错误：不是目录：{path}"

        matches = [
            str(item.relative_to(workspace))
            for item in base.glob(pattern)
            if item.is_file()
        ]
        if not matches:
            return "未找到文件"
        return _truncate("\n".join(sorted(matches)), max_chars)

    @tool
    def grep_search(pattern: str, path: str = ".", include: str = "*") -> str:
        """按正则表达式搜索文件内容。"""
        try:
            base = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"错误：{exc}"

        if not base.exists() or not base.is_dir():
            return f"错误：不是目录：{path}"

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"错误：正则表达式无效：{exc}"

        results = []
        for file_path in base.rglob(include):
            if not file_path.is_file():
                continue
            try:
                text = read_text_file(file_path).replace("\r\n", "\n")
            except (BinaryFileError, OSError):
                continue
            for line_number, line in enumerate(text.split("\n"), start=1):
                if regex.search(line):
                    rel = file_path.relative_to(workspace)
                    results.append(f"{rel}:{line_number}: {line}")

        if not results:
            return "未找到匹配项"
        return _truncate("\n".join(results), max_chars)

    return [list_dir, read_file, write_file, replace_in_file, glob_search, grep_search]
