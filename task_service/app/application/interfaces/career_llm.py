from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PeerSnippet:
    code: str
    bug: str


@dataclass(frozen=True, slots=True)
class NightIncidentDraft:
    scene: str
    code: str
    expect: str


@dataclass(frozen=True, slots=True)
class PeerGrade:
    found: bool
    emma: str


class CareerLlmInterface(Protocol):
    async def generate_peer_snippet(self) -> PeerSnippet | None:
        raise NotImplementedError

    async def generate_night_incident(self) -> NightIncidentDraft | None:
        raise NotImplementedError

    async def grade_peer_note(self, code: str, bug: str, note: str) -> PeerGrade | None:
        raise NotImplementedError

    async def grade_demo_answer(self, criterion: str, answer: str) -> bool | None:
        raise NotImplementedError
