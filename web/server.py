"""
FastAPI app exposing the Evening Planner over SSE.

- GET /              → serves the Claude-styled chat UI
- POST /api/plan     → SSE stream of the planning phase
- POST /api/confirm  → SSE stream of the execution phase (after user clicks Confirm)
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from agent.mcp_client import MCPMultiClient
from agent.orchestrator import EveningPlanner

load_dotenv()

WEB_DIR = Path(__file__).parent / "static"
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")

SESSIONS: dict[str, dict] = {}
MCP_CLIENT: MCPMultiClient | None = None
MCP_LOCK = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global MCP_CLIENT
    MCP_CLIENT = MCPMultiClient()
    await MCP_CLIENT.__aenter__()
    print(f"[startup] MCP servers connected: {list(MCP_CLIENT.sessions.keys())}")
    print(f"[startup] tools registered: {len(MCP_CLIENT.tools)}")
    yield
    await MCP_CLIENT.__aexit__(None, None, None)


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/meta")
async def meta():
    return {
        "model": MODEL,
        "servers": list(MCP_CLIENT.sessions.keys()) if MCP_CLIENT else [],
        "tool_count": len(MCP_CLIENT.tools) if MCP_CLIENT else 0,
    }


def _sse(event: str, payload: dict) -> dict:
    return {"event": event, "data": json.dumps(payload)}


@app.post("/api/plan")
async def plan(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return {"error": "empty prompt"}

    session_id = uuid.uuid4().hex[:8]
    anthropic = AsyncAnthropic()
    planner = EveningPlanner(anthropic, MODEL)

    async def stream():
        yield _sse("session", {"session_id": session_id})
        try:
            async with MCP_LOCK:
                async for event in planner.plan(MCP_CLIENT, prompt):
                    etype = event["type"]
                    if etype == "awaiting_confirmation":
                        SESSIONS[session_id] = {"messages": event["messages"]}
                        yield _sse("awaiting_confirmation", {"session_id": session_id})
                    else:
                        yield _sse(etype, event)
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
        yield _sse("done", {})

    return EventSourceResponse(stream())


@app.post("/api/confirm")
async def confirm(request: Request):
    body = await request.json()
    session_id = body.get("session_id")
    confirmed = bool(body.get("confirmed", True))

    if session_id not in SESSIONS:
        return {"error": "session not found"}

    session = SESSIONS.pop(session_id)
    anthropic = AsyncAnthropic()
    planner = EveningPlanner(anthropic, MODEL)

    async def stream():
        if not confirmed:
            yield _sse("cancelled", {})
            yield _sse("done", {})
            return
        try:
            async with MCP_LOCK:
                async for event in planner.execute(MCP_CLIENT, session["messages"]):
                    yield _sse(event["type"], event)
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
        yield _sse("done", {})

    return EventSourceResponse(stream())
