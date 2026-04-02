from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Client session identifier")
    message: str = Field(..., min_length=1, description="User message")
    task_title: str | None = Field(None, min_length=1, max_length=200, description="Task title context (optional)")
    task_description: str | None = Field(None, min_length=1, max_length=8000, description="Task description context (optional)")


class ChatResponse(BaseModel):
    session_id: str
    answer: str
