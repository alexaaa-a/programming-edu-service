import logging
from agent_service.app.application.base_agent import BaseAgent
from agent_service.app.application.dto import Review
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.skills import (
    DetectBugsSkill,
    LLMGenerateSkill,
    ParseReviewJSONSkill,
)
from agent_service.app.application.observability.tracing import ensure_trace_id


class BugAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm: LLMInterface,
        memory: MemoryInterface,
    ) -> None:
        super().__init__(llm=llm, memory=memory)
        self.skills = [
            DetectBugsSkill(memory=memory),
            LLMGenerateSkill(llm=llm),
            ParseReviewJSONSkill(),
        ]
        self._build_prompts = self.skills[0]
        self._llm_generate = self.skills[1]
        self._parse_review = self.skills[2]

    async def run(self, code: str) -> Review:
        trace_id = ensure_trace_id()
        logger = logging.getLogger("agent_service")
        logger.info("pipeline.trace trace_id=%s agent=Bug skill=BuildBugsPrompts start", trace_id)
        try:
            system_prompt, user_prompt = await self._build_prompts.run(code=code, trace_id=trace_id)
            logger.info("pipeline.trace trace_id=%s agent=Bug skill=BuildBugsPrompts end", trace_id)
            logger.info("pipeline.trace trace_id=%s agent=Bug skill=LLMGenerate start", trace_id)
            raw = await self._llm_generate.run(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                trace_id=trace_id,
            )
            logger.info("pipeline.trace trace_id=%s agent=Bug skill=LLMGenerate end", trace_id)
            logger.info("pipeline.trace trace_id=%s agent=Bug skill=ParseReviewJSON start", trace_id)
            review = await self._parse_review.run(raw=raw, trace_id=trace_id)
            logger.info("pipeline.trace trace_id=%s agent=Bug skill=ParseReviewJSON end", trace_id)
            return review
        except Exception:
            logger.error("pipeline.error trace_id=%s agent=Bug stage=review_parse_failed", trace_id)
            return Review(
                score=1,
                feedback="Failed to parse bug agent output as JSON; please retry.",
                suggestions=[],
            )

