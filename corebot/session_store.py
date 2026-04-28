"""原始会话消息的持久化层。

这个文件只管“完整消息历史”的读写，不负责摘要、偏好、项目记忆等结构化信息。
换句话说：
- `SessionStore` 保存的是 LangChain message 列表
- `MemoryManager` 保存的是加工后的结构化记忆
"""

from __future__ import annotations

import json
from pathlib import Path

from corebot.bootstrap import bootstrap_local_langchain

bootstrap_local_langchain()

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict


class SessionStore:
    """负责把会话消息保存到本地 JSON 文件。"""

    def __init__(self, sessions_dir: Path):
        """初始化会话存储目录。

        参数：
        - sessions_dir: 用来保存每个会话 JSON 文件的目录
        """
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, session_id: str) -> Path:
        """根据会话 ID 生成对应的存储文件路径。"""
        # 会话 ID 可能包含路径分隔符，因此先做安全替换。
        safe = session_id.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.sessions_dir / f"{safe}.json"

    def load_messages(self, session_id: str) -> list[BaseMessage]:
        """读取某个会话的完整消息历史。

        参数：
        - session_id: 会话 ID

        返回：
        - LangChain `BaseMessage` 列表；如果文件不存在，返回空列表
        """
        path = self._path_for(session_id)
        if not path.exists():
            return []

        payload = json.loads(path.read_text(encoding="utf-8"))
        return messages_from_dict(payload.get("messages", []))

    def save_messages(self, session_id: str, messages: list[BaseMessage]) -> None:
        """保存某个会话的完整消息历史。"""
        path = self._path_for(session_id)

        payload = {
            "session_id": session_id,
            "messages": [message_to_dict(message) for message in messages],
        }

        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, session_id: str) -> bool:
        """删除某个会话文件。

        返回：
        - `True` 表示文件存在且已删除
        - `False` 表示文件原本就不存在
        """
        path = self._path_for(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True
