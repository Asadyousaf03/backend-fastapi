from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeResponse(BaseModel):
    status: str
    summary: str
    actions: list[str]
    confidence_score: float = Field(ge=0.0, le=1.0)


class AnalyzeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None


LogLevel = Literal["info", "warn", "error", "success"]
LogSessionStatus = Literal["running", "completed", "failed"]


class AgentLogEntry(BaseModel):
    step: int = Field(ge=1)
    message: str
    level: LogLevel = "info"
    timestamp: datetime


class AgentLogHistory(BaseModel):
    session_id: str
    status: LogSessionStatus
    entries: list[AgentLogEntry]


class StreamLogEvent(BaseModel):
    step: int = Field(ge=1)
    message: str
    level: LogLevel = "info"
