"""工具模块导出入口。

这个文件的作用很简单：把最常用的工具构造函数统一导出，
这样外部模块只需要 `from corebot.tools import ...`。
"""

from corebot.tools.files import build_file_tools
from corebot.tools.shell import build_shell_tool

# `__all__` 用来声明“这个模块对外推荐导出的名字有哪些”。
__all__ = ["build_file_tools", "build_shell_tool"]
