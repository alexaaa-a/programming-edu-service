from pydantic import BaseModel, Field


class PathStep(BaseModel):
    kind: str
    name: str
    status: str
    detail: str = ""


class ChatRequest(BaseModel):
    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Client session identifier",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User message",
    )
    task_title: str | None = Field(None, min_length=1, max_length=200, description="Task title context (optional)")
    task_description: str | None = Field(None, min_length=1, max_length=8000, description="Task description context (optional)")
    task_id: int | None = Field(None, description="Task id for trajectory briefing (optional)")
    emma_briefing: str | None = Field(
        None,
        max_length=800,
        description="Падающий тест из последнего ревью для одной сессии Эммы",
    )
    solo_only: bool = Field(
        False,
        description="Стажёрский грейд: один спикер за ход, без совещания",
    )
    turn_id: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        description="Optional idempotency key to resume the same LangGraph turn",
    )


class ChatHistoryMessage(BaseModel):
    id: str
    role: str
    text: str
    sender: str | None = None
    created_at: str = ""


class ChatHistoryResponse(BaseModel):
    messages: list[ChatHistoryMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    speaker: str
    role: str
    mode: str = "solo"
    advisors: list[str] = Field(default_factory=list)
    agent_path: list[PathStep] = Field(default_factory=list)


class ChatNudgeRequest(BaseModel):
    session_id: str = ""
    task_title: str | None = None


class ChatNudgeResponse(BaseModel):
    sent: bool = False
    message: str = ""
    speaker_id: str = ""
    speaker_name: str = ""
    speaker_role: str = ""
    kind: str = ""
    task_id: int | None = None
