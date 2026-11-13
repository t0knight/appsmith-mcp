import unittest

from appsmith_mcp import server


class ToolAnnotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_registered_tool_has_explicit_annotations(self):
        for tool in await server.mcp.list_tools():
            with self.subTest(tool=tool.name):
                self.assertIsNotNone(tool.annotations)
                values = tool.annotations.model_dump(exclude_none=True)
                self.assertTrue({"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"} <= values.keys())

    async def test_effects_are_classified_by_behavior_not_name(self):
        tools = {tool.name: tool.annotations for tool in await server.mcp.list_tools()}
        reads = tools["get_widget"]
        self.assertTrue(reads.readOnlyHint)
        self.assertFalse(reads.openWorldHint)
        for name in ["delete_pages", "clear_canvas", "import_page", "update_widgets"]:
            with self.subTest(tool=name):
                self.assertFalse(tools[name].readOnlyHint)
                self.assertTrue(tools[name].destructiveHint)
        for name in ["capture_screenshot", "preview_hidden", "export_page"]:
            with self.subTest(tool=name):
                self.assertFalse(tools[name].readOnlyHint)
        self.assertTrue(tools["export_page"].openWorldHint)
        self.assertTrue(tools["execute_queries"].openWorldHint)
        self.assertFalse(tools["execute_queries"].readOnlyHint)
        self.assertFalse(tools["create_pages"].destructiveHint)

    async def test_unclassified_tool_cannot_be_registered(self):
        from appsmith_mcp.protocol import AppsmithMCP

        async def unclassified_tool() -> dict:
            return {}

        with self.assertRaisesRegex(ValueError, "unclassified_tool"):
            AppsmithMCP("test").add_tool(unclassified_tool)


if __name__ == "__main__":
    unittest.main()
