from __future__ import annotations

from pathlib import Path


class WorkspacePathError(ValueError):
    pass


class BinaryFileError(ValueError):
    pass


def resolve_workspace_path(workspace: Path, raw_path: str) -> Path:
    base = workspace.resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise WorkspacePathError(f"Path '{raw_path}' escapes the workspace") from exc
    return resolved


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BinaryFileError(f"File '{path}' is not valid UTF-8 text") from exc
