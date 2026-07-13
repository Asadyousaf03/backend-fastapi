from pydantic import BaseModel, Field


class AnalyzeResponse(BaseModel):
    status: str
    summary: str
    actions: list[str]
    confidence_score: float = Field(ge=0.0, le=1.0)


class AnalyzeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
