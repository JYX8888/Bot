"""会话存储测试。"""

from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from corebot.bootstrap import bootstrap_local_langchain
from corebot.session_store import SessionStore

bootstrap_local_langchain()

from langchain_core.messages import AIMessage, HumanMessage


class SessionStoreTest(unittest.TestCase):
    """验证原始消息历史的保存与读取。"""

    def _make_dir(self, name: str) -> Path:
        """创建临时目录并在测试结束后清理。"""
        path = Path(__file__).resolve().parent / ".session_tmp" / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_save_and_load_messages(self) -> None:
        """验证消息保存后可以完整读回。"""
        sessions_dir = self._make_dir("save_load")
        store = SessionStore(sessions_dir)
        messages = [HumanMessage(content="hello"), AIMessage(content="world")]
        store.save_messages("default", messages)
        loaded = store.load_messages("default")
        self.assertEqual([message.content for message in loaded], ["hello", "world"])


if __name__ == "__main__":
    unittest.main()
