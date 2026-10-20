"""MCP registration and argument contracts, independent of the editor connection."""

import inspect

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from appsmith_mcp.tool_annotations import annotations_for


STRICT_ARGUMENT_TOOLS = frozenset({"configure_table", "set_validation"})


class AppsmithMCP(FastMCP):
    def __init__(self, *args, **kwargs):
        self._strict_arguments = {}
        super().__init__(*args, **kwargs)

    def add_tool(self, fn, name=None, **kwargs):
        tool_name = name or fn.__name__
        kwargs["annotations"] = annotations_for(tool_name)
        if tool_name in STRICT_ARGUMENT_TOOLS:
            self._strict_arguments[tool_name] = frozenset(inspect.signature(fn).parameters)
        super().add_tool(fn, name=name, **kwargs)

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            if tool.name in self._strict_arguments:
                tool.inputSchema = {**tool.inputSchema, "additionalProperties": False}
        return tools

    async def call_tool(self, name, arguments):
        # FastMCP's argument model ignores extra fields by default. Reject typos before
        # its conversion drops them and a handler reads or mutates the editor.
        allowed = self._strict_arguments.get(name)
        if allowed is not None:
            unknown = sorted(set(arguments) - allowed)
            if unknown:
                raise ToolError(f"{name}: unknown argument(s) {unknown}; valid: {sorted(allowed)}")
        return await super().call_tool(name, arguments)
