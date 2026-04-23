from __future__ import annotations

import json
from pathlib import Path

from corebot.bootstrap import bootstrap_local_langchain

bootstrap_local_langchain()

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict


class SessionStore:
    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.sessions_dir / f"{safe}.json"

    def load_messages(self, session_id: str) -> list[BaseMessage]:
        path = self._path_for(session_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return messages_from_dict(payload.get("messages", []))

    def save_messages(self, session_id: str, messages: list[BaseMessage]) -> None:
        path = self._path_for(session_id)
        payload = {
            "session_id": session_id,
            "messages": [message_to_dict(message) for message in messages],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, session_id: str) -> bool:
        path = self._path_for(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True
