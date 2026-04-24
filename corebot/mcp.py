from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import httpx

from corebot.bootstrap import bootstrap_local_langchain

bootstrap_local_langchain()

from langchain_core.tools import StructuredTool


def _extract_nullable_branch(options: Any) -> tuple[dict[str, Any], bool] | None:
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
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "required": []}

    normalized = dict(schema)
    raw_type = normalized.get("type")
    if isinstance(raw_type, list):
        non_null = [item for item in raw_type if item != "null"]
        if "null" in raw_type and len(non_null) == 1:
            normalized["type"] = non_null[0]
            normalized["nullable"] = True

    for key in ("oneOf", "anyOf"):
        nullable_branch = _extract_nullable_branch(normalized.get(key))
        if nullable_branch is not None:
            branch, _ = nullable_branch
            merged = {k: v for k, v in normalized.items() if k != key}
            merged.update(branch)
            normalized = merged
            normalized["nullable"] = True
            break

    if "properties" in normalized and isinstance(normalized["properties"], dict):
        normalized["properties"] = {
            name: normalize_schema_for_tool(prop) if isinstance(prop, dict) else prop
            for name, prop in normalized["properties"].items()
        }

    if "items" in normalized and isinstance(normalized["items"], dict):
        normalized["items"] = normalize_schema_for_tool(normalized["items"])

    if normalized.get("type") == "object":
        normalized.setdefault("properties", {})
        normalized.setdefault("required", [])
    return normalized


async def connect_mcp_servers(mcp_servers: dict[str, dict]) -> tuple[list, dict[str, AsyncExitStack]]:
    """Connect configured MCP servers and expose tools/resources/prompts as LangChain tools."""
    if not mcp_servers:
        return [], {}

    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client

    async def _connect_one(name: str, cfg: dict) -> tuple[list, AsyncExitStack | None]:
        stack = AsyncExitStack()
        await stack.__aenter__()

        transport_type = cfg.get("type")
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

            tool_defs = await session.list_tools()
            for tool_def in tool_defs.tools:
                wrapped_name = f"mcp_{name}_{tool_def.name}"
                if not allow_all and tool_def.name not in enabled and wrapped_name not in enabled:
                    continue

                async def _call_tool(_tool_name: str = tool_def.name, **kwargs: Any) -> str:
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
                    return "\n".join(parts) or "(no output)"

                tools.append(
                    StructuredTool.from_function(
                        coroutine=_call_tool,
                        name=wrapped_name,
                        description=tool_def.description or f"MCP tool {tool_def.name}",
                        args_schema=normalize_schema_for_tool(
                            tool_def.inputSchema or {"type": "object", "properties": {}}
                        ),
                        infer_schema=False,
                    )
                )

            try:
                resources = await session.list_resources()
                for resource in resources.resources:
                    resource_name = f"mcp_{name}_resource_{resource.name}"

                    async def _read_resource(_uri: str = resource.uri) -> str:
                        result = await asyncio.wait_for(
                            session.read_resource(_uri),
                            timeout=timeout,
                        )
                        parts = []
                        for block in result.contents:
                            if hasattr(block, "text"):
                                parts.append(block.text)
                            elif hasattr(block, "blob"):
                                parts.append(f"[Binary resource: {len(block.blob)} bytes]")
                            else:
                                parts.append(str(block))
                        return "\n".join(parts) or "(no output)"

                    tools.append(
                        StructuredTool.from_function(
                            coroutine=_read_resource,
                            name=resource_name,
                            description=resource.description or f"MCP resource {resource.name}",
                            args_schema={"type": "object", "properties": {}, "required": []},
                            infer_schema=False,
                        )
                    )
            except Exception:
                pass

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
                        return "\n".join(parts) or "(no output)"

                    tools.append(
                        StructuredTool.from_function(
                            coroutine=_read_prompt,
                            name=prompt_name,
                            description=prompt.description or f"MCP prompt {prompt.name}",
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
