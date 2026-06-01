"""
Swiggy Instamart MCP Server (stub)

Mirrors the 13-tool surface area from Swiggy's MCP docs.
Replace the data layer with real Swiggy endpoints after production approval.
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
PRODUCTS = json.loads((DATA_DIR / "instamart_products.json").read_text())
ADDRESSES = json.loads((DATA_DIR / "addresses.json").read_text())

MIN_ORDER = 99
DELIVERY_FEE = 25

_CARTS: dict[str, dict] = {}
_ORDERS: dict[str, dict] = {}

server = Server("swiggy-instamart")


def _text(payload: dict) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


def _cart_summary(cart: dict) -> dict:
    subtotal = sum(item["price"] * item["quantity"] for item in cart["items"])
    return {
        **cart,
        "subtotal": subtotal,
        "delivery_fee": DELIVERY_FEE if subtotal > 0 else 0,
        "total": subtotal + (DELIVERY_FEE if subtotal > 0 else 0),
        "meets_minimum": subtotal >= MIN_ORDER,
    }


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_addresses",
            description="Retrieve the user's saved delivery addresses for Instamart.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="search_products",
            description=(
                "Search Instamart catalog by keyword or category. "
                "Categories include 'Flowers', 'Dessert', 'Groceries', etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword e.g. 'roses', 'cake'"},
                    "category": {"type": "string"},
                    "in_stock_only": {"type": "boolean", "default": True},
                    "max_price": {"type": "number"},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_product_details",
            description="Get full details for a product including stock, delivery time, and description.",
            inputSchema={
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        ),
        types.Tool(
            name="update_cart",
            description=(
                "Add, update, or remove an item in the Instamart cart. "
                "Pass quantity=0 to remove. Cart binds to delivery address — changing address risks serviceability failure."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "address_id": {"type": "string", "description": "Delivery address to bind cart to"},
                    "product_id": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 0},
                },
                "required": ["address_id", "product_id", "quantity"],
            },
        ),
        types.Tool(
            name="get_cart",
            description=(
                "Get the authoritative cart state from the server. "
                "Call this at every turn boundary — don't cache locally."
            ),
            inputSchema={
                "type": "object",
                "properties": {"address_id": {"type": "string"}},
                "required": ["address_id"],
            },
        ),
        types.Tool(
            name="clear_cart",
            description="Empty the cart for a delivery address.",
            inputSchema={
                "type": "object",
                "properties": {"address_id": {"type": "string"}},
                "required": ["address_id"],
            },
        ),
        types.Tool(
            name="your_go_to_items",
            description="Suggest the user's frequently purchased Instamart items.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="fetch_coupons",
            description="List available Instamart discount codes for the current cart.",
            inputSchema={
                "type": "object",
                "properties": {"address_id": {"type": "string"}},
                "required": ["address_id"],
            },
        ),
        types.Tool(
            name="apply_coupon",
            description="Apply a coupon code to the cart.",
            inputSchema={
                "type": "object",
                "properties": {
                    "address_id": {"type": "string"},
                    "coupon_code": {"type": "string"},
                },
                "required": ["address_id", "coupon_code"],
            },
        ),
        types.Tool(
            name="checkout",
            description=(
                "Place the Instamart order. NON-IDEMPOTENT — on failure, call get_orders before retrying. "
                "Always confirm with user before calling. Optional scheduled_for ISO timestamp for delayed delivery."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "address_id": {"type": "string"},
                    "scheduled_for": {
                        "type": "string",
                        "description": "Optional ISO timestamp for scheduled delivery; omit for ASAP",
                    },
                    "payment_method": {"type": "string", "default": "UPI"},
                },
                "required": ["address_id"],
            },
        ),
        types.Tool(
            name="get_orders",
            description="List recent Instamart orders for the user.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="track_order",
            description="Get real-time delivery status and ETA for an order.",
            inputSchema={
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
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
    if name == "get_addresses":
        return _text({"success": True, "addresses": ADDRESSES})

    if name == "search_products":
        results = PRODUCTS[:]
        query = (arguments.get("query") or "").lower().strip()
        category = arguments.get("category")
        in_stock_only = arguments.get("in_stock_only", True)
        max_price = arguments.get("max_price")

        if query:
            results = [p for p in results if query in p["name"].lower() or query in p["description"].lower()]
        if category:
            results = [p for p in results if p["category"].lower() == category.lower()]
        if in_stock_only:
            results = [p for p in results if p["in_stock"]]
        if max_price is not None:
            results = [p for p in results if p["price"] <= max_price]

        return _text({"success": True, "count": len(results), "results": results})

    if name == "get_product_details":
        pid = arguments["product_id"]
        match = next((p for p in PRODUCTS if p["id"] == pid), None)
        if not match:
            return _text({"success": False, "error": "PRODUCT_NOT_FOUND"})
        return _text({"success": True, "product": match})

    if name == "update_cart":
        address_id = arguments["address_id"]
        product_id = arguments["product_id"]
        quantity = arguments["quantity"]

        cart = _CARTS.setdefault(address_id, {
            "cart_id": f"IM_CART_{uuid.uuid4().hex[:8].upper()}",
            "address_id": address_id,
            "items": [],
        })

        product = next((p for p in PRODUCTS if p["id"] == product_id), None)
        if not product:
            return _text({"success": False, "error": "PRODUCT_NOT_FOUND"})
        if not product["in_stock"]:
            return _text({"success": False, "error": "ITEM_OUT_OF_STOCK", "product_id": product_id})

        cart["items"] = [i for i in cart["items"] if i["product_id"] != product_id]
        if quantity > 0:
            cart["items"].append({
                "product_id": product_id,
                "name": product["name"],
                "price": product["price"],
                "quantity": quantity,
            })

        return _text({"success": True, "cart": _cart_summary(cart)})

    if name == "get_cart":
        address_id = arguments["address_id"]
        cart = _CARTS.get(address_id, {
            "cart_id": None,
            "address_id": address_id,
            "items": [],
        })
        return _text({"success": True, "cart": _cart_summary(cart)})

    if name == "clear_cart":
        address_id = arguments["address_id"]
        _CARTS.pop(address_id, None)
        return _text({"success": True, "message": "Cart cleared."})

    if name == "your_go_to_items":
        return _text({
            "success": True,
            "items": [PRODUCTS[0], PRODUCTS[4]],  # Roses + truffle cake
        })

    if name == "fetch_coupons":
        return _text({
            "success": True,
            "coupons": [
                {"code": "WELCOME50", "description": "₹50 off on orders above ₹399", "discount": 50},
                {"code": "INSTASAVE", "description": "10% off up to ₹100", "discount_percent": 10, "max_discount": 100},
            ],
        })

    if name == "apply_coupon":
        return _text({
            "success": True,
            "applied": arguments["coupon_code"],
            "discount": 50,
        })

    if name == "checkout":
        address_id = arguments["address_id"]
        cart = _CARTS.get(address_id)
        if not cart or not cart["items"]:
            return _text({"success": False, "error": "EMPTY_CART"})
        summary = _cart_summary(cart)
        if not summary["meets_minimum"]:
            return _text({"success": False, "error": "MIN_ORDER_NOT_MET", "min": MIN_ORDER, "current": summary["subtotal"]})

        order_id = f"IM_ORD_{uuid.uuid4().hex[:8].upper()}"
        _ORDERS[order_id] = {
            "order_id": order_id,
            "status": "CONFIRMED",
            "items": cart["items"],
            "total": summary["total"],
            "address_id": address_id,
            "scheduled_for": arguments.get("scheduled_for"),
            "payment_method": arguments.get("payment_method", "UPI"),
            "confirmation_code": f"SW-{uuid.uuid4().hex[:4].upper()}",
            "placed_at": datetime.now().isoformat(),
            "eta_minutes": 25,
        }
        _CARTS.pop(address_id, None)
        return _text({"success": True, "order": _ORDERS[order_id]})

    if name == "get_orders":
        return _text({"success": True, "orders": list(_ORDERS.values())})

    if name == "track_order":
        oid = arguments["order_id"]
        order = _ORDERS.get(oid)
        if not order:
            return _text({"success": False, "error": "ORDER_NOT_FOUND"})
        return _text({
            "success": True,
            "order_id": oid,
            "status": order["status"],
            "eta_minutes": order["eta_minutes"],
            "rider": {"name": "Ramesh K.", "phone": "+91-XXXXXXXXXX"},
        })

    if name == "report_error":
        return _text({
            "success": True,
            "report_id": f"ERR_{uuid.uuid4().hex[:8].upper()}",
            "message": "Diagnostic captured.",
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
