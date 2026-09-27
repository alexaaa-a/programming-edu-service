import logging

from agent_service.app.application.base_agent import BaseAgent
from agent_service.app.application.dto import Review
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.skills import (
    AnalyzeCodeQualitySkill,
    LLMGenerateSkill,
    ParseReviewJSONSkill,
)
from agent_service.app.application.observability.tracing import ensure_trace_id


class ReviewerAgent(BaseAgent):
    def __init__(
            self,
            llm: LLMInterface,
            memory: MemoryInterface,
    ) -> None:
        super().__init__(llm=llm, memory=memory)
        self.skills = [
            AnalyzeCodeQualitySkill(memory=memory),
            LLMGenerateSkill(llm=llm),
            ParseReviewJSONSkill(),
        ]
        self._build_prompts = self.skills[0]
        self._llm_generate = self.skills[1]
        self._parse_review = self.skills[2]

    async def run(self, code: str, task_description: str, tool_facts: str = "") -> Review:
        trace_id = ensure_trace_id()
        logger = logging.getLogger("agent_service")
        logger.info("pipeline.trace trace_id=%s agent=Reviewer skill=BuildPrompts start", trace_id)
        system_prompt, user_prompt = await self._build_prompts.run(
            code=code,
            task_description=task_description,
            tool_facts=tool_facts,
            trace_id=trace_id,
        )
        logger.info("pipeline.trace trace_id=%s agent=Reviewer skill=BuildPrompts end", trace_id)
        logger.info("pipeline.trace trace_id=%s agent=Reviewer skill=LLMGenerate start", trace_id)
        try:
            raw = await self._llm_generate.run(system_prompt=system_prompt, user_prompt=user_prompt, trace_id=trace_id)
            logger.info("pipeline.trace trace_id=%s agent=Reviewer skill=LLMGenerate end", trace_id)
            logger.info("pipeline.trace trace_id=%s agent=Reviewer skill=ParseReviewJSON start", trace_id)
            review = await self._parse_review.run(raw=raw, trace_id=trace_id)
            logger.info("pipeline.trace trace_id=%s agent=Reviewer skill=ParseReviewJSON end", trace_id)
            return review
        except Exception:
            logger.error("pipeline.error trace_id=%s agent=Reviewer stage=review_parse_failed", trace_id)
            return Review(
                score=1,
                feedback="Failed to parse reviewer output as JSON; please retry.",
                suggestions=[],
            )

