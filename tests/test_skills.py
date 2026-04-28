"""Skills 管理器测试。"""

from __future__ import annotations

import shutil
from pathlib import Path
import unittest

from corebot.skills import SkillsManager


class SkillsManagerTest(unittest.TestCase):
    """验证 Skills 的扫描、激活与依赖逻辑。"""

    def _make_workspace(self, name: str) -> Path:
        """创建测试工作区，并预建 `skills` 目录。"""
        path = Path(__file__).resolve().parent / ".skills_tmp" / name
        if path.exists():
            shutil.rmtree(path)
        (path / "skills").mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(path, ignore_errors=True))
        return path

    def test_lists_and_injects_requested_skills(self) -> None:
        """验证显式提到技能时，技能会出现在上下文中。"""
        workspace = self._make_workspace("workspace")
        skill_dir = workspace / "skills" / "git"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "description: Git helper\n"
            "summary: 用于 Git 相关操作\n"
            "triggers:\n"
            "  - commit\n"
            "---\n"
            "Use git status before suggesting commits.\n",
            encoding="utf-8",
        )

        manager = SkillsManager(workspace)
        skills = manager.list_skills()
        self.assertEqual(skills[0]["name"], "git")
        context = manager.build_context("请参考 git skill，帮我整理 commit 建议")
        self.assertIn("可用技能", context)
        self.assertIn("触发原因", context)
        self.assertIn("Use git status before suggesting commits.", context)

    def test_loads_dependencies_and_task_type_matches(self) -> None:
        """验证技能依赖和任务类型匹配都能正常生效。"""
        workspace = self._make_workspace("dependencies")

        base_dir = workspace / "skills" / "base"
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "SKILL.md").write_text(
            "---\n"
            "description: Base helper\n"
            "---\n"
            "Base instructions.\n",
            encoding="utf-8",
        )

        review_dir = workspace / "skills" / "reviewer"
        review_dir.mkdir(parents=True, exist_ok=True)
        (review_dir / "SKILL.md").write_text(
            "---\n"
            "description: Review helper\n"
            "taskTypes:\n"
            "  - review\n"
            "dependsOn:\n"
            "  - base\n"
            "priority: 10\n"
            "---\n"
            "Review instructions.\n",
            encoding="utf-8",
        )

        manager = SkillsManager(workspace)
        active = manager.resolve_active_skills("请帮我做一次代码审查")
        names = [str(item["name"]) for item in active]
        self.assertIn("reviewer", names)
        self.assertIn("base", names)


if __name__ == "__main__":
    unittest.main()
