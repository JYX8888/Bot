"""MCP 连接与工具包装逻辑。

这个模块的作用是把外部 MCP Server 提供的能力转换成 LangChain 工具，
从而让模型可以像调用本地工具一样调用 MCP 工具、资源和 prompt。
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import httpx

from corebot.bootstrap import bootstrap_local_langchain

bootstrap_local_langchain()

from langchain_core.tools import StructuredTool


def _extract_nullable_branch(options: Any) -> tuple[dict[str, Any], bool] | None:
    """识别 `oneOf/anyOf` 中的“单一非空类型 + null”结构。"""
    if not isinstance(options, list):
        return None

    non_null: list[dict[str, Any]] = []
    saw_null = False
    for option in options:
        if not isinstance(option, dict):
            return None
        if option.get("type") == "null":
            saw_null = True
            continue
        non_null.append(option)

    if saw_null and len(non_null) == 1:
        return non_null[0], True
    return None


def normalize_schema_for_tool(schema: Any) -> dict[str, Any]:
    """把 MCP 工具输入 schema 规范化成更适合 LangChain 使用的形式。"""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "required": []}

    normalized = dict(schema)
    raw_type = normalized.get("type")

    # 兼容 `type: ["string", "null"]` 这种写法。
    if isinstance(raw_type, list):
        non_null = [item for item in raw_type if item != "null"]
        if "null" in raw_type and len(non_null) == 1:
            normalized["type"] = non_null[0]
            normalized["nullable"] = True

    # 兼容 `oneOf` / `anyOf` 中一个非空类型 + null 的写法。
    for key in ("oneOf", "anyOf"):
        nullable_branch = _extract_nullable_branch(normalized.get(key))
        if nullable_branch is not None:
            branch, _ = nullable_branch
            merged = {k: v for k, v in normalized.items() if k != key}
            merged.update(branch)
            normalized = merged
            normalized["nullable"] = True
            break

    # 递归处理对象属性。
    if "properties" in normalized and isinstance(normalized["properties"], dict):
        normalized["properties"] = {
            name: normalize_schema_for_tool(prop) if isinstance(prop, dict) else prop
            for name, prop in normalized["properties"].items()
        }

    # 递归处理数组元素。
    if "items" in normalized and isinstance(normalized["items"], dict):
        normalized["items"] = normalize_schema_for_tool(normalized["items"])

    if normalized.get("type") == "object":
        normalized.setdefault("properties", {})
        normalized.setdefault("required", [])

    return normalized


async def connect_mcp_servers(mcp_servers: dict[str, dict]) -> tuple[list, dict[str, AsyncExitStack]]:
    """连接所有已配置 MCP 服务并返回 LangChain 工具列表。

    参数：
    - mcp_servers: MCP 配置字典，键是服务名，值是连接参数

    返回：
    - 第一个返回值：所有 MCP 工具列表
    - 第二个返回值：每个服务对应的 `AsyncExitStack`，用于后续关闭连接
    """
    if not mcp_servers:
        return [], {}

    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    async def _connect_one(name: str, cfg: dict) -> tuple[list, AsyncExitStack | None]:
        """连接单个 MCP 服务。"""
        stack = AsyncExitStack()
        await stack.__aenter__()

        transport_type = cfg.get("type")

        # 如果用户没显式写 type，就根据 command/url 推断。
        if not transport_type:
            if cfg.get("command"):
                transport_type = "stdio"
            elif cfg.get("url"):
                transport_type = (
                    "sse" if str(cfg["url"]).rstrip("/").endswith("/sse") else "streamableHttp"
                )
            else:
                await stack.aclose()
                return [], None

        try:
            if transport_type == "stdio":
                params = StdioServerParameters(
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=cfg.get("env") or None,
                )
                read, write = await stack.enter_async_context(stdio_client(params))

            elif transport_type == "sse":

                def httpx_client_factory(
                    headers: dict[str, str] | None = None,
                    timeout: httpx.Timeout | None = None,
                    auth: httpx.Auth | None = None,
                ) -> httpx.AsyncClient:
                    """为 SSE 客户端构造 httpx 异步客户端。"""
                    merged_headers = {
                        "Accept": "application/json, text/event-stream",
                        **(cfg.get("headers") or {}),
                        **(headers or {}),
                    }
                    return httpx.AsyncClient(
                        headers=merged_headers or None,
                        follow_redirects=True,
                        timeout=timeout,
                        auth=auth,
                    )

                read, write = await stack.enter_async_context(
                    sse_client(cfg["url"], httpx_client_factory=httpx_client_factory)
                )

            elif transport_type == "streamableHttp":
                http_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=cfg.get("headers") or None,
                        follow_redirects=True,
                        timeout=None,
                    )
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(cfg["url"], http_client=http_client)
                )

            else:
                await stack.aclose()
                return [], None

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            enabled = set(cfg.get("enabledTools", cfg.get("enabled_tools", ["*"])))
            allow_all = "*" in enabled or not enabled
            timeout = int(cfg.get("toolTimeout", cfg.get("tool_timeout", 30)))
            tools: list = []

            # 1. MCP 工具 -> LangChain 工具
            tool_defs = await session.list_tools()
            for tool_def in tool_defs.tools:
                wrapped_name = f"mcp_{name}_{tool_def.name}"
                if not allow_all and tool_def.name not in enabled and wrapped_name not in enabled:
                    continue

                async def _call_tool(_tool_name: str = tool_def.name, **kwargs: Any) -> str:
                    """执行单个 MCP 工具。"""
                    result = await asyncio.wait_for(
                        session.call_tool(_tool_name, arguments=kwargs),
                        timeout=timeout,
                    )
                    parts = []
                    for block in result.content:
                        if isinstance(block, types.TextContent):
                            parts.append(block.text)
                        else:
                            parts.append(str(block))
                    return "\n".join(parts) or "(无输出)"

                tools.append(
                    StructuredTool.from_function(
                        coroutine=_call_tool,
                        name=wrapped_name,
                        description=tool_def.description or f"MCP 工具 {tool_def.name}",
                        args_schema=normalize_schema_for_tool(
                            tool_def.inputSchema or {"type": "object", "properties": {}}
                        ),
                        infer_schema=False,
                    )
                )

            # 2. MCP 资源 -> 零参数或固定参数 LangChain 工具
            try:
                resources = await session.list_resources()
                for resource in resources.resources:
                    resource_name = f"mcp_{name}_resource_{resource.name}"

                    async def _read_resource(_uri: str = resource.uri) -> str:
                        """读取单个 MCP 资源。"""
                        result = await asyncio.wait_for(
                            session.read_resource(_uri),
                            timeout=timeout,
                        )
                        parts = []
                        for block in result.contents:
                            if hasattr(block, "text"):
                                parts.append(block.text)
                            elif hasattr(block, "blob"):
                                parts.append(f"[二进制资源：{len(block.blob)} 字节]")
                            else:
                                parts.append(str(block))
                        return "\n".join(parts) or "(无输出)"

                    tools.append(
                        StructuredTool.from_function(
                            coroutine=_read_resource,
                            name=resource_name,
                            description=resource.description or f"MCP 资源 {resource.name}",
                            args_schema={"type": "object", "properties": {}, "required": []},
                            infer_schema=False,
                        )
                    )
            except Exception:
                # 资源能力不是所有 MCP 服务都支持，因此这里容错处理。
                pass

            # 3. MCP prompt -> LangChain 工具
            try:
                prompts = await session.list_prompts()
                for prompt in prompts.prompts:
                    prompt_name = f"mcp_{name}_prompt_{prompt.name}"
                    properties = {}
                    required = []

                    for argument in prompt.arguments or []:
                        properties[argument.name] = {
                            "type": "string",
                            "description": getattr(argument, "description", "") or argument.name,
                        }
                        if argument.required:
                            required.append(argument.name)

                    async def _read_prompt(_prompt_name: str = prompt.name, **kwargs: Any) -> str:
                        """读取并渲染单个 MCP prompt。"""
                        result = await asyncio.wait_for(
                            session.get_prompt(_prompt_name, arguments=kwargs),
                            timeout=timeout,
                        )
                        parts = []
                        for message in result.messages:
                            content = getattr(message.content, "text", None)
                            if content:
                                parts.append(content)
                            else:
                                parts.append(str(message))
                        return "\n".join(parts) or "(无输出)"

                    tools.append(
                        StructuredTool.from_function(
                            coroutine=_read_prompt,
                            name=prompt_name,
                            description=prompt.description or f"MCP 提示 {prompt.name}",
                            args_schema={
                                "type": "object",
                                "properties": properties,
                                "required": required,
                            },
                            infer_schema=False,
                        )
                    )
            except Exception:
                pass

            return tools, stack
        except Exception:
            # 一旦连接过程出错，确保释放已经打开的资源。
            await stack.aclose()
            return [], None

    all_tools: list = []
    stacks: dict[str, AsyncExitStack] = {}

    for name, cfg in mcp_servers.items():
        tools, stack = await _connect_one(name, cfg)
        all_tools.extend(tools)
        if stack is not None:
            stacks[name] = stack

    return all_tools, stacks
