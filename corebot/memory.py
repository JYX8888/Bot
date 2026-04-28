"""结构化记忆系统。

这个文件是项目里“越用越顺手”的核心之一。
它把记忆拆成三层：
1. `SessionMemoryRecord`: 当前会话相关的中期记忆
2. `UserMemoryRecord`: 用户长期偏好、工作流、约束
3. `ProjectMemoryRecord`: 项目级长期事实、决策和文件线索

同时它还负责：
- 长对话时裁剪原始历史
- 从本轮输入/回复里抽取结构化信息
- 按关键词召回历史记忆
- 为系统提示词生成可读的记忆上下文
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from corebot.bootstrap import bootstrap_local_langchain

bootstrap_local_langchain()

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class SessionMemoryRecord(BaseModel):
    """单个会话对应的结构化记忆。"""

    # 会话 ID，用于和外部 session 概念对齐。
    session_id: str = ""

    # 当前会话的压缩摘要。
    summary: str = ""

    # 最近若干次用户请求，帮助快速回忆最近在做什么。
    recent_requests: list[str] = Field(default_factory=list)

    # 已经确认过的结论或决策。
    decisions: list[str] = Field(default_factory=list)

    # 后续待办事项。
    todos: list[str] = Field(default_factory=list)

    # 和项目相关的事实描述。
    facts: list[str] = Field(default_factory=list)

    # 用于关键词召回的索引词。
    keywords: list[str] = Field(default_factory=list)

    # 最后更新时间，便于调试和观察。
    updated_at: str = ""


class UserMemoryRecord(BaseModel):
    """用户长期记忆。"""

    preferences: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    updated_at: str = ""


class ProjectMemoryRecord(BaseModel):
    """项目长期记忆。"""

    summary: str = ""
    facts: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    workflows: list[str] = Field(default_factory=list)
    file_hints: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    updated_at: str = ""


class MemoryManager:
    """管理所有结构化记忆文件。"""

    def __init__(
        self,
        memory_dir: Path,
        max_history_messages: int = 12,
        max_recalled_memories: int = 6,
        max_session_requests: int = 6,
    ) -> None:
        """初始化记忆目录及相关参数。

        参数：
        - memory_dir: 记忆根目录
        - max_history_messages: 原始消息保留窗口
        - max_recalled_memories: 单轮最多召回多少条记忆
        - max_session_requests: 会话里最多保留多少条最近请求
        """
        self.memory_dir = memory_dir
        self.max_history_messages = max_history_messages
        self.max_recalled_memories = max_recalled_memories
        self.max_session_requests = max_session_requests

        # 不同记忆类型放到不同文件中，便于单独查看和删除。
        self.sessions_dir = self.memory_dir / "sessions"
        self.user_profile_path = self.memory_dir / "user_profile.json"
        self.project_profile_path = self.memory_dir / "project_profile.json"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def trim_history(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """裁剪过长的原始消息历史。"""
        if len(messages) <= self.max_history_messages:
            return messages
        return messages[-self.max_history_messages :]

    def build_context(
        self,
        session_id: str,
        user_input: str,
        stored_messages: list[BaseMessage],
    ) -> str:
        """把结构化记忆组装成模型可读的上下文文本。"""
        session = self.load_session_record(session_id)
        if not session.summary and stored_messages:
            session.summary = self._build_session_summary(stored_messages, session)

        user_profile = self.load_user_profile()
        project_profile = self.load_project_profile()
        recalled = self.search(user_input, session_id=session_id)

        parts: list[str] = []

        # 用户长期记忆：帮助 bot 长期保持一致的输出习惯和行为偏好。
        if user_profile.preferences or user_profile.workflows or user_profile.constraints:
            lines: list[str] = []
            if user_profile.preferences:
                lines.append("用户偏好：" + "；".join(user_profile.preferences[:4]))
            if user_profile.workflows:
                lines.append("常用流程：" + "；".join(user_profile.workflows[:4]))
            if user_profile.constraints:
                lines.append("固定约束：" + "；".join(user_profile.constraints[:4]))
            parts.append("\n".join(lines))

        # 项目长期记忆：帮助 bot 在跨会话时记住项目背景。
        if project_profile.summary or project_profile.facts or project_profile.decisions:
            lines: list[str] = []
            if project_profile.summary:
                lines.append("项目摘要：" + project_profile.summary)
            if project_profile.facts:
                lines.append("项目事实：" + "；".join(project_profile.facts[:5]))
            if project_profile.decisions:
                lines.append("项目决策：" + "；".join(project_profile.decisions[:5]))
            parts.append("\n".join(lines))

        # 当前会话记忆：帮助 bot 记住本轮上下文里已经讨论过什么。
        if session.summary or session.decisions or session.todos:
            lines = []
            if session.summary:
                lines.append("当前会话摘要：" + session.summary)
            if session.decisions:
                lines.append("本会话已确认：" + "；".join(session.decisions[:5]))
            if session.todos:
                lines.append("本会话后续事项：" + "；".join(session.todos[:5]))
            parts.append("\n".join(lines))

        # 召回结果：只把和当前问题最相关的历史内容带进来。
        if recalled:
            lines = [f"- [{item['source']}] {item['text']}" for item in recalled]
            parts.append("相关历史记忆：\n" + "\n".join(lines))

        # 如果原始历史被裁剪了，明确告诉模型应该结合摘要理解。
        if len(stored_messages) > len(self.trim_history(stored_messages)):
            parts.append(
                f"历史消息已裁剪，只保留最近 {self.max_history_messages} 条原始消息，其余信息请结合会话摘要理解。"
            )

        return "\n\n".join(part for part in parts if part)

    def update_after_turn(
        self,
        session_id: str,
        messages: list[BaseMessage],
        user_input: str,
        assistant_text: str,
    ) -> None:
        """在一轮对话结束后更新所有记忆。

        这里会同时更新：
        - 当前会话记忆
        - 用户长期记忆
        - 项目长期记忆
        """
        session = self.load_session_record(session_id)
        session.session_id = session_id
        session.recent_requests = self._merge_unique(
            session.recent_requests + [self._compact_text(user_input, 120)],
            limit=self.max_session_requests,
        )
        session.decisions = self._merge_unique(
            session.decisions + self._extract_decisions(assistant_text),
            limit=8,
        )
        session.todos = self._merge_unique(
            session.todos + self._extract_todos(user_input) + self._extract_todos(assistant_text),
            limit=8,
        )
        session.facts = self._merge_unique(
            session.facts + self._extract_project_facts(user_input) + self._extract_project_facts(assistant_text),
            limit=10,
        )
        session.keywords = self._merge_unique(
            session.keywords + self._extract_keywords(user_input + "\n" + assistant_text),
            limit=60,
        )
        session.summary = self._build_session_summary(messages, session)
        session.updated_at = self._now()
        self.save_session_record(session_id, session)

        # 只从用户输入里抽用户偏好；这样更接近“明确表达的要求”。
        user_profile = self.load_user_profile()
        preferences, workflows, constraints = self._extract_user_profile_items(user_input)
        user_profile.preferences = self._merge_unique(user_profile.preferences + preferences, limit=10)
        user_profile.workflows = self._merge_unique(user_profile.workflows + workflows, limit=10)
        user_profile.constraints = self._merge_unique(user_profile.constraints + constraints, limit=10)
        user_profile.keywords = self._merge_unique(
            user_profile.keywords + self._extract_keywords(user_input),
            limit=60,
        )
        user_profile.updated_at = self._now()
        self.save_user_profile(user_profile)

        # 项目记忆吸收当前会话里沉淀出的项目信息。
        project_profile = self.load_project_profile()
        project_profile.facts = self._merge_unique(project_profile.facts + session.facts, limit=12)
        project_profile.decisions = self._merge_unique(project_profile.decisions + session.decisions, limit=12)
        project_profile.workflows = self._merge_unique(project_profile.workflows + workflows, limit=10)
        project_profile.file_hints = self._merge_unique(
            project_profile.file_hints
            + self._extract_file_hints(user_input)
            + self._extract_file_hints(assistant_text),
            limit=12,
        )
        project_profile.keywords = self._merge_unique(
            project_profile.keywords + self._extract_keywords(user_input + "\n" + assistant_text),
            limit=80,
        )
        project_profile.summary = self._build_project_summary(project_profile)
        project_profile.updated_at = self._now()
        self.save_project_profile(project_profile)

    def load_session_record(self, session_id: str) -> SessionMemoryRecord:
        """读取某个会话的结构化记忆。"""
        path = self.sessions_dir / f"{self._safe_name(session_id)}.json"
        record = self._load_record(path, SessionMemoryRecord)
        if not record.session_id:
            record.session_id = session_id
        return record

    def save_session_record(self, session_id: str, record: SessionMemoryRecord) -> None:
        """保存某个会话的结构化记忆。"""
        path = self.sessions_dir / f"{self._safe_name(session_id)}.json"
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def delete_session_record(self, session_id: str) -> bool:
        """删除某个会话的结构化记忆文件。"""
        path = self.sessions_dir / f"{self._safe_name(session_id)}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    def load_user_profile(self) -> UserMemoryRecord:
        """读取用户长期记忆。"""
        return self._load_record(self.user_profile_path, UserMemoryRecord)

    def save_user_profile(self, record: UserMemoryRecord) -> None:
        """保存用户长期记忆。"""
        self.user_profile_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def load_project_profile(self) -> ProjectMemoryRecord:
        """读取项目长期记忆。"""
        return self._load_record(self.project_profile_path, ProjectMemoryRecord)

    def save_project_profile(self, record: ProjectMemoryRecord) -> None:
        """保存项目长期记忆。"""
        self.project_profile_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def search(self, query: str, session_id: str) -> list[dict[str, str]]:
        """根据当前问题从结构化记忆中召回最相关的条目。"""
        query_keywords = set(self._extract_keywords(query))
        if not query_keywords:
            return []

        candidates: list[dict[str, str | int]] = []
        user_profile = self.load_user_profile()
        project_profile = self.load_project_profile()

        for item in user_profile.preferences:
            self._append_candidate(candidates, query_keywords, "用户偏好", item)
        for item in user_profile.workflows:
            self._append_candidate(candidates, query_keywords, "用户流程", item)
        for item in user_profile.constraints:
            self._append_candidate(candidates, query_keywords, "用户约束", item)

        for item in project_profile.facts:
            self._append_candidate(candidates, query_keywords, "项目事实", item)
        for item in project_profile.decisions:
            self._append_candidate(candidates, query_keywords, "项目决策", item)
        for item in project_profile.workflows:
            self._append_candidate(candidates, query_keywords, "项目流程", item)
        for item in project_profile.file_hints:
            self._append_candidate(candidates, query_keywords, "相关文件", item)

        # 也会扫描其他历史会话，做到跨会话召回。
        for path in sorted(self.sessions_dir.glob("*.json")):
            record = self._load_record(path, SessionMemoryRecord)
            if not record.session_id or record.session_id == session_id:
                continue
            if record.summary:
                self._append_candidate(candidates, query_keywords, f"历史会话 {record.session_id}", record.summary)
            for item in record.decisions:
                self._append_candidate(candidates, query_keywords, f"历史决策 {record.session_id}", item)
            for item in record.facts:
                self._append_candidate(candidates, query_keywords, f"历史事实 {record.session_id}", item)
            for item in record.recent_requests:
                self._append_candidate(candidates, query_keywords, f"历史请求 {record.session_id}", item)

        # 分数高的优先召回。
        candidates.sort(key=lambda item: (-int(item["score"]), str(item["source"]), str(item["text"])))

        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in candidates:
            key = (str(item["source"]), str(item["text"]))
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"source": str(item["source"]), "text": str(item["text"])})
            if len(deduped) >= self.max_recalled_memories:
                break

        return deduped

    def _append_candidate(
        self,
        candidates: list[dict[str, str | int]],
        query_keywords: set[str],
        source: str,
        text: str,
    ) -> None:
        """把一条可能相关的记忆加入候选池。"""
        score = self._score_text(query_keywords, text)
        if score <= 0:
            return
        candidates.append({"source": source, "text": text, "score": score})

    def _build_session_summary(
        self,
        messages: list[BaseMessage],
        record: SessionMemoryRecord,
    ) -> str:
        """根据当前会话消息和已有结构化字段生成摘要。"""
        recent_requests = [
            self._compact_text(message.content, 80)
            for message in messages
            if isinstance(message, HumanMessage)
        ][-3:]
        recent_answers = [
            self._compact_text(self._message_text(message), 80)
            for message in messages
            if isinstance(message, AIMessage)
        ][-2:]

        lines: list[str] = []
        if recent_requests:
            lines.append("最近请求：" + "；".join(recent_requests))
        if record.decisions:
            lines.append("已确认决策：" + "；".join(record.decisions[:4]))
        if record.todos:
            lines.append("后续事项：" + "；".join(record.todos[:4]))
        if record.facts:
            lines.append("项目事实：" + "；".join(record.facts[:4]))
        elif recent_answers:
            lines.append("最近回复：" + "；".join(recent_answers))
        return "\n".join(lines)

    def _build_project_summary(self, record: ProjectMemoryRecord) -> str:
        """根据项目长期记忆生成简要摘要。"""
        lines: list[str] = []
        if record.facts:
            lines.append("事实：" + "；".join(record.facts[:3]))
        if record.decisions:
            lines.append("决策：" + "；".join(record.decisions[:3]))
        if record.workflows:
            lines.append("流程：" + "；".join(record.workflows[:3]))
        return "\n".join(lines)

    def _extract_user_profile_items(self, text: str) -> tuple[list[str], list[str], list[str]]:
        """从用户输入中抽取偏好、流程和约束。"""
        preferences: list[str] = []
        workflows: list[str] = []
        constraints: list[str] = []

        lowered = text.lower()
        if "中文" in text:
            preferences.append("默认使用中文回复")
        if any(keyword in text for keyword in ("简洁", "精简", "简短")):
            preferences.append("输出保持简洁")
        if "markdown" in lowered or "md" in lowered:
            preferences.append("输出优先使用 Markdown")

        for clause in self._split_clauses(text):
            compact = self._compact_text(clause, 80)
            if not compact:
                continue
            if any(keyword in clause for keyword in ("每次", "先", "然后", "修改后", "提交前")):
                workflows.append(compact)
            if any(keyword in clause for keyword in ("不要", "不能", "禁止", "必须", "只要")):
                constraints.append(compact)
            if any(keyword in clause for keyword in ("默认", "优先", "请用", "风格", "格式")):
                preferences.append(compact)

        return (
            self._merge_unique(preferences, limit=10),
            self._merge_unique(workflows, limit=10),
            self._merge_unique(constraints, limit=10),
        )

    def _extract_decisions(self, text: str) -> list[str]:
        """从回复中抽取更像“已完成决定”的句子。"""
        items = [
            self._compact_text(clause, 100)
            for clause in self._split_clauses(text)
            if any(keyword in clause for keyword in ("已", "现在", "当前", "支持", "接入", "改为", "采用", "新增"))
        ]
        return self._merge_unique(items, limit=8)

    def _extract_todos(self, text: str) -> list[str]:
        """从文本中抽取待办线索。"""
        items = [
            self._compact_text(clause, 100)
            for clause in self._split_clauses(text)
            if any(keyword in clause.lower() for keyword in ("todo", "待办", "下次", "后续", "继续", "之后", "还要"))
        ]
        return self._merge_unique(items, limit=8)

    def _extract_project_facts(self, text: str) -> list[str]:
        """从文本中抽取与项目直接相关的事实。"""
        items = [
            self._compact_text(clause, 100)
            for clause in self._split_clauses(text)
            if any(keyword in clause for keyword in ("项目", "仓库", "工作区", "模型", "配置", "MCP", "Skill", "Skills", "技能", "README"))
        ]
        return self._merge_unique(items, limit=10)

    def _extract_file_hints(self, text: str) -> list[str]:
        """从文本中提取可能的文件路径或文件名线索。"""
        matches = re.findall(r"(?:[A-Za-z]:[\\/][^\s]+|[\w./\\-]+\.[A-Za-z0-9_]+)", text)
        return self._merge_unique([self._compact_text(match, 120) for match in matches], limit=12)

    def _extract_keywords(self, text: str) -> list[str]:
        """从文本中提取召回用关键词。

        这里同时支持：
        - 英文 token
        - 中文短语
        - 中文 2/3/4 字切片
        """
        tokens: list[str] = []
        lowered = text.lower()
        tokens.extend(re.findall(r"[a-z0-9_./-]{2,}", lowered))

        for phrase in re.findall(r"[\u4e00-\u9fff]{2,8}", text):
            tokens.append(phrase)
            if len(phrase) > 2:
                for size in (2, 3, 4):
                    if len(phrase) >= size:
                        tokens.extend(phrase[index : index + size] for index in range(len(phrase) - size + 1))

        return self._merge_unique(tokens, limit=80)

    def _score_text(self, query_keywords: set[str], text: str) -> int:
        """计算一段文本与查询关键词的相关性分数。"""
        lowered = text.lower()
        text_keywords = set(self._extract_keywords(text))
        score = len(query_keywords & text_keywords)
        for token in query_keywords:
            if token and token in lowered:
                score += 1
        return score

    def _split_clauses(self, text: str) -> list[str]:
        """按句号、感叹号、换行等切分文本。"""
        return [part.strip(" -\t") for part in re.split(r"[。！？\n;；]+", text) if part.strip()]

    def _message_text(self, message: BaseMessage) -> str:
        """把 LangChain message 转成纯文本。"""
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    def _compact_text(self, text: str, limit: int) -> str:
        """把文本压缩成单行并限制长度。"""
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _merge_unique(self, items: list[str], limit: int) -> list[str]:
        """去重并保留最后 `limit` 条。"""
        merged: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged[-limit:]

    def _load_record(self, path: Path, model_cls: type[BaseModel]):
        """从 JSON 文件读取某种记忆记录。"""
        if not path.exists():
            return model_cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return model_cls()
        return model_cls.model_validate(payload)

    def _safe_name(self, name: str) -> str:
        """把任意会话名转换成适合作为文件名的字符串。"""
        return name.replace("/", "_").replace("\\", "_").replace(":", "_")

    def _now(self) -> str:
        """生成当前时间字符串。"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
