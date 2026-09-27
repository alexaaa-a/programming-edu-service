from typing import Any, Literal

from agent_service.app.application.base_agent import BaseAgent
from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces import LLMInterface, MemoryInterface
from agent_service.app.application.skills import (
    BuildChatPromptsSkill,
    BuildRetrievalQuerySkill,
    LLMGenerateSkill,
    RAGRetrieveSkill,
)
from agent_service.app.application.team import TeamMember, JOHN


class ChatAgent(BaseAgent):
    def __init__(
            self,
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

    async def speak(
            self,
            member: TeamMember,
            message: str,
            context: Any,
            chat_history: list[Any],
            briefing: str | None = None,
            voice: Literal["user", "internal"] = "user",
    ) -> str:
        query = await self._build_query.run(message=message, context=context)
        k_docs = 3
        allowed_types = set(member.rag_types) | {"chat_episode"}
        knowledge_docs = await self._retrieve_docs.run(
            query=query,
            k=k_docs,
            types=allowed_types,
        )
        semantic_only = set(member.rag_types) - {"chat_episode", "past_review", "student_note"}
        if not knowledge_docs and semantic_only:
            knowledge_docs = await self._retrieve_docs.run(
                query=query,
                k=k_docs,
                types=semantic_only,
            )

        knowledge_docs = self._scope_docs(knowledge_docs, context=context)
        if semantic_only and len(knowledge_docs) < k_docs:
            need = k_docs - len(knowledge_docs)
            refill = await self._retrieve_docs.run(
                query=query,
                k=max(need, k_docs),
                types=semantic_only,
            )
            seen = {id(d) for d in knowledge_docs}
            texts = {d.text for d in knowledge_docs}
            for doc in self._scope_docs(refill, context=context):
                if id(doc) in seen or doc.text in texts:
                    continue
                knowledge_docs.append(doc)
                texts.add(doc.text)
                if len(knowledge_docs) >= k_docs:
                    break

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
            member=member,
            briefing=briefing,
            voice=voice,
        )
        return await self._llm_generate.run(system_prompt=system_prompt, user_prompt=user_prompt)

    async def run(
            self,
            message: str,
            context: Any,
            chat_history: list[Any],
    ) -> str:
        return await self.speak(
            member=JOHN,
            message=message,
            context=context,
            chat_history=chat_history,
        )

    def _limit_docs_for_prompt(
            self,
            docs: list[RetrievedDocument],
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

    def _scope_docs(
            self,
            docs: list[RetrievedDocument],
            context: Any,
    ) -> list[RetrievedDocument]:
        user_id = ""
        session_id = ""
        if isinstance(context, dict):
            user_id = str(context.get("user_id") or "").strip()
            session_id = str(context.get("session_id") or "").strip()
        scoped: list[RetrievedDocument] = []
        for doc in docs:
            meta = doc.metadata or {}
            doc_type = str(meta.get("type") or "")
            if doc_type in {"past_review", "student_note"}:
                if not user_id or str(meta.get("user_id") or "") != user_id:
                    continue
            elif doc_type == "chat_episode":
                meta_user = str(meta.get("user_id") or "").strip()
                meta_session = str(meta.get("session_id") or "").strip()
                if user_id:
                    if not meta_user or meta_user != user_id:
                        continue
                elif meta_user:
                    continue
                if session_id and meta_session and meta_session != session_id:
                    continue
                if session_id and not meta_session:
                    continue
            scoped.append(doc)
        return scoped
