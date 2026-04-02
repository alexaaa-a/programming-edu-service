from typing import Any

from agent_service.app.application.base_agent import BaseAgent
from agent_service.app.application.interfaces import LLMInterface
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.skills import (
    BuildChatPromptsSkill,
    BuildRetrievalQuerySkill,
    LLMGenerateSkill,
    RAGRetrieveSkill,
)


class ChatAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm: LLMInterface,
        memory: MemoryInterface,
    ) -> None:
        super().__init__(llm=llm, memory=memory)
        self.skills = [
            BuildRetrievalQuerySkill(),
            RAGRetrieveSkill(memory=memory),
            BuildChatPromptsSkill(),
            LLMGenerateSkill(llm=llm),
        ]
        self._build_query = self.skills[0]
        self._retrieve_docs = self.skills[1]
        self._build_prompts = self.skills[2]
        self._llm_generate = self.skills[3]

    async def run(
        self,
        message: str,
        context: Any,
        chat_history: list[Any],
    ) -> str:
        session_id = None
        if isinstance(context, dict):
            session_id = context.get("session_id")

        if session_id is not None:
            chat_history = await self._memory.get_chat_history(str(session_id))  # type: ignore[union-attr]

        query = await self._build_query.run(message=message, context=context)
        k_docs = 3
        knowledge_docs = await self._retrieve_docs.run(query=query, k=k_docs)

        knowledge_docs = self._limit_docs_for_prompt(
            knowledge_docs,
            max_docs=k_docs,
            max_total_chars=6000,
            max_chars_per_doc=2200,
        )

        system_prompt, user_prompt = await self._build_prompts.run(
            message=message,
            chat_history=chat_history,
            context=context,
            knowledge_docs=knowledge_docs,
        )

        answer = await self._llm_generate.run(system_prompt=system_prompt, user_prompt=user_prompt)

        if session_id is not None:
            await self._memory.append_chat_message(  # type: ignore[union-attr]
                session_id=str(session_id),
                role="user",
                content=message,
            )
            await self._memory.append_chat_message(  # type: ignore[union-attr]
                session_id=str(session_id),
                role="assistant",
                content=answer,
            )

        return answer

    def _limit_docs_for_prompt(
        self,
        docs: list[RetrievedDocument],
        *,
        max_docs: int,
        max_total_chars: int,
        max_chars_per_doc: int,
    ) -> list[RetrievedDocument]:
        if not docs or max_docs <= 0:
            return []

        trimmed: list[RetrievedDocument] = []
        total = 0
        for doc in docs[:max_docs]:
            text = doc.text.strip()
            if not text:
                continue
            if len(text) > max_chars_per_doc:
                text = text[:max_chars_per_doc].rsplit(" ", 1)[0].strip()
            doc_chars = len(text)
            if total + doc_chars > max_total_chars:
                break

            trimmed.append(
                RetrievedDocument(
                    text=text,
                    metadata=doc.metadata or {},
                    score=doc.score,
                ),
            )
            total += doc_chars

        return trimmed
