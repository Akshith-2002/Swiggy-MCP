"""
Two-phase agent orchestrator.

Phase 1 (plan): all read tools + cart-prep tools available; book_table /
checkout / place_food_order / clear_cart are withheld. Agent loops until
it produces a final itinerary.

Phase 2 (execute): after user confirms in the UI, prior messages are
replayed with the full tool set and the agent fires the writes.

Events yielded as dicts; the FastAPI layer serializes them as SSE.
"""

from anthropic import AsyncAnthropic

from agent.mcp_client import MCPMultiClient
from agent.prompts import EXECUTION_PROMPT, PLANNING_PROMPT

WRITE_TOOLS = {"book_table", "checkout", "place_food_order", "clear_cart"}


class EveningPlanner:
    def __init__(self, anthropic_client: AsyncAnthropic, model: str):
        self.client = anthropic_client
        self.model = model

    async def plan(self, mcp: MCPMultiClient, user_prompt: str):
        tools = [t for t in mcp.tools if t["name"] not in WRITE_TOOLS]
        messages = [{"role": "user", "content": user_prompt}]
        async for event in self._run_loop(mcp, messages, tools, PLANNING_PROMPT):
            yield event
        yield {"type": "awaiting_confirmation", "messages": messages}

    async def execute(self, mcp: MCPMultiClient, prior_messages: list):
        tools = mcp.tools
        messages = prior_messages + [{
            "role": "user",
            "content": "Confirmed. Execute the plan now — book the table and place the Instamart order.",
        }]
        async for event in self._run_loop(mcp, messages, tools, EXECUTION_PROMPT):
            yield event

    async def _run_loop(self, mcp, messages, tools, system_prompt):
        while True:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            assistant_content = []
            for block in response.content:
                if block.type == "text":
                    yield {"type": "text", "content": block.text}
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    yield {
                        "type": "tool_call",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                        "server": mcp.server_for_tool(block.name),
                    }
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result_text = await mcp.call_tool(block.name, block.input)
                    yield {
                        "type": "tool_result",
                        "id": block.id,
                        "name": block.name,
                        "result": result_text,
                    }
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })
                messages.append({"role": "user", "content": tool_results})
                continue

            break  # unknown stop reason
