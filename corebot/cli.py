"""命令行入口。

这个文件把 `CoreBotAgent` 暴露成几个 CLI 命令，方便在终端里直接使用。
主要命令包括：
- `chat`: 交互式对话或单轮提问
- `clear-session`: 删除某个会话及其记忆
- `status`: 查看当前生效配置
- `list-skills`: 查看可用技能
- `show-memory`: 查看当前已经沉淀的结构化记忆
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from corebot.config import BotSettings

# Typer 应用对象。它会自动把 `@app.command()` 标记的函数暴露成 CLI 子命令。
app = typer.Typer(help="基于 LangChain 的精简编码机器人")


def _build_agent(workspace: Path | None):
    """根据工作区参数创建 Agent。"""
    from corebot.agent import CoreBotAgent

    settings = BotSettings.load(workspace)
    return CoreBotAgent(settings)


async def _interactive_chat(agent, session_id: str) -> None:
    """运行交互式聊天循环。"""
    typer.echo(f"corebot 已就绪。工作区：{agent.settings.workspace}")
    typer.echo("输入 'exit' 或 'quit' 结束。\n")
    try:
        while True:
            try:
                user_input = input("你> ").strip()
            except EOFError:
                typer.echo("")
                break

            if not user_input:
                continue

            if user_input.lower() in {"exit", "quit"}:
                break

            reply = await agent.ask(user_input, session_id=session_id)
            typer.echo(f"机器人> {reply}\n")
    finally:
        await agent.aclose()


@app.command()
def chat(
    message: str | None = typer.Argument(None, help="可选的一次性消息"),
    workspace: Path | None = typer.Option(None, help="机器人可操作的工作区"),
    session: str = typer.Option("default", help="会话 ID"),
) -> None:
    """执行一次对话或启动交互式会话。"""
    agent = _build_agent(workspace)

    if message:

        async def _run_once() -> str:
            """把单轮问答包装成一个协程，便于 `asyncio.run()` 调用。"""
            try:
                return await agent.ask(message, session_id=session)
            finally:
                await agent.aclose()

        reply = asyncio.run(_run_once())
        typer.echo(reply)
        return

    asyncio.run(_interactive_chat(agent, session_id=session))


@app.command("clear-session")
def clear_session(
    session_id: str = typer.Argument(..., help="要删除的会话 ID"),
    workspace: Path | None = typer.Option(None, help="用于推导数据目录的工作区"),
) -> None:
    """删除已保存的会话文件和对应记忆。"""
    from corebot.memory import MemoryManager
    from corebot.session_store import SessionStore

    settings = BotSettings.load(workspace)

    store_deleted = SessionStore(settings.sessions_dir).delete(session_id)
    memory_deleted = MemoryManager(
        settings.memory_dir,
        max_history_messages=settings.max_history_messages,
        max_recalled_memories=settings.max_recalled_memories,
        max_session_requests=settings.max_session_requests,
    ).delete_session_record(session_id)

    if store_deleted or memory_deleted:
        typer.echo(f"已删除会话 '{session_id}' 及其对应记忆。")
    else:
        typer.echo(f"会话 '{session_id}' 不存在。")


@app.command()
def status(workspace: Path | None = typer.Option(None, help="要查看的工作区")) -> None:
    """显示当前生效的运行配置。"""
    settings = BotSettings.load(workspace)

    typer.echo(f"工作区: {settings.workspace}")
    typer.echo(f"数据目录: {settings.data_dir}")
    typer.echo(f"会话目录: {settings.sessions_dir}")
    typer.echo(f"记忆目录: {settings.memory_dir}")
    typer.echo(f"模型: {settings.model}")
    typer.echo(f"接口地址: {settings.base_url or '(默认 OpenAI)'}")
    typer.echo(f"温度: {settings.temperature}")
    typer.echo(f"最大输出: {settings.max_tokens if settings.max_tokens is not None else '(由服务端默认值决定)'}")
    typer.echo(f"最大工具轮数: {settings.max_iterations}")
    typer.echo(f"历史消息窗口: {settings.max_history_messages}")
    typer.echo(f"最大召回记忆数: {settings.max_recalled_memories}")
    typer.echo(f"MCP 服务数: {len(settings.mcp_servers)}")

    skill_dirs = [str(settings.workspace / "skills")]
    if settings.builtin_skills_dir:
        skill_dirs.append(str(settings.builtin_skills_dir))
    skill_dirs.extend(str(path) for path in settings.extra_skills_dirs)
    typer.echo(f"技能目录: {', '.join(skill_dirs)}")


@app.command("list-skills")
def list_skills(workspace: Path | None = typer.Option(None, help="要查看的工作区")) -> None:
    """列出可用技能。"""
    from corebot.skills import SkillsManager

    settings = BotSettings.load(workspace)
    manager = SkillsManager(
        settings.workspace,
        builtin_skills_dir=settings.builtin_skills_dir,
        extra_skills_dirs=settings.extra_skills_dirs,
    )
    skills = manager.list_skills()
    if not skills:
        typer.echo("未找到任何技能。")
        return

    for entry in skills:
        typer.echo(
            f"{entry['name']}: {entry['description']} "
            f"(优先级 {entry['priority']}, 路径 {entry['path']})"
        )


@app.command("show-memory")
def show_memory(
    session: str = typer.Option("default", help="要查看的会话 ID"),
    workspace: Path | None = typer.Option(None, help="用于定位数据目录的工作区"),
) -> None:
    """显示当前会话、用户和项目的记忆内容。"""
    from corebot.memory import MemoryManager

    settings = BotSettings.load(workspace)
    manager = MemoryManager(
        settings.memory_dir,
        max_history_messages=settings.max_history_messages,
        max_recalled_memories=settings.max_recalled_memories,
        max_session_requests=settings.max_session_requests,
    )

    session_record = manager.load_session_record(session)
    user_profile = manager.load_user_profile()
    project_profile = manager.load_project_profile()

    typer.echo(f"会话: {session}")
    typer.echo(f"会话摘要: {session_record.summary or '(空)'}")
    typer.echo(f"最近请求: {'；'.join(session_record.recent_requests) if session_record.recent_requests else '(空)'}")
    typer.echo(f"会话决策: {'；'.join(session_record.decisions) if session_record.decisions else '(空)'}")
    typer.echo(f"会话待办: {'；'.join(session_record.todos) if session_record.todos else '(空)'}")
    typer.echo(f"用户偏好: {'；'.join(user_profile.preferences) if user_profile.preferences else '(空)'}")
    typer.echo(f"用户流程: {'；'.join(user_profile.workflows) if user_profile.workflows else '(空)'}")
    typer.echo(f"用户约束: {'；'.join(user_profile.constraints) if user_profile.constraints else '(空)'}")
    typer.echo(f"项目摘要: {project_profile.summary or '(空)'}")
    typer.echo(f"项目事实: {'；'.join(project_profile.facts) if project_profile.facts else '(空)'}")
    typer.echo(f"项目决策: {'；'.join(project_profile.decisions) if project_profile.decisions else '(空)'}")
