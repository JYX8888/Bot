from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from corebot.bootstrap import bootstrap_local_langchain
from corebot.session_store import SessionStore

bootstrap_local_langchain()

from langchain_core.messages import AIMessage, HumanMessage


class SessionStoreTest(unittest.TestCase):
    def _make_dir(self, name: str) -> Path:
        path = Path(__file__).resolve().parent / ".session_tmp" / name
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_save_and_load_messages(self) -> None:
        sessions_dir = self._make_dir("save_load")
        store = SessionStore(sessions_dir)
        messages = [HumanMessage(content="hello"), AIMessage(content="world")]
        store.save_messages("default", messages)
        loaded = store.load_messages("default")
        self.assertEqual([message.content for message in loaded], ["hello", "world"])


if __name__ == "__main__":
    unittest.main()
