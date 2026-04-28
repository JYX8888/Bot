"""系统提示词构造器。

这个文件的职责很单一：根据当前配置、记忆上下文和 Skills 上下文，
拼出每一轮真正送给模型的系统提示词。
"""

from __future__ import annotations

from datetime import datetime

from corebot.config import BotSettings


def build_system_prompt(
    settings: BotSettings,
    memory_context: str = "",
    skills_context: str = "",
) -> str:
    """构造系统提示词。

    参数：
    - settings: 当前运行配置，用于注入工作区路径等信息
    - memory_context: 结构化记忆模块生成的上下文
    - skills_context: Skills 管理器生成的技能上下文

    返回：
    - 拼接好的系统提示词字符串
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # parts 使用列表而不是字符串直接拼接，便于按条件追加不同上下文块。
    parts = [
        f"""你是 corebot，一个面向本地工作区的精简型编码助手。

当前时间：{now}
工作区：{settings.workspace}

运行规则：
- 除非用户明确要求，否则只在工作区内活动。
- 读取、列出、搜索和编辑文件时，优先使用专用工具，不要优先依赖 Shell。
- 修改文件前先阅读文件，除非需求非常简单且明确。
- 回复保持简洁、直接、可执行。
- 工具失败时，简要说明原因，并选择最安全的下一步。
- 不要编造文件内容、命令输出或仓库结构。
- 如果历史记忆与用户当前这一轮的明确要求冲突，以用户当前要求为准。

主要职责：
- 检查代码
- 回答技术问题
- 按要求修改文件
- 在有帮助时执行安全的工作区命令""",
    ]

    if memory_context:
        parts.append("# 记忆上下文\n" + memory_context)

    if skills_context:
        parts.append(skills_context)

    return "\n\n".join(parts)
