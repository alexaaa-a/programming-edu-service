from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatWithTeamResult:
    session_id: str
    answer: str