from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Client session identifier")
    message: str = Field(..., min_length=1, description="User message")


class ChatResponse(BaseModel):
    session_id: str
    answer: str
