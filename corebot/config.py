"""corebot 的配置定义与加载逻辑。

这个文件的主要目标是把多来源配置统一整理成一个 `BotSettings` 对象。
当前支持的配置来源包括：
1. 代码里的默认值
2. 环境变量
3. 项目根目录的 `bot.local.json`

后续如果你想增加新的配置项，通常就是先在 `BotSettings` 里加字段，
再在 `load()` 方法里把它从环境变量或 JSON 配置里读取出来。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


class BotSettings(BaseModel):
    """运行时配置对象。

    这里的每个字段都会在 Agent 初始化时被使用，因此这个类相当于整个项目的
    “配置总表”。
    """

    # 当前要操作的工作区路径。所有文件工具、Shell 工具都以它为边界。
    workspace: Path

    # 项目的数据目录，用于存放会话、记忆等持久化数据。
    data_dir: Path

    # 模型名称，例如 `gpt-4o-mini` 或 OpenAI 兼容服务上的其他模型名。
    model: str = "gpt-4o-mini"

    # 模型服务的鉴权信息。
    api_key: str | None = None

    # 兼容 OpenAI 接口的服务地址；为空时走官方默认地址。
    base_url: str | None = None

    # 温度越高，模型输出越发散；越低越稳定。
    temperature: float = 0.0

    # 模型最大输出 token 数。为空时使用服务端默认值。
    max_tokens: int | None = None

    # 一轮请求里最多允许模型调用多少轮工具。
    max_iterations: int = 8

    # Shell 工具的默认超时时间，单位秒。
    shell_timeout: int = 60

    # 单次工具输出最多允许保留多少字符，避免上下文过大。
    max_tool_output_chars: int = 8000

    # 历史原始消息窗口大小，超出后会被裁剪。
    max_history_messages: int = 12

    # 单轮最多召回多少条结构化记忆。
    max_recalled_memories: int = 6

    # 会话记忆里保留多少条最近请求。
    max_session_requests: int = 6

    # MCP 服务配置，键通常是服务名，值是传输参数。
    mcp_servers: dict[str, dict] = Field(default_factory=dict)

    # 内置技能目录，可选。
    builtin_skills_dir: Path | None = None

    # 额外技能目录列表，可选。
    extra_skills_dirs: list[Path] = Field(default_factory=list)

    @staticmethod
    def _load_json_config(project_root: Path) -> dict:
        """从项目配置文件读取 JSON 配置。

        参数：
        - project_root: 项目根目录，用于推导默认的 `bot.local.json` 位置

        返回：
        - 解析后的字典；如果文件不存在，则返回空字典
        """
        config_path = Path(
            os.environ.get("BOT_CONFIG_FILE", project_root / "bot.local.json")
        ).expanduser()

        if not config_path.exists():
            return {}

        # 使用 utf-8-sig 兼容带 BOM 的 JSON 文件。
        return json.loads(config_path.read_text(encoding="utf-8-sig"))

    @staticmethod
    def _load_provider_defaults(config: dict) -> tuple[dict, dict]:
        """从配置中提取 provider 块和默认 agent 块。"""
        providers = config.get("providers", {})
        defaults = config.get("agents", {}).get("defaults", {})
        provider_name = defaults.get("provider")
        provider_block = providers.get(provider_name, {}) if provider_name else {}
        return provider_block, defaults

    @staticmethod
    def _load_skills_settings(config: dict) -> tuple[Path | None, list[Path]]:
        """读取 Skills 相关配置。"""
        skills_cfg = config.get("skills", {})
        builtin_dir = skills_cfg.get("builtinDir") or skills_cfg.get("builtin_dir")
        dirs = skills_cfg.get("dirs", [])

        # 额外支持从环境变量注入多个 Skills 目录。
        env_dirs = os.environ.get("BOT_SKILLS_DIRS")
        if env_dirs:
            dirs = list(dirs) + [part for part in env_dirs.split(os.pathsep) if part]

        builtin_path = Path(builtin_dir).expanduser().resolve() if builtin_dir else None
        resolved_dirs = [Path(item).expanduser().resolve() for item in dirs]
        return builtin_path, resolved_dirs

    @staticmethod
    def _load_mcp_servers(config: dict) -> dict[str, dict]:
        """读取 MCP 服务配置。"""
        return config.get("mcpServers", config.get("mcp_servers", {}))

    @staticmethod
    def _load_memory_settings(config: dict) -> dict:
        """读取记忆系统相关配置。"""
        return config.get("memory", {})

    @classmethod
    def load(cls, workspace: Path | None = None) -> "BotSettings":
        """把环境变量、JSON 配置和默认值合并成最终运行配置。

        参数：
        - workspace: 可选。若传入则使用指定工作区，否则默认使用当前目录

        返回：
        - 一个完整的 `BotSettings` 实例
        """
        project_root = Path(__file__).resolve().parents[1]
        workspace_path = (workspace or Path.cwd()).resolve()
        config = cls._load_json_config(project_root)

        provider_block, defaults = cls._load_provider_defaults(config)
        builtin_skills_dir, extra_skills_dirs = cls._load_skills_settings(config)
        memory_cfg = cls._load_memory_settings(config)

        # data_dir 允许通过环境变量覆写，方便不同环境分开存储数据。
        data_dir = Path(os.environ.get("BOT_DATA_DIR", project_root / "data")).resolve()

        # API Key / Base URL 同时兼容环境变量和 JSON 配置。
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

        # 某些兼容 OpenAI 的接口必须传 key，即便它不校验；这里给一个占位值。
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
            max_history_messages=int(
                os.environ.get(
                    "BOT_MAX_HISTORY_MESSAGES",
                    memory_cfg.get("historyWindow", memory_cfg.get("history_window", 12)),
                )
            ),
            max_recalled_memories=int(
                os.environ.get(
                    "BOT_MAX_RECALLED_MEMORIES",
                    memory_cfg.get("maxRecalledItems", memory_cfg.get("max_recalled_items", 6)),
                )
            ),
            max_session_requests=int(
                os.environ.get(
                    "BOT_MAX_SESSION_REQUESTS",
                    memory_cfg.get("maxSessionRequests", memory_cfg.get("max_session_requests", 6)),
                )
            ),
            mcp_servers=cls._load_mcp_servers(config),
            builtin_skills_dir=builtin_skills_dir,
            extra_skills_dirs=extra_skills_dirs,
        )

    @property
    def sessions_dir(self) -> Path:
        """会话消息目录。"""
        return self.data_dir / "sessions"

    @property
    def memory_dir(self) -> Path:
        """结构化记忆目录。"""
        return self.data_dir / "memory"

    def validate_runtime(self) -> None:
        """校验当前配置是否满足运行前提。"""
        if not self.api_key:
            raise ValueError(
                "缺少 API Key。请设置 BOT_API_KEY 或 OPENAI_API_KEY；"
                "如果你接的是兼容 OpenAI 的本地接口，请同时设置 BOT_BASE_URL。"
            )
