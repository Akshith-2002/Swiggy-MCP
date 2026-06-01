"""
Swiggy Dineout MCP Server (stub)

Mirrors the 8-tool surface area from Swiggy's MCP docs.
Replace the data layer with real Swiggy endpoints after production approval.
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, time
from pathlib import Path

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

DATA_DIR = Path(__file__).parent.parent / "data"
RESTAURANTS = json.loads((DATA_DIR / "dineout_restaurants.json").read_text())
ADDRESSES = json.loads((DATA_DIR / "addresses.json").read_text())

_CARTS: dict[str, dict] = {}
_BOOKINGS: dict[str, dict] = {}

server = Server("swiggy-dineout")


def _text(payload: dict) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


def _generate_slots(date_str: str) -> list[dict]:
    base = datetime.strptime(date_str, "%Y-%m-%d")
    slots = []
    for hour in [12, 12.5, 13, 13.5, 19, 19.5, 20, 20.5, 21, 21.5]:
        h, m = int(hour), int((hour % 1) * 60)
        dt = base.replace(hour=h, minute=m)
        slots.append({
            "slot_id": f"SLOT_{dt.strftime('%Y%m%d_%H%M')}",
            "time": dt.strftime("%H:%M"),
            "meal": "lunch" if h < 17 else "dinner",
            "available": True,
            "deal_percent_off": 0,
        })
    return slots


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_saved_locations",
            description="Retrieve the user's saved addresses for Dineout (Home, Office, etc).",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="search_restaurants_dineout",
            description=(
                "Search Dineout-bookable restaurants. Filter by area, cuisine, minimum rating, "
                "vegetarian preference, or amenities (e.g. 'Date Night', 'Romantic')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "area": {"type": "string", "description": "Locality, e.g. 'Indiranagar'"},
                    "cuisine": {"type": "string", "description": "Cuisine filter"},
                    "min_rating": {"type": "number", "description": "Minimum rating, e.g. 4.3"},
                    "vegetarian": {"type": "boolean", "description": "Restrict to vegetarian-friendly or pure-veg"},
                    "amenities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required amenities like 'Date Night', 'Romantic'",
                    },
                    "max_price_for_two": {"type": "number"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_restaurant_details",
            description="Get full details for a restaurant: amenities, popular dishes, address, ratings.",
            inputSchema={
                "type": "object",
                "properties": {"restaurant_id": {"type": "string"}},
                "required": ["restaurant_id"],
            },
        ),
        types.Tool(
            name="get_available_slots",
            description="Check available reservation slots over a date window (up to 7 days).",
            inputSchema={
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD; defaults to today"},
                    "party_size": {"type": "integer", "default": 2},
                },
                "required": ["restaurant_id"],
            },
        ),
        types.Tool(
            name="create_cart",
            description="Initialize a Dineout reservation cart. Returns a cart_id used for booking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "restaurant_id": {"type": "string"},
                    "slot_id": {"type": "string"},
                    "party_size": {"type": "integer", "default": 2},
                },
                "required": ["restaurant_id", "slot_id", "party_size"],
            },
        ),
        types.Tool(
            name="book_table",
            description=(
                "Reserve the table. NON-IDEMPOTENT — on failure, call get_booking_status before retrying. "
                "Always confirm with user before calling this."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cart_id": {"type": "string"},
                    "guest_name": {"type": "string"},
                    "guest_phone": {"type": "string"},
                },
                "required": ["cart_id"],
            },
        ),
        types.Tool(
            name="get_booking_status",
            description="Retrieve confirmation status and details for a booking_id.",
            inputSchema={
                "type": "object",
                "properties": {"booking_id": {"type": "string"}},
                "required": ["booking_id"],
            },
        ),
        types.Tool(
            name="report_error",
            description="Generate a diagnostic report for support escalation.",
            inputSchema={
                "type": "object",
                "properties": {"context": {"type": "string"}},
                "required": ["context"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "get_saved_locations":
        return _text({"success": True, "addresses": ADDRESSES})

    if name == "search_restaurants_dineout":
        results = RESTAURANTS[:]
        area = arguments.get("area")
        cuisine = arguments.get("cuisine")
        min_rating = arguments.get("min_rating")
        vegetarian = arguments.get("vegetarian")
        amenities = arguments.get("amenities") or []
        max_price = arguments.get("max_price_for_two")

        if area:
            results = [r for r in results if area.lower() in r["area"].lower()]
        if cuisine:
            results = [r for r in results if any(cuisine.lower() in c.lower() for c in r["cuisine"])]
        if min_rating is not None:
            results = [r for r in results if r["rating"] >= min_rating]
        if vegetarian:
            results = [
                r for r in results
                if r["is_pure_veg"] or "Vegetarian" in r["amenities"] or "Vegetarian Options" in r["amenities"]
            ]
        if amenities:
            results = [r for r in results if all(a in r["amenities"] for a in amenities)]
        if max_price is not None:
            results = [r for r in results if r["price_for_two"] <= max_price]

        results.sort(key=lambda r: r["rating"], reverse=True)
        return _text({"success": True, "count": len(results), "results": results})

    if name == "get_restaurant_details":
        rid = arguments["restaurant_id"]
        match = next((r for r in RESTAURANTS if r["id"] == rid), None)
        if not match:
            return _text({"success": False, "error": "RESTAURANT_NOT_FOUND"})
        return _text({"success": True, "restaurant": match})

    if name == "get_available_slots":
        rid = arguments["restaurant_id"]
        date_str = arguments.get("date") or datetime.now().strftime("%Y-%m-%d")
        party = arguments.get("party_size", 2)
        match = next((r for r in RESTAURANTS if r["id"] == rid), None)
        if not match:
            return _text({"success": False, "error": "RESTAURANT_NOT_FOUND"})
        return _text({
            "success": True,
            "restaurant_id": rid,
            "restaurant_name": match["name"],
            "date": date_str,
            "party_size": party,
            "slots": _generate_slots(date_str),
        })

    if name == "create_cart":
        rid = arguments["restaurant_id"]
        slot_id = arguments["slot_id"]
        party = arguments.get("party_size", 2)
        restaurant = next((r for r in RESTAURANTS if r["id"] == rid), None)
        if not restaurant:
            return _text({"success": False, "error": "RESTAURANT_NOT_FOUND"})
        cart_id = f"DO_CART_{uuid.uuid4().hex[:8].upper()}"
        _CARTS[cart_id] = {
            "cart_id": cart_id,
            "restaurant_id": rid,
            "restaurant_name": restaurant["name"],
            "slot_id": slot_id,
            "party_size": party,
            "booking_fee": 0,
        }
        return _text({"success": True, "cart": _CARTS[cart_id]})

    if name == "book_table":
        cart_id = arguments["cart_id"]
        cart = _CARTS.get(cart_id)
        if not cart:
            return _text({"success": False, "error": "CART_NOT_FOUND"})
        booking_id = f"DO_BK_{uuid.uuid4().hex[:8].upper()}"
        _BOOKINGS[booking_id] = {
            "booking_id": booking_id,
            "status": "CONFIRMED",
            "cart": cart,
            "guest_name": arguments.get("guest_name", "Guest"),
            "guest_phone": arguments.get("guest_phone", "+91-XXXXXXXXXX"),
            "confirmation_code": f"DO-{uuid.uuid4().hex[:4].upper()}",
            "booked_at": datetime.now().isoformat(),
        }
        return _text({"success": True, "booking": _BOOKINGS[booking_id]})

    if name == "get_booking_status":
        bid = arguments["booking_id"]
        booking = _BOOKINGS.get(bid)
        if not booking:
            return _text({"success": False, "error": "BOOKING_NOT_FOUND"})
        return _text({"success": True, "booking": booking})

    if name == "report_error":
        return _text({
            "success": True,
            "report_id": f"ERR_{uuid.uuid4().hex[:8].upper()}",
            "message": "Diagnostic captured. Swiggy support will be in touch.",
        })

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
