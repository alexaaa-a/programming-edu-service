from typing import Any, Mapping, Protocol, Sequence

from agent_service.app.application.decisions.questions import Answers, Question


class DecisionModelInterface(Protocol):
    @property
    def enabled(self) -> bool:
        raise NotImplementedError

    async def ask(
            self,
            state: str | Mapping[str, Any],
            questions: Sequence[Question],
            label: str = "",
    ) -> Answers:
        raise NotImplementedError
