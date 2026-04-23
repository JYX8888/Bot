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
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2) :]
    return f"{head}\n\n... truncated ...\n\n{tail}"


def build_file_tools(workspace: Path, max_chars: int) -> list:
    workspace = workspace.resolve()

    @tool
    def list_dir(path: str = ".") -> str:
        """List files and directories under a workspace path."""
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"Error: {exc}"
        if not target.exists():
            return f"Error: Path not found: {path}"
        if not target.is_dir():
            return f"Error: Not a directory: {path}"
        lines = []
        for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            prefix = "[D]" if child.is_dir() else "[F]"
            rel = child.relative_to(workspace)
            lines.append(f"{prefix} {rel}")
        return "\n".join(lines) if lines else "(empty directory)"

    @tool
    def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
        """Read a UTF-8 text file with line numbers."""
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"Error: {exc}"
        if not target.exists():
            return f"Error: File not found: {path}"
        if not target.is_file():
            return f"Error: Not a file: {path}"
        try:
            text = read_text_file(target)
        except BinaryFileError as exc:
            return f"Error: {exc}"
        lines = text.replace("\r\n", "\n").split("\n")
        start = max(offset - 1, 0)
        end = min(start + max(limit, 1), len(lines))
        body = [f"{index + 1}| {lines[index]}" for index in range(start, end)]
        suffix = f"\n\n(Showing lines {start + 1}-{end} of {len(lines)})"
        return _truncate("\n".join(body) + suffix, max_chars)

    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a UTF-8 text file inside the workspace."""
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"Error: {exc}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {target.relative_to(workspace)} ({len(content)} chars)"

    @tool
    def replace_in_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        """Replace text in a UTF-8 file. By default exactly one match is expected."""
        try:
            target = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"Error: {exc}"
        if not target.exists():
            return f"Error: File not found: {path}"
        try:
            text = read_text_file(target)
        except BinaryFileError as exc:
            return f"Error: {exc}"
        count = text.count(old_text)
        if count == 0:
            return "Error: old_text was not found"
        if not replace_all and count != 1:
            return f"Error: old_text matched {count} times; refine the target or set replace_all=true"
        updated = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
        target.write_text(updated, encoding="utf-8")
        return f"Updated {target.relative_to(workspace)}"

    @tool
    def glob_search(pattern: str, path: str = ".") -> str:
        """Find files by glob pattern under the workspace."""
        try:
            base = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"Error: {exc}"
        if not base.exists() or not base.is_dir():
            return f"Error: Not a directory: {path}"
        matches = [
            str(item.relative_to(workspace))
            for item in base.glob(pattern)
            if item.is_file()
        ]
        if not matches:
            return "No files found"
        return _truncate("\n".join(sorted(matches)), max_chars)

    @tool
    def grep_search(pattern: str, path: str = ".", include: str = "*") -> str:
        """Search file content with a regular expression."""
        try:
            base = resolve_workspace_path(workspace, path)
        except WorkspacePathError as exc:
            return f"Error: {exc}"
        if not base.exists() or not base.is_dir():
            return f"Error: Not a directory: {path}"
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return f"Error: Invalid regex: {exc}"
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
            return "No matches found"
        return _truncate("\n".join(results), max_chars)

    return [list_dir, read_file, write_file, replace_in_file, glob_search, grep_search]
