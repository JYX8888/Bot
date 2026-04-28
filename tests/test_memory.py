"""结构化记忆系统测试。"""

from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from corebot.bootstrap import bootstrap_local_langchain
from corebot.memory import MemoryManager

bootstrap_local_langchain()

from langchain_core.messages import AIMessage, HumanMessage


class MemoryManagerTest(unittest.TestCase):
    """验证记忆写入、摘要、裁剪和删除逻辑。"""

    def _make_dir(self, name: str) -> Path:
        """创建临时目录并注册清理逻辑。"""
        path = Path(__file__).resolve().parent / ".memory_tmp" / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_updates_profiles_and_builds_context(self) -> None:
        """验证一轮对话后，用户记忆、项目记忆和会话上下文都会被更新。"""
        memory_dir = self._make_dir("profiles")
        manager = MemoryManager(memory_dir, max_history_messages=2, max_recalled_memories=4, max_session_requests=4)
        messages = [
            HumanMessage(content="请默认用中文回答，每次修改后都更新 README。这个项目支持 MCP。"),
            AIMessage(content="已添加 MCP 支持，并会保持中文输出。"),
        ]

        manager.update_after_turn(
            "default",
            messages,
            "请默认用中文回答，每次修改后都更新 README。这个项目支持 MCP。",
            "已添加 MCP 支持，并会保持中文输出。",
        )

        user_profile = manager.load_user_profile()
        project_profile = manager.load_project_profile()
        session_record = manager.load_session_record("default")
        context = manager.build_context("default", "继续完善 README 和 MCP 能力", messages)

        self.assertIn("默认使用中文回复", user_profile.preferences)
        self.assertTrue(any("README" in item for item in user_profile.workflows + user_profile.constraints))
        self.assertTrue(any("MCP" in item for item in project_profile.facts + project_profile.decisions))
        self.assertTrue(session_record.summary)
        self.assertIn("相关历史记忆", context)

    def test_trims_history_window(self) -> None:
        """验证长历史会被裁剪到指定窗口大小。"""
        memory_dir = self._make_dir("trim")
        manager = MemoryManager(memory_dir, max_history_messages=2, max_recalled_memories=2, max_session_requests=4)
        messages = [
            HumanMessage(content="one"),
            AIMessage(content="two"),
            HumanMessage(content="three"),
        ]
        trimmed = manager.trim_history(messages)
        self.assertEqual([message.content for message in trimmed], ["two", "three"])

    def test_deletes_session_record(self) -> None:
        """验证会话结构化记忆可以被删除。"""
        memory_dir = self._make_dir("delete")
        manager = MemoryManager(memory_dir, max_history_messages=2, max_recalled_memories=2, max_session_requests=4)
        manager.save_session_record("demo", manager.load_session_record("demo"))
        self.assertTrue(manager.delete_session_record("demo"))
        self.assertFalse(manager.delete_session_record("demo"))


if __name__ == "__main__":
    unittest.main()
