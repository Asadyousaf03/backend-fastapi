import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from schemas import AgentLogEntry, AgentLogHistory, StreamLogEvent

router = APIRouter()

AGENT_STEPS: list[StreamLogEvent] = [
    StreamLogEvent(step=1, message="Initializing Multi-Agent Orchestrator...", level="info"),
    StreamLogEvent(step=2, message="Inspecting database via pgvector context...", level="info"),
    StreamLogEvent(step=3, message="Consulting Claude Sonnet 3.5 tool pipeline...", level="info"),
    StreamLogEvent(step=4, message="Injecting final layout into memory blocks...", level="info"),
    StreamLogEvent(
        step=5,
        message="Workflow execution successfully finished!",
        level="success",
    ),
]


@router.get("/api/agent-logs")
async def stream_agent_logs(request: Request) -> StreamingResponse:
    session_id = str(uuid4())

    async def log_generator():
        history_entries: list[AgentLogEntry] = []

        for event in AGENT_STEPS:
            if await request.is_disconnected():
                break

            history_entries.append(
                AgentLogEntry(
                    step=event.step,
                    message=event.message,
                    level=event.level,
                    timestamp=datetime.now(UTC),
                )
            )
            yield f"data: {event.model_dump_json()}\n\n"
            await asyncio.sleep(1.5)

        history = AgentLogHistory(
            session_id=session_id,
            status="completed",
            entries=history_entries,
        )
        yield f"event: complete\ndata: {history.model_dump_json()}\n\n"

    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
