"""为本地 LangChain 源码提供导入兜底逻辑。

这个项目既可以依赖已经安装好的 `langchain_core` / `langchain_openai`，
也可以直接复用当前仓库旁边的 `langchain` 源码目录。

这样做的好处是：
- 在本地调试时不一定要先 `pip install`
- 可以直接联动修改本地 LangChain 源码
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def bootstrap_local_langchain() -> None:
    """在缺少已安装包时，把兄弟目录中的 LangChain 源码加到 `sys.path`。

    这个函数是幂等的，多次调用不会重复插入路径。
    """
    if importlib.util.find_spec("langchain_core") and importlib.util.find_spec("langchain_openai"):
        return

    project_root = Path(__file__).resolve().parents[1]
    repo_root = project_root.parent
    libs_root = repo_root / "langchain" / "libs"

    # 这些目录对应 LangChain 的不同子包源码位置。
    candidates = [
        libs_root / "core",
        libs_root / "langchain_v1",
        libs_root / "partners" / "openai",
    ]

    # reversed 的目的是保证后插入的路径会排在 sys.path 更靠前的位置。
    for candidate in reversed(candidates):
        if candidate.exists():
            text = str(candidate)
            if text not in sys.path:
                sys.path.insert(0, text)
