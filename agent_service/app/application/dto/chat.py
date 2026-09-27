from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PathStepResult:
    kind: str
    name: str
    status: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    answer: str
    speaker_id: str
    speaker_name: str
    speaker_role: str
    mode: str
    advisors: list[str] = field(default_factory=list)
    agent_path: list[PathStepResult] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ChatWithTeamResult:
    session_id: str
    answer: str
    speaker_id: str
    speaker_name: str
    speaker_role: str
    mode: str
    advisors: list[str] = field(default_factory=list)
    agent_path: list[PathStepResult] = field(default_factory=list)
