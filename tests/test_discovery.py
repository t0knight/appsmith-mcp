import json
import unittest
from unittest.mock import AsyncMock, patch

from appsmith_mcp import server
from tests.test_mcp_contracts import payload


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_capabilities_work_without_browser_and_match_registered_tools(self):
        with patch.object(server, "ensure_ready", new=AsyncMock(side_effect=AssertionError("browser touched"))):
            result = payload(await server.mcp.call_tool("get_capabilities", {}))
        tools = await server.mcp.list_tools()
        self.assertEqual(result["toolCount"], len(tools))
        self.assertEqual(set(result["tools"]), {tool.name for tool in tools})
        self.assertEqual(result["transport"], "stdio")
        self.assertEqual(result["policy"]["queryExecution"], "read_only")
        self.assertFalse(result["policy"]["arbitraryJsExecution"])
        self.assertFalse(result["runtime"]["verified"])
        self.assertEqual(result["runtime"]["inspectWith"], "get_build_context")
        self.assertLess(len(json.dumps(result).encode("utf-8")), 8192)

    async def test_guides_list_and_read_only_the_selected_recipe_without_browser(self):
        with patch.object(server, "ensure_ready", new=AsyncMock(side_effect=AssertionError("browser touched"))):
            listing = payload(await server.mcp.call_tool("get_guide", {}))
            result = payload(await server.mcp.call_tool("get_guide", {"slug": "download-binary"}))
        self.assertIn("download-binary", [guide["slug"] for guide in listing["guides"]])
        self.assertEqual(result["slug"], "download-binary")
        self.assertIn("URL.revokeObjectURL", result["markdown"])
        self.assertNotIn("## 2.", result["markdown"])
        self.assertNotIn("markdown", listing)

    async def test_unknown_or_path_like_slug_is_rejected_with_available_guides(self):
        for slug in ["../README.md", "C:/Windows/win.ini", "missing-guide", ""]:
            with self.subTest(slug=slug):
                result = payload(await server.mcp.call_tool("get_guide", {"slug": slug}))
                self.assertFalse(result["ok"])
                self.assertIn("available", result)
                self.assertNotIn("markdown", result)

    async def test_reading_and_diagnostics_guides_are_available(self):
        for slug in ["reading-state", "diagnostics"]:
            with self.subTest(slug=slug):
                result = payload(await server.mcp.call_tool("get_guide", {"slug": slug}))
                self.assertTrue(result["ok"])
                self.assertIn("get_build_context", result["markdown"])

    async def test_every_indexed_guide_resolves(self):
        listing = payload(await server.mcp.call_tool("get_guide", {}))
        for guide in listing["guides"]:
            with self.subTest(slug=guide["slug"]):
                result = payload(await server.mcp.call_tool("get_guide", {"slug": guide["slug"]}))
                self.assertTrue(result["ok"])
                self.assertTrue(result["markdown"].strip())


if __name__ == "__main__":
    unittest.main()
