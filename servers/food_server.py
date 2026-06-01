"""
Swiggy Food MCP Server (stub, lightweight)

Implements key tools for the demo. Full surface area (14 tools) is exposed,
but the agent's primary demo path doesn't exercise food delivery.
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

DATA_DIR = Path(__file__).parent.parent / "data"
ADDRESSES = json.loads((DATA_DIR / "addresses.json").read_text())

CART_CAP = 1000

server = Server("swiggy-food")

_RESTAURANTS = [
    {
        "id": "FD_R_001",
        "name": "Meghana Foods",
        "cuisine": ["Andhra", "Biryani"],
        "rating": 4.4,
        "delivery_minutes": 32,
        "availabilityStatus": "OPEN",
    },
    {
        "id": "FD_R_002",
        "name": "Empire Restaurant",
        "cuisine": ["North Indian", "Chinese"],
        "rating": 4.2,
        "delivery_minutes": 28,
        "availabilityStatus": "OPEN",
    },
]


def _text(payload: dict) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name="get_addresses", description="Retrieve delivery addresses.",
                   inputSchema={"type": "object", "properties": {}, "required": []}),
        types.Tool(name="search_restaurants", description="Search Food delivery restaurants.",
                   inputSchema={"type": "object", "properties": {"query": {"type": "string"}}, "required": []}),
        types.Tool(name="get_restaurant_menu", description="Get a restaurant's menu.",
                   inputSchema={"type": "object", "properties": {"restaurant_id": {"type": "string"}}, "required": ["restaurant_id"]}),
        types.Tool(name="get_food_cart", description="Read the food cart (server-authoritative).",
                   inputSchema={"type": "object", "properties": {}, "required": []}),
        types.Tool(name="place_food_order", description=f"Place food order (COD only in v1, ₹{CART_CAP} cap). Non-idempotent.",
                   inputSchema={"type": "object", "properties": {}, "required": []}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_addresses":
        return _text({"success": True, "addresses": ADDRESSES})
    if name == "search_restaurants":
        return _text({"success": True, "results": _RESTAURANTS})
    if name == "get_restaurant_menu":
        return _text({"success": True, "menu": [{"id": "ITM1", "name": "Veg Biryani", "price": 269}]})
    if name == "get_food_cart":
        return _text({"success": True, "cart": {"items": [], "total": 0}})
    if name == "place_food_order":
        return _text({"success": True, "order_id": f"FD_ORD_{uuid.uuid4().hex[:8].upper()}"})
    return _text({"success": False, "error": f"UNKNOWN_TOOL:{name}"})


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
