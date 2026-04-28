"""配置加载相关测试。"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import unittest

from corebot.config import BotSettings


class ConfigTest(unittest.TestCase):
    """验证 `BotSettings.load()` 的配置合并逻辑。"""

    def _make_dir(self, name: str) -> Path:
        """创建测试临时目录，并在测试结束后自动清理。"""
        path = Path(__file__).resolve().parent / ".config_tmp" / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_loads_json_config_and_memory_settings(self) -> None:
        """验证 JSON 配置里的 provider、skills、memory 设置都能正确加载。"""
        workspace = self._make_dir("workspace")
        config_path = self._make_dir("config") / "bot.local.json"
        config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "custom": {
                            "apiKey": "test-key",
                            "apiBase": "https://example.invalid/v1/",
                        }
                    },
                    "agents": {
                        "defaults": {
                            "provider": "custom",
                            "model": "demo-model",
                            "temperature": 0.7,
                            "maxTokens": 2048,
                        }
                    },
                    "mcpServers": {
                        "demo": {
                            "type": "stdio",
                            "command": "python",
                            "args": ["demo.py"],
                        }
                    },
                    "skills": {
                        "builtinDir": str(workspace / "builtin_skills"),
                        "dirs": [str(workspace / "shared_skills")],
                    },
                    "memory": {
                        "historyWindow": 9,
                        "maxRecalledItems": 4,
                        "maxSessionRequests": 5,
                    },
                }
            ),
            encoding="utf-8",
        )

        previous = os.environ.get("BOT_CONFIG_FILE")
        os.environ["BOT_CONFIG_FILE"] = str(config_path)
        self.addCleanup(
            lambda: (
                os.environ.__setitem__("BOT_CONFIG_FILE", previous)
                if previous is not None
                else os.environ.pop("BOT_CONFIG_FILE", None)
            )
        )

        settings = BotSettings.load(workspace)
        self.assertEqual(settings.api_key, "test-key")
        self.assertEqual(settings.base_url, "https://example.invalid/v1/")
        self.assertEqual(settings.model, "demo-model")
        self.assertEqual(settings.temperature, 0.7)
        self.assertEqual(settings.max_tokens, 2048)
        self.assertEqual(settings.max_history_messages, 9)
        self.assertEqual(settings.max_recalled_memories, 4)
        self.assertEqual(settings.max_session_requests, 5)
        self.assertIn("demo", settings.mcp_servers)
        self.assertEqual(settings.builtin_skills_dir, (workspace / "builtin_skills").resolve())
        self.assertEqual(settings.extra_skills_dirs, [(workspace / "shared_skills").resolve()])


if __name__ == "__main__":
    unittest.main()
