"""
Multi-server MCP client.

Spawns the 3 stub Swiggy MCP servers (Food, Instamart, Dineout) over stdio,
aggregates their tools into a single Anthropic-compatible tool list, and
routes tool calls to the right session.

To migrate to production: replace `stdio_client` with `streamablehttp_client`
pointed at mcp.swiggy.com/{food,instamart,dineout} and add the OAuth bearer.
"""

import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVERS_DIR = Path(__file__).parent.parent / "servers"

# Load order matters: when tool names collide across servers (e.g. `get_addresses`
# is on both Food and Instamart per Swiggy docs, `report_error` is on all three),
# the first-registered server wins. Instamart owns address-bound cart operations
# in this demo, so it must register `get_addresses` first.
SERVER_SCRIPTS = {
    "instamart": SERVERS_DIR / "instamart_server.py",
    "dineout": SERVERS_DIR / "dineout_server.py",
    "food": SERVERS_DIR / "food_server.py",
}


class MCPMultiClient:
    def __init__(self):
        self._stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}
        self.tool_to_server: dict[str, str] = {}
        self.tools: list[dict] = []

    async def __aenter__(self):
        await self._stack.__aenter__()
        python_exe = sys.executable or "python3"
        for server_name, script_path in SERVER_SCRIPTS.items():
            params = StdioServerParameters(
                command=python_exe,
                args=[str(script_path)],
                env=os.environ.copy(),
            )
            transport = await self._stack.enter_async_context(stdio_client(params))
            read, write = transport
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions[server_name] = session

            result = await session.list_tools()
            for tool in result.tools:
                if tool.name in self.tool_to_server:
                    # First-wins on cross-server tool name collisions
                    # (get_addresses, report_error are shared across Swiggy's servers).
                    continue
                self.tool_to_server[tool.name] = server_name
                self.tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                })
        return self

    async def __aexit__(self, *args):
        await self._stack.__aexit__(*args)

    async def call_tool(self, name: str, arguments: dict) -> str:
        server_name = self.tool_to_server.get(name)
        if not server_name:
            return f'{{"success": false, "error": "UNKNOWN_TOOL:{name}"}}'
        session = self.sessions[server_name]
        result = await session.call_tool(name, arguments)
        parts = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
        return "\n".join(parts)

    def server_for_tool(self, name: str) -> str:
        return self.tool_to_server.get(name, "mcp")
