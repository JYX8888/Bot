from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from corebot.skills import SkillsManager


class SkillsManagerTest(unittest.TestCase):
    def _make_workspace(self, name: str) -> Path:
        path = Path(__file__).resolve().parent / ".skills_tmp" / name
        if path.exists():
            shutil.rmtree(path)
        (path / "skills").mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_lists_and_injects_requested_skills(self) -> None:
        workspace = self._make_workspace("workspace")
        skill_dir = workspace / "skills" / "git"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "description: Git helper\n"
            "---\n"
            "Use git status before suggesting commits.\n",
            encoding="utf-8",
        )

        manager = SkillsManager(workspace)
        skills = manager.list_skills()
        self.assertEqual(skills[0]["name"], "git")
        context = manager.build_context("请使用 $git skill 帮我分析")
        self.assertIn("Available Skills", context)
        self.assertIn("Use git status before suggesting commits.", context)

    def test_loads_always_skill_without_explicit_reference(self) -> None:
        workspace = self._make_workspace("always")
        skill_dir = workspace / "skills" / "safety"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "description: Safety helper\n"
            "always: true\n"
            "---\n"
            "Always validate dangerous commands.\n",
            encoding="utf-8",
        )

        manager = SkillsManager(workspace)
        context = manager.build_context("普通问题")
        self.assertIn("Always validate dangerous commands.", context)


if __name__ == "__main__":
    unittest.main()
