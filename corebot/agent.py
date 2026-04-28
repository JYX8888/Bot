"""corebot 的主 Agent 实现。

这个文件负责把项目里的几个核心子系统串起来：
1. 配置加载后的运行时设置 `BotSettings`
2. LangChain/OpenAI 兼容模型客户端
3. 文件工具、Shell 工具、MCP 工具
4. 会话存储与结构化记忆
5. Skills 上下文注入

如果你想理解“用户输入 -> 组装上下文 -> 模型决策 -> 调工具 -> 保存记忆”
这一整条链路，这个文件是最重要的入口。
"""

from __future__ import annotations

from typing import Any

from corebot.bootstrap import bootstrap_local_langchain
from corebot.config import BotSettings
from corebot.mcp import connect_mcp_servers
from corebot.memory import MemoryManager
from corebot.prompts import build_system_prompt
from corebot.session_store import SessionStore
from corebot.skills import SkillsManager
from corebot.tools import build_file_tools, build_shell_tool

# 在导入 LangChain 相关模块前，先尝试补齐本地源码路径。
bootstrap_local_langchain()

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI


class CoreBotAgent:
    """代表一个完整可运行的 bot 实例。

    这个类把“模型、工具、记忆、技能、MCP”这些能力全部持有起来，
    并对外提供一个最核心的方法：`ask()`。

    参数：
    - settings: 已经解析好的运行配置，包含模型、目录、记忆窗口、MCP 等设置
    """

    def __init__(self, settings: BotSettings):
        """初始化 Agent 的所有运行时组件。"""
        # 先校验运行环境，例如 API Key 是否已经可用。
        settings.validate_runtime()

        # 保存配置，后续所有子系统都会用到。
        self.settings = settings

        # 会话存储：保存完整原始消息。
        self.session_store = SessionStore(settings.sessions_dir)

        # 记忆管理：负责摘要、偏好、项目记忆、历史召回和历史裁剪。
        self.memory = MemoryManager(
            settings.memory_dir,
            max_history_messages=settings.max_history_messages,
            max_recalled_memories=settings.max_recalled_memories,
            max_session_requests=settings.max_session_requests,
        )

        # 基础工具：文件工具 + 受保护的 Shell 工具。
        self.tools = build_file_tools(settings.workspace, settings.max_tool_output_chars)
        self.tools.append(
            build_shell_tool(
                settings.workspace,
                settings.shell_timeout,
                settings.max_tool_output_chars,
            )
        )

        # Skills 管理器：按用户输入动态决定要不要注入某些技能上下文。
        self.skills = SkillsManager(
            settings.workspace,
            builtin_skills_dir=settings.builtin_skills_dir,
            extra_skills_dirs=settings.extra_skills_dirs,
        )

        # 下面三个字段只用于 MCP 生命周期管理。
        self._mcp_tools: list = []
        self._mcp_stacks: dict[str, Any] = {}
        self._mcp_connected = False

        # 方便通过工具名快速定位对应的工具对象。
        self.tool_map = {tool.name: tool for tool in self.tools}

        # ChatOpenAI 这里并不意味着只能接 OpenAI，也可以接兼容 OpenAI 的服务端。
        self.model = ChatOpenAI(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )

        # 绑定工具后的模型对象。LangChain 会让模型输出 tool_calls。
        self.model_with_tools = self.model.bind_tools(self.tools)

    async def _ensure_mcp_connected(self) -> None:
        """按需连接 MCP 服务，并把 MCP 工具挂到当前 Agent 上。

        这里使用懒加载，而不是在初始化时立刻连接，原因是：
        - 并非所有用户请求都需要 MCP
        - 某些 MCP 服务启动成本较高
        - 可以减少 CLI 启动等待时间
        """
        if self._mcp_connected or not self.settings.mcp_servers:
            return

        self._mcp_tools, self._mcp_stacks = await connect_mcp_servers(self.settings.mcp_servers)

        # 如果拿到了 MCP 工具，就把它们合并到已有工具集中。
        if self._mcp_tools:
            self.tools.extend(self._mcp_tools)
            self.tool_map = {tool.name: tool for tool in self.tools}
            self.model_with_tools = self.model.bind_tools(self.tools)

        self._mcp_connected = True

    async def ask(self, user_input: str, session_id: str = "default") -> str:
        """处理一轮完整的用户提问。

        参数：
        - user_input: 用户当前这一轮的输入文本
        - session_id: 会话 ID。相同会话 ID 会共享历史消息和会话记忆

        返回：
        - 最终回复文本。如果模型没有给出标准字符串，也会被整理成字符串
        """
        await self._ensure_mcp_connected()

        # 1. 读取完整历史消息。
        stored_messages = self.session_store.load_messages(session_id)

        # 2. 对长历史做裁剪，只保留最近窗口内的原始消息。
        trimmed_history = self.memory.trim_history(stored_messages)

        # 3. 构建记忆上下文和 Skills 上下文。
        memory_context = self.memory.build_context(session_id, user_input, stored_messages)
        skills_context = self.skills.build_context(user_input)

        # 4. 构建系统提示词，把规则、记忆、技能一起注入。
        system_message = SystemMessage(
            content=build_system_prompt(
                self.settings,
                memory_context=memory_context,
                skills_context=skills_context,
            )
        )

        # 5. 这一轮新增消息从用户输入开始。
        turn_messages: list[BaseMessage] = [HumanMessage(content=user_input)]

        # 6. 运行时消息 = 系统提示 + 裁剪后的历史 + 当前轮新增消息。
        runtime_messages: list[BaseMessage] = [system_message, *trimmed_history, *turn_messages]

        # 用于记录最终纯文本答案。
        final_text = ""

        # 7. 进入“模型回复 / 工具执行 / 再次调用模型”的循环。
        for _ in range(self.settings.max_iterations):
            ai_message = await self.model_with_tools.ainvoke(runtime_messages)
            runtime_messages.append(ai_message)
            turn_messages.append(ai_message)

            # 如果没有工具调用，说明这轮已经是最终回答。
            if not ai_message.tool_calls:
                final_text = self._stringify_content(ai_message.content)
                break

            # 如果有多个工具调用，就按顺序执行并把 ToolMessage 回填给模型。
            for tool_call in ai_message.tool_calls:
                tool_message = await self._execute_tool(tool_call)
                runtime_messages.append(tool_message)
                turn_messages.append(tool_message)
        else:
            # for/else：只有当循环没有 break 时才会进入这里。
            final_text = "已达到最大工具轮数，但未获得最终答案。"
            turn_messages.append(AIMessage(content=final_text))

        # 保存完整历史消息，注意这里保存的是“未裁剪版本”。
        all_messages = [*stored_messages, *turn_messages]
        self.session_store.save_messages(session_id, all_messages)

        # 更新结构化记忆，让后续轮次可以复用。
        self.memory.update_after_turn(session_id, all_messages, user_input, final_text or "(空响应)")

        return final_text or "(空响应)"

    async def aclose(self) -> None:
        """异步关闭 Agent 持有的外部资源。

        当前主要是关闭 MCP 连接堆栈，避免进程退出前资源泄漏。
        """
        for stack in self._mcp_stacks.values():
            await stack.aclose()
        self._mcp_stacks.clear()

    async def _execute_tool(self, tool_call: dict[str, Any]) -> ToolMessage:
        """执行模型请求的某个工具，并把结果封装回 ToolMessage。

        参数：
        - tool_call: LangChain/模型产出的工具调用描述，至少包含 `name`、`id`、`args`

        返回：
        - ToolMessage，后续会继续送回模型
        """
        name = tool_call["name"]
        tool = self.tool_map.get(name)

        if tool is None:
            content = f"错误：未知工具“{name}”"
            return ToolMessage(content=content, tool_call_id=tool_call["id"], name=name)

        try:
            result = await tool.ainvoke(tool_call.get("args", {}))
        except Exception as exc:
            result = f"执行 {name} 时出错：{exc}"

        return ToolMessage(content=str(result), tool_call_id=tool_call["id"], name=name)

    @staticmethod
    def _stringify_content(content: Any) -> str:
        """把模型返回内容统一整理成字符串。

        模型可能返回：
        - 纯字符串
        - 多段内容列表
        - 其他结构

        这个函数会尽量提取文本部分，方便最终输出到 CLI。
        """
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part).strip()

        return str(content).strip()
