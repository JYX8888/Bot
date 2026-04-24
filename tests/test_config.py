from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import unittest

from corebot.config import BotSettings


class ConfigTest(unittest.TestCase):
    def _make_dir(self, name: str) -> Path:
        path = Path(__file__).resolve().parent / ".config_tmp" / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_loads_nanobot_style_json_config(self) -> None:
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
        self.assertIn("demo", settings.mcp_servers)
        self.assertEqual(settings.builtin_skills_dir, (workspace / "builtin_skills").resolve())
        self.assertEqual(settings.extra_skills_dirs, [(workspace / "shared_skills").resolve()])


if __name__ == "__main__":
    unittest.main()
