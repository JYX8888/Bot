from __future__ import annotations

import re
from pathlib import Path

import yaml


class SkillsManager:
    """Minimal skill loader for workspace and configured skill directories."""

    _FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.DOTALL)

    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path | None = None,
        extra_skills_dirs: list[Path] | None = None,
    ) -> None:
        self.workspace = workspace
        self.workspace_skills_dir = workspace / "skills"
        self.builtin_skills_dir = builtin_skills_dir
        self.extra_skills_dirs = extra_skills_dirs or []

    def _roots(self) -> list[Path]:
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

    def list_skills(self) -> list[dict[str, str]]:
        seen: set[str] = set()
        entries: list[dict[str, str]] = []
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
                entries.append(
                    {
                        "name": name,
                        "path": str(skill_file),
                        "description": self.skill_description(name),
                    }
                )
        return entries

    def load_skill(self, name: str) -> str | None:
        for root in self._roots():
            path = root / name / "SKILL.md"
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def skill_metadata(self, name: str) -> dict:
        content = self.load_skill(name)
        if not content:
            return {}
        match = self._FRONTMATTER_RE.match(content)
        if not match:
            return {}
        parsed = yaml.safe_load(match.group(1))
        return parsed if isinstance(parsed, dict) else {}

    def skill_description(self, name: str) -> str:
        metadata = self.skill_metadata(name)
        description = metadata.get("description")
        return str(description) if description else name

    def _strip_frontmatter(self, content: str) -> str:
        match = self._FRONTMATTER_RE.match(content)
        if not match:
            return content.strip()
        return content[match.end() :].strip()

    def always_skills(self) -> list[str]:
        always: list[str] = []
        for entry in self.list_skills():
            metadata = self.skill_metadata(entry["name"])
            if metadata.get("always") is True:
                always.append(entry["name"])
        return always

    def requested_skills(self, user_input: str) -> list[str]:
        if not user_input.strip():
            return self.always_skills()

        available_names = [entry["name"] for entry in self.list_skills()]
        requested: list[str] = []
        lower_input = user_input.lower()

        for name in self.always_skills():
            if name not in requested:
                requested.append(name)

        for name in available_names:
            lowered = name.lower()
            if f"${lowered}" in lower_input or re.search(rf"\b{re.escape(lowered)}\b", lower_input):
                if name not in requested:
                    requested.append(name)
        return requested

    def build_summary(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = [
            f"- `{entry['name']}`: {entry['description']} (`{entry['path']}`)"
            for entry in skills
        ]
        return "\n".join(lines)

    def build_context(self, user_input: str) -> str:
        summary = self.build_summary()
        requested = self.requested_skills(user_input)
        parts: list[str] = []
        if summary:
            parts.append("# Available Skills\n" + summary)
        if requested:
            loaded = []
            for name in requested:
                content = self.load_skill(name)
                if content:
                    loaded.append(f"## Skill: {name}\n\n{self._strip_frontmatter(content)}")
            if loaded:
                parts.append("# Active Skill Content\n\n" + "\n\n---\n\n".join(loaded))
        return "\n\n".join(parts)
