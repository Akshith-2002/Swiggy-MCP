# Demo recording script (60–90 seconds)

For the Swiggy Builders Club application video. Use QuickTime screen recording
on a clean macOS desktop. 1280×720 minimum, 30fps.

## Setup (off-camera)

```bash
cd /Users/akshithkumaryv/Downloads/swiggy_MCP
source .venv/bin/activate
uvicorn web.server:app --port 8000
```

Open Chrome to `http://localhost:8000` in incognito (no extensions, clean
chrome). Resize browser to roughly 900×900. Hide the bookmarks bar.

## Beat-by-beat script

**[0:00 – 0:05] Cold open**
- Cursor lands on the Evening Planner page.
- Voice-over: *"An AI agent built on Swiggy's MCP — Dineout, Instamart, and Food, in one conversation."*

**[0:05 – 0:12] The prompt**
- Click the first suggestion chip:
  *"Plan a date night in Indiranagar tonight, ₹3500 budget, she's vegetarian. Flowers + dessert to home after."*
- Voice-over: *"One prompt — a vegetarian date night with flowers home after."*

**[0:12 – 0:42] The agent works**
- Tool-call cards stream in. As each appears, briefly call out what's happening:
  - `search_restaurants_dineout` (DINEOUT) → *"Searching Dineout — pure-veg-friendly, 4.3+ rating."*
  - `get_available_slots` (DINEOUT) → *"Pulling 8pm slots."*
  - `create_cart` (DINEOUT) → *"Locking the reservation."*
  - `get_addresses` (INSTAMART) → *"Finding the home address."*
  - `search_products` (INSTAMART) — twice → *"Roses, then dessert."*
  - `update_cart` (INSTAMART) — twice → *"Building the Instamart cart."*
  - `get_cart` (INSTAMART) → *"Refreshing the server-authoritative cart total."*

- Click on one of the tool-call cards mid-stream to expand it, showing the
  JSON request and response. Close it.
  - Voice-over: *"Every call is real MCP — input, output, full transparency."*

**[0:42 – 0:55] The itinerary**
- Itinerary card renders with:
  - 8:00 PM dinner at Burma Burma
  - 10:30 PM home delivery: roses + truffle cake
  - Total ₹X / ₹3500
- Voice-over: *"It picks Burma Burma — 4.6 stars, fully vegetarian — and schedules dessert at home for 10:30. Within budget."*

**[0:55 – 1:05] Confirmation safety**
- Hover over **Confirm & book**.
- Voice-over: *"It will not call any non-idempotent tool until I confirm — same safety pattern Swiggy's docs require."*
- Click **Confirm & book**.

**[1:05 – 1:20] Execution**
- Tool-call cards for `book_table` and `checkout` stream in.
- Final success card:
  - ✅ Reservation confirmed (DO-XXXX)
  - ✅ Delivery scheduled (SW-XXXX)
- Voice-over: *"Books the table. Schedules the delivery. Done."*

**[1:20 – 1:25] Outro**
- Voice-over: *"Three MCP servers. One conversation. Built with Claude on top of Swiggy's MCP stack."*

## Things to call out in the application form

When submitting the form, paste this technical summary:

> Built a working Evening Planner agent on three Swiggy MCP servers (Dineout 8
> tools, Instamart 13 tools, Food 5 tools) using the official Python MCP SDK
> and Anthropic's Claude Sonnet. Two-phase agent: planning phase uses read +
> cart-prep tools only, withholds book_table / checkout / place_food_order
> until explicit user confirmation. SSE-streamed UI shows every tool call and
> result transparently. Demo runs against stub MCP servers mirroring Swiggy's
> exact tool signatures; swapping to mcp.swiggy.com via streamable HTTP
> requires only a transport change in agent/mcp_client.py.

## Backup demo prompts

If the first run is awkward, try:
- *Anniversary dinner in Indiranagar, ₹5000, pure-veg only. Roses + cake home by 10:30.*
- *Veg-friendly romantic dinner near HSR, ₹3000, dessert delivery after.*
