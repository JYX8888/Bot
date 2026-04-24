from __future__ import annotations

import unittest

from corebot.mcp import normalize_schema_for_tool


class MCPTest(unittest.TestCase):
    def test_normalize_nullable_schema(self) -> None:
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
