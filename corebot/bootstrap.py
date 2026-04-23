from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def bootstrap_local_langchain() -> None:
    """Load sibling LangChain sources when site-packages do not provide them."""
    if importlib.util.find_spec("langchain_core") and importlib.util.find_spec("langchain_openai"):
        return

    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    libs_root = repo_root / "langchain" / "libs"
    candidates = [
        libs_root / "core",
        libs_root / "langchain_v1",
        libs_root / "partners" / "openai",
    ]
    for candidate in reversed(candidates):
        if candidate.exists():
            text = str(candidate)
            if text not in sys.path:
                sys.path.insert(0, text)
