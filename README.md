# Evening Planner — built on Swiggy MCP

A multi-server MCP agent that plans a complete evening in one prompt.
Orchestrates **Swiggy Dineout** (restaurant reservation), **Swiggy Instamart**
(flowers + dessert scheduled delivery), and **Swiggy Food** (delivery)
through real MCP servers, with a Claude-styled chat UI streaming every
tool call live.

This is a working demo built against **stub MCP servers** that mirror Swiggy's
exact tool surface area (Dineout 8 tools, Instamart 13 tools, Food 5 tools).
Swap the stdio transport for `streamablehttp_client` pointed at
`mcp.swiggy.com` once you receive production credentials and the same agent
code works unchanged.

## What it shows off

- **Multi-MCP orchestration** — agent coordinates across 3 separate MCP server processes in a single conversation.
- **Budget-aware planning** — explicit ₹ reasoning, surfaces breakdown vs. cap.
- **Dietary constraint handling** — filters Dineout for vegetarian-friendly + pure-veg.
- **Confirmation-before-write safety** — non-idempotent tools (`book_table`, `checkout`) are withheld from the planning phase and only fire after explicit user confirmation, exactly matching Swiggy's documented safety pattern.
- **Server-authoritative cart state** — `get_cart` is called every turn, no client-side caching drift.
- **Streaming UI** — Server-Sent Events render tool calls and results live, like Claude.ai's tool-use disclosure.

## Setup

```bash
cd /Users/akshithkumaryv/Downloads/swiggy_MCP
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and add ANTHROPIC_API_KEY
```

## Run

```bash
source .venv/bin/activate
uvicorn web.server:app --reload --port 8000
```

Open http://localhost:8000.

## Try

Type one of:

- `Plan a date night in Indiranagar tonight, ₹3500 budget, she's vegetarian. Flowers + dessert to home after.`
- `Anniversary dinner in Indiranagar, ₹5000, pure-veg only. Roses + cake home by 10:30.`
- `Veg-friendly romantic dinner near HSR, ₹3000, dessert delivery after.`

Watch the agent:
1. Search Dineout for ≥4.3-rated veg-friendly spots
2. Pick one, pull available 8pm slots, create a reservation cart
3. Pull your home address from Instamart
4. Search products for flowers + dessert, add to cart
5. Present a full itinerary with the budget breakdown
6. Wait for you to tap **Confirm & book** — only then does it fire `book_table` and `checkout`

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (web/static/) — Claude-styled chat UI, SSE consumer    │
└──────────────────────────────┬──────────────────────────────────┘
                               │ SSE
┌──────────────────────────────▼──────────────────────────────────┐
│  FastAPI (web/server.py) — /api/plan, /api/confirm              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  EveningPlanner (agent/orchestrator.py) — two-phase agent loop  │
│  • Phase 1: read tools only, ends with itinerary                │
│  • Phase 2: full tools, fires book_table + checkout             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  MCPMultiClient (agent/mcp_client.py) — stdio fan-out           │
└─────────┬─────────────────────┬──────────────────────┬──────────┘
          │                     │                      │
   ┌──────▼──────┐      ┌───────▼──────┐      ┌────────▼──────┐
   │ Dineout MCP │      │ Instamart MCP│      │   Food MCP    │
   │ (8 tools)   │      │ (13 tools)   │      │   (5 tools)   │
   └─────────────┘      └──────────────┘      └───────────────┘
```

## Project layout

```
swiggy_MCP/
├── agent/
│   ├── mcp_client.py      # spawns + multiplexes the 3 MCP servers
│   ├── orchestrator.py    # two-phase agent loop
│   └── prompts.py         # planning + execution system prompts
├── servers/
│   ├── dineout_server.py  # 8 tools, full surface area
│   ├── instamart_server.py# 13 tools, full surface area
│   └── food_server.py     # 5 tools, lightweight stub
├── data/
│   ├── dineout_restaurants.json
│   ├── instamart_products.json
│   └── addresses.json
├── web/
│   ├── server.py          # FastAPI + SSE
│   └── static/
│       ├── index.html     # Claude-styled chat UI
│       ├── styles.css     # warm cream palette, serif headings
│       └── app.js         # SSE consumer, markdown renderer
├── requirements.txt
└── README.md
```

## Migrating to real Swiggy MCP

Edit `agent/mcp_client.py`:

```python
# from
from mcp.client.stdio import stdio_client
...
transport = await self._stack.enter_async_context(stdio_client(params))

# to
from mcp.client.streamable_http import streamablehttp_client
...
url = f"https://mcp.swiggy.com/{server_name}"
transport = await self._stack.enter_async_context(
    streamablehttp_client(url, headers={"Authorization": f"Bearer {token}"})
)
```

Add OAuth 2.1 PKCE flow per Swiggy docs to obtain the token. The agent loop
and prompts work unchanged.
