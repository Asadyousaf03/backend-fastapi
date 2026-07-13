import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

AGENT_STEPS = [
    "⚡ Initializing Multi-Agent Orchestrator...",
    "🔍 Inspecting database via pgvector context...",
    "🤖 Consulting Claude Sonnet 3.5 tool pipeline...",
    "⚙️ Injecting final layout into memory blocks...",
    "✅ Workflow execution successfully finished!",
]


@router.get("/api/agent-logs")
async def stream_agent_logs(request: Request) -> StreamingResponse:
    async def log_generator():
        for step in AGENT_STEPS:
            if await request.is_disconnected():
                break

            yield f"data: {step}\n\n"
            await asyncio.sleep(1.5)

    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
