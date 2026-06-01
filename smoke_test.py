"""Smoke test: spawn the 3 stub MCP servers, list tools, call a few read tools."""

import asyncio
import json
import sys

from agent.mcp_client import MCPMultiClient


async def main():
    print("→ Spawning 3 stub MCP servers via stdio…")
    async with MCPMultiClient() as mcp:
        print(f"✓ Sessions: {list(mcp.sessions.keys())}")
        print(f"✓ Total tools registered: {len(mcp.tools)}")

        # Group by server
        by_server: dict[str, list[str]] = {}
        for tool_name, server in mcp.tool_to_server.items():
            by_server.setdefault(server, []).append(tool_name)
        for server, names in by_server.items():
            print(f"\n  [{server}] {len(names)} tools:")
            for n in sorted(names):
                print(f"    • {n}")

        print("\n→ Calling search_restaurants_dineout (Indiranagar, veg, 4.3+)…")
        result = await mcp.call_tool(
            "search_restaurants_dineout",
            {"area": "Indiranagar", "min_rating": 4.3, "vegetarian": True},
        )
        parsed = json.loads(result)
        print(f"  ✓ Found {parsed['count']} restaurants:")
        for r in parsed["results"]:
            print(f"    • {r['name']} ({r['rating']}★, ₹{r['price_for_two']}/2)")

        print("\n→ Calling search_products (Instamart, flowers)…")
        result = await mcp.call_tool(
            "search_products", {"category": "Flowers", "in_stock_only": True}
        )
        parsed = json.loads(result)
        print(f"  ✓ Found {parsed['count']} in-stock flower products")
        for p in parsed["results"]:
            print(f"    • {p['name']} — ₹{p['price']}")

        print("\n→ Calling get_addresses (Instamart)…")
        result = await mcp.call_tool("get_addresses", {})
        parsed = json.loads(result)
        print(f"  ✓ {len(parsed['addresses'])} saved addresses")

        print("\n✅ All MCP servers wired up correctly.")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
