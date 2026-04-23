from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel


class BotSettings(BaseModel):
    workspace: Path
    data_dir: Path
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    max_iterations: int = 8
    shell_timeout: int = 60
    max_tool_output_chars: int = 8000

    @staticmethod
    def _load_json_config(project_root: Path) -> dict:
        config_path = Path(
            os.environ.get("BOT_CONFIG_FILE", project_root / "bot.local.json")
        ).expanduser()
        if not config_path.exists():
            return {}
        return json.loads(config_path.read_text(encoding="utf-8-sig"))

    @staticmethod
    def _nanobot_defaults(config: dict) -> tuple[dict, dict]:
        providers = config.get("providers", {})
        defaults = config.get("agents", {}).get("defaults", {})
        provider_name = defaults.get("provider")
        provider_block = providers.get(provider_name, {}) if provider_name else {}
        return provider_block, defaults

    @classmethod
    def load(cls, workspace: Path | None = None) -> "BotSettings":
        project_root = Path(__file__).resolve().parents[1]
        workspace_path = (workspace or Path.cwd()).resolve()
        config = cls._load_json_config(project_root)
        provider_block, defaults = cls._nanobot_defaults(config)
        data_dir = Path(os.environ.get("BOT_DATA_DIR", project_root / "data")).resolve()
        api_key = (
            os.environ.get("BOT_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or provider_block.get("apiKey")
        )
        base_url = (
            os.environ.get("BOT_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
            or provider_block.get("apiBase")
        )
        if not api_key and base_url:
            api_key = "EMPTY"
        return cls(
            workspace=workspace_path,
            data_dir=data_dir,
            model=os.environ.get("BOT_MODEL", defaults.get("model", "gpt-4o-mini")),
            api_key=api_key,
            base_url=base_url,
            temperature=float(os.environ.get("BOT_TEMPERATURE", defaults.get("temperature", "0"))),
            max_tokens=(
                int(os.environ["BOT_MAX_TOKENS"])
                if os.environ.get("BOT_MAX_TOKENS")
                else (
                    int(defaults["maxTokens"])
                    if defaults.get("maxTokens") is not None
                    else None
                )
            ),
            max_iterations=int(os.environ.get("BOT_MAX_ITERATIONS", "8")),
            shell_timeout=int(os.environ.get("BOT_SHELL_TIMEOUT", "60")),
            max_tool_output_chars=int(os.environ.get("BOT_MAX_TOOL_OUTPUT_CHARS", "8000")),
        )

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    def validate_runtime(self) -> None:
        if not self.api_key:
            raise ValueError(
                "Missing API key. Set BOT_API_KEY or OPENAI_API_KEY. "
                "If you use a local OpenAI-compatible endpoint, set BOT_BASE_URL so the runtime can use a dummy key."
            )
