"""Skills 扫描、匹配与上下文注入逻辑。

这个模块做的事情可以简单理解为：
1. 找出有哪些 Skill 可用
2. 判断当前输入该激活哪些 Skill
3. 把这些 Skill 的内容整理成模型可读的上下文
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


class SkillsManager:
    """负责扫描、匹配和注入 Skills 上下文。"""

    # 用于提取 SKILL.md 顶部 YAML frontmatter。
    _FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)

    # 根据用户输入推断任务类型时使用的关键字表。
    _TASK_KEYWORDS = {
        "analysis": ("分析", "架构", "结构", "梳理", "解释"),
        "review": ("review", "审查", "检查", "风险", "回归"),
        "coding": ("实现", "修改", "重构", "修复", "开发"),
        "docs": ("readme", "文档", "说明", "教程"),
        "testing": ("测试", "test", "校验", "验证"),
        "release": ("发布", "部署", "上线"),
    }

    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path | None = None,
        extra_skills_dirs: list[Path] | None = None,
        max_active_skills: int = 4,
        max_inline_chars: int = 1800,
    ) -> None:
        """初始化 Skills 管理器。

        参数：
        - workspace: 当前工作区，用于扫描 `workspace/skills`
        - builtin_skills_dir: 内置技能目录
        - extra_skills_dirs: 额外技能目录
        - max_active_skills: 单轮最多激活多少个技能
        - max_inline_chars: 注入模型前，单个技能正文最多保留多少字符
        """
        self.workspace = workspace
        self.workspace_skills_dir = workspace / "skills"
        self.builtin_skills_dir = builtin_skills_dir
        self.extra_skills_dirs = extra_skills_dirs or []
        self.max_active_skills = max_active_skills
        self.max_inline_chars = max_inline_chars

    def _roots(self) -> list[Path]:
        """返回所有需要扫描的技能根目录。"""
        roots = [self.workspace_skills_dir, self.workspace / "nanobot" / "skills"]
        if self.builtin_skills_dir:
            roots.append(self.builtin_skills_dir)
        roots.extend(self.extra_skills_dirs)

        unique: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if root.exists() and root not in seen:
                seen.add(root)
                unique.append(root)
        return unique

    def list_skills(self) -> list[dict[str, str | int]]:
        """列出当前可用的所有技能。"""
        seen: set[str] = set()
        entries: list[dict[str, str | int]] = []

        for root in self._roots():
            for skill_dir in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if not skill_dir.is_dir():
                    continue
                skill_file = skill_dir / "SKILL.md"
                if not skill_file.exists():
                    continue

                name = skill_dir.name
                if name in seen:
                    continue
                seen.add(name)

                metadata = self.skill_metadata(name)
                entries.append(
                    {
                        "name": name,
                        "path": str(skill_file),
                        "description": str(metadata.get("description") or metadata.get("summary") or name),
                        "summary": str(metadata.get("summary") or metadata.get("description") or name),
                        "priority": int(metadata.get("priority", 0)),
                    }
                )

        return sorted(entries, key=lambda item: (-int(item["priority"]), str(item["name"])))

    def load_skill(self, name: str) -> str | None:
        """读取某个技能的 `SKILL.md` 全文。"""
        for root in self._roots():
            path = root / name / "SKILL.md"
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def skill_metadata(self, name: str) -> dict:
        """读取技能 frontmatter 里的元数据。"""
        content = self.load_skill(name)
        if not content:
            return {}
        match = self._FRONTMATTER_RE.match(content)
        if not match:
            return {}
        parsed = yaml.safe_load(match.group(1))
        return parsed if isinstance(parsed, dict) else {}

    def _strip_frontmatter(self, content: str) -> str:
        """移除技能文件顶部的 YAML frontmatter。"""
        match = self._FRONTMATTER_RE.match(content)
        if not match:
            return content.strip()
        return content[match.end() :].strip()

    def _dependency_names(self, metadata: dict) -> list[str]:
        """提取技能依赖列表。"""
        raw = metadata.get("dependsOn", metadata.get("depends_on", []))
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item).strip()]
        return []

    def _trigger_terms(self, metadata: dict) -> list[str]:
        """提取技能触发词列表。"""
        raw = metadata.get("triggers", [])
        if isinstance(raw, str):
            return [raw.lower()]
        if isinstance(raw, list):
            return [str(item).lower() for item in raw if str(item).strip()]
        return []

    def _task_types(self, metadata: dict) -> list[str]:
        """提取技能声明支持的任务类型。"""
        raw = metadata.get("taskTypes", metadata.get("task_types", []))
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item).strip()]
        return []

    def _infer_task_types(self, user_input: str) -> set[str]:
        """根据用户输入粗略推断任务类型。"""
        lowered = user_input.lower()
        task_types: set[str] = set()
        for task_type, keywords in self._TASK_KEYWORDS.items():
            if any(keyword in lowered or keyword in user_input for keyword in keywords):
                task_types.add(task_type)
        return task_types

    def always_skills(self) -> list[str]:
        """返回所有声明 `always: true` 的技能。"""
        always: list[str] = []
        for entry in self.list_skills():
            metadata = self.skill_metadata(str(entry["name"]))
            if metadata.get("always") is True:
                always.append(str(entry["name"]))
        return always

    def resolve_active_skills(self, user_input: str) -> list[dict[str, str | int]]:
        """根据本轮输入决定哪些技能应该被激活。"""
        entries = {str(entry["name"]): entry for entry in self.list_skills()}
        inferred_tasks = self._infer_task_types(user_input)
        lowered = user_input.lower()
        activated: dict[str, dict[str, str | int]] = {}

        def _activate(name: str, reason: str) -> None:
            """递归激活技能及其依赖。"""
            entry = entries.get(name)
            if not entry:
                return

            current = activated.get(name)
            if current is None or str(current["reason"]) == "自动加载":
                activated[name] = {**entry, "reason": reason}

            metadata = self.skill_metadata(name)
            for dependency in self._dependency_names(metadata):
                _activate(dependency, f"依赖于 {name}")

        for name in self.always_skills():
            _activate(name, "自动加载")

        for name in entries:
            metadata = self.skill_metadata(name)
            explicit = f"${name.lower()}" in lowered or re.search(rf"\b{re.escape(name.lower())}\b", lowered)
            if explicit:
                _activate(name, "显式引用")
                continue

            for trigger in self._trigger_terms(metadata):
                if trigger and trigger in lowered:
                    _activate(name, f"触发词：{trigger}")
                    break

            task_types = set(self._task_types(metadata))
            if task_types and task_types & inferred_tasks:
                _activate(name, "任务类型匹配")

        resolved = list(activated.values())
        resolved.sort(key=lambda item: (-int(item["priority"]), str(item["name"])))
        return resolved[: self.max_active_skills]

    def build_summary(self) -> str:
        """构建“可用技能总览”文本。"""
        skills = self.list_skills()
        if not skills:
            return ""
        lines = [
            f"- `{entry['name']}`: {entry['summary']}（优先级 {entry['priority']}）"
            for entry in skills
        ]
        return "\n".join(lines)

    def build_context(self, user_input: str) -> str:
        """构建要注入模型的 Skills 上下文。"""
        summary = self.build_summary()
        active_skills = self.resolve_active_skills(user_input)
        parts: list[str] = []

        if summary:
            parts.append("# 可用技能\n" + summary)

        if active_skills:
            blocks: list[str] = []
            for entry in active_skills:
                name = str(entry["name"])
                metadata = self.skill_metadata(name)
                content = self.load_skill(name) or ""
                body = self._strip_frontmatter(content)
                reason = str(entry["reason"])
                summary_text = str(metadata.get("summary") or metadata.get("description") or "")

                # 为了控制上下文大小，长技能只保留摘要 + 截断正文。
                if len(body) > self.max_inline_chars and summary_text:
                    body = summary_text + "\n\n" + body[: self.max_inline_chars].rstrip() + "\n..."
                elif len(body) > self.max_inline_chars:
                    body = body[: self.max_inline_chars].rstrip() + "\n..."

                blocks.append(f"## 技能：{name}\n触发原因：{reason}\n\n{body}")

            parts.append("# 当前激活的技能内容\n\n" + "\n\n---\n\n".join(blocks))

        return "\n\n".join(parts)
