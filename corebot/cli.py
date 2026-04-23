from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from corebot.config import BotSettings

app = typer.Typer(help="Minimal LangChain-based coding bot")


def _build_agent(workspace: Path | None):
    from corebot.agent import CoreBotAgent

    settings = BotSettings.load(workspace)
    return CoreBotAgent(settings)


async def _interactive_chat(agent, session_id: str) -> None:
    typer.echo(f"corebot ready. workspace={agent.settings.workspace}")
    typer.echo("Type 'exit' or 'quit' to stop.\n")
    while True:
        try:
            user_input = input("You> ").strip()
        except EOFError:
            typer.echo("")
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break
        reply = await agent.ask(user_input, session_id=session_id)
        typer.echo(f"Bot> {reply}\n")


@app.command()
def chat(
    message: str | None = typer.Argument(None, help="Optional one-shot message"),
    workspace: Path | None = typer.Option(None, help="Workspace the bot can operate on"),
    session: str = typer.Option("default", help="Session id"),
) -> None:
    """Run one chat turn or start an interactive session."""
    agent = _build_agent(workspace)
    if message:
        reply = asyncio.run(agent.ask(message, session_id=session))
        typer.echo(reply)
        return
    asyncio.run(_interactive_chat(agent, session_id=session))


@app.command("clear-session")
def clear_session(
    session_id: str = typer.Argument(..., help="Session id to delete"),
    workspace: Path | None = typer.Option(None, help="Workspace used to derive the data dir"),
) -> None:
    """Delete a saved session file."""
    from corebot.session_store import SessionStore

    settings = BotSettings.load(workspace)
    deleted = SessionStore(settings.sessions_dir).delete(session_id)
    if deleted:
        typer.echo(f"Deleted session '{session_id}'.")
    else:
        typer.echo(f"Session '{session_id}' does not exist.")


@app.command()
def status(workspace: Path | None = typer.Option(None, help="Workspace to inspect")) -> None:
    """Show effective runtime settings."""
    settings = BotSettings.load(workspace)
    typer.echo(f"workspace: {settings.workspace}")
    typer.echo(f"data_dir: {settings.data_dir}")
    typer.echo(f"sessions_dir: {settings.sessions_dir}")
    typer.echo(f"model: {settings.model}")
    typer.echo(f"base_url: {settings.base_url or '(default OpenAI)'}")
    typer.echo(f"temperature: {settings.temperature}")
    typer.echo(f"max_tokens: {settings.max_tokens if settings.max_tokens is not None else '(provider default)'}")
