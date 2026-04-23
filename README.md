# corebot

A minimal bot project rebuilt around the LangChain ecosystem and focused on the core local workflow:

- CLI chat loop
- persistent local sessions
- file read/write/search tools
- guarded shell execution inside a workspace
- OpenAI-compatible model access through `langchain_openai.ChatOpenAI`

## Project layout

- `corebot/agent.py`: tool-calling loop and model integration
- `corebot/cli.py`: CLI entrypoints
- `corebot/session_store.py`: persistent session storage
- `corebot/tools/`: local workspace tools

## Local LangChain source checkout

This project auto-detects the sibling `../langchain` source tree and adds these local packages to `sys.path` when installed wheels are not available:

- `langchain_core`
- `langchain_openai`

That keeps the project aligned with the local `D:\xiangmu\agent\langchain` checkout.

## Environment variables

- `BOT_MODEL`: model name, default `gpt-4o-mini`
- `BOT_API_KEY`: API key; falls back to `OPENAI_API_KEY`
- `BOT_BASE_URL`: optional OpenAI-compatible base URL
- `BOT_MAX_TOKENS`: optional max output tokens
- `BOT_DATA_DIR`: overrides the default local data directory
- `BOT_MAX_ITERATIONS`: max tool loop turns, default `8`
- `BOT_SHELL_TIMEOUT`: shell timeout in seconds, default `60`
- `BOT_CONFIG_FILE`: optional path to a local JSON config file; defaults to `bot.local.json`

If you use a local OpenAI-compatible endpoint, `BOT_API_KEY` can be omitted and the runtime will use `EMPTY`.

## Local JSON config

You can also drop a local `bot.local.json` next to the project root. `corebot` understands the `providers.custom` and `agents.defaults` parts of a nanobot-style config, so you can reuse the same model/api settings without exporting environment variables every time.

## Run

From `D:\xiangmu\agent\bot`:

```powershell
$env:BOT_API_KEY = "your-key"
python -m corebot status --workspace D:\xiangmu\agent\nanobot-main
python -m corebot chat --workspace D:\xiangmu\agent\nanobot-main
```

Single-turn mode:

```powershell
python -m corebot chat "summarize this repository" --workspace D:\xiangmu\agent\nanobot-main
```

Clear a saved session:

```powershell
python -m corebot clear-session default
```
