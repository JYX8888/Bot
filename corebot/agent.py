from __future__ import annotations

from typing import Any

from corebot.bootstrap import bootstrap_local_langchain
from corebot.config import BotSettings
from corebot.prompts import build_system_prompt
from corebot.session_store import SessionStore
from corebot.tools import build_file_tools, build_shell_tool

bootstrap_local_langchain()

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI


class CoreBotAgent:
    def __init__(self, settings: BotSettings):
        settings.validate_runtime()
        self.settings = settings
        self.session_store = SessionStore(settings.sessions_dir)
        self.tools = build_file_tools(settings.workspace, settings.max_tool_output_chars)
        self.tools.append(
            build_shell_tool(
                settings.workspace,
                settings.shell_timeout,
                settings.max_tool_output_chars,
            )
        )
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.model = ChatOpenAI(
            model=settings.model,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
        self.model_with_tools = self.model.bind_tools(self.tools)

    async def ask(self, user_input: str, session_id: str = "default") -> str:
        stored_messages = self.session_store.load_messages(session_id)
        system_message = SystemMessage(content=build_system_prompt(self.settings))
        turn_messages: list[BaseMessage] = [HumanMessage(content=user_input)]
        runtime_messages: list[BaseMessage] = [system_message, *stored_messages, *turn_messages]

        final_text = ""
        for _ in range(self.settings.max_iterations):
            ai_message = await self.model_with_tools.ainvoke(runtime_messages)
            runtime_messages.append(ai_message)
            turn_messages.append(ai_message)

            if not ai_message.tool_calls:
                final_text = self._stringify_content(ai_message.content)
                break

            for tool_call in ai_message.tool_calls:
                tool_message = await self._execute_tool(tool_call)
                runtime_messages.append(tool_message)
                turn_messages.append(tool_message)
        else:
            final_text = "Reached the maximum tool iterations without a final answer."
            turn_messages.append(AIMessage(content=final_text))

        self.session_store.save_messages(session_id, [*stored_messages, *turn_messages])
        return final_text or "(empty response)"

    async def _execute_tool(self, tool_call: dict[str, Any]) -> ToolMessage:
        name = tool_call["name"]
        tool = self.tool_map.get(name)
        if tool is None:
            content = f"Error: Unknown tool '{name}'"
            return ToolMessage(content=content, tool_call_id=tool_call["id"], name=name)
        try:
            result = await tool.ainvoke(tool_call.get("args", {}))
        except Exception as exc:
            result = f"Error executing {name}: {exc}"
        return ToolMessage(content=str(result), tool_call_id=tool_call["id"], name=name)

    @staticmethod
    def _stringify_content(content: Any) -> str:
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
