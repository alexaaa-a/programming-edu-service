from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Review:
    score: int
    feedback: str
    suggestions: list[str] = field(default_factory=list)
