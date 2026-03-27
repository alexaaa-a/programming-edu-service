import logging
from typing import Any

from agent_service.app.application.base_agent import BaseAgent
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.skills import (
    BuildMentorPromptsSkill,
    LLMGenerateSkill,
)
from agent_service.app.application.observability.tracing import ensure_trace_id


class MentorAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm: LLMInterface,
        memory: MemoryInterface | None = None,
    ) -> None:
        super().__init__(llm=llm, memory=memory)
        self.skills = [
            BuildMentorPromptsSkill(),
            LLMGenerateSkill(llm=llm),
        ]
        self._build_prompts = self.skills[0]
        self._llm_generate = self.skills[1]

    async def run(self, code: str, results: Any) -> str:
        trace_id = ensure_trace_id()
        logger = logging.getLogger("agent_service")
        logger.info("pipeline.trace trace_id=%s agent=Mentor skill=BuildMentorPrompts start", trace_id)
        system_prompt, user_prompt = await self._build_prompts.run(code=code, results=results, trace_id=trace_id)
        logger.info("pipeline.trace trace_id=%s agent=Mentor skill=BuildMentorPrompts end", trace_id)
        logger.info("pipeline.trace trace_id=%s agent=Mentor skill=LLMGenerate start", trace_id)
        answer = await self._llm_generate.run(system_prompt=system_prompt, user_prompt=user_prompt, trace_id=trace_id)
        logger.info("pipeline.trace trace_id=%s agent=Mentor skill=LLMGenerate end", trace_id)
        return answer
