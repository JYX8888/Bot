"""MCP 工具包装相关测试。"""

from __future__ import annotations

import unittest

from corebot.mcp import normalize_schema_for_tool


class MCPTest(unittest.TestCase):
    """验证 MCP schema 规范化逻辑。"""

    def test_normalize_nullable_schema(self) -> None:
        """`oneOf: [null, string]` 应该被规范化成 `type=string + nullable=true`。"""
        schema = {
            "type": "object",
            "properties": {
                "value": {
                    "oneOf": [
                        {"type": "null"},
                        {"type": "string"},
                    ]
                }
            },
        }
        normalized = normalize_schema_for_tool(schema)
        self.assertEqual(normalized["type"], "object")
        self.assertEqual(normalized["properties"]["value"]["type"], "string")
        self.assertTrue(normalized["properties"]["value"]["nullable"])


if __name__ == "__main__":
    unittest.main()
