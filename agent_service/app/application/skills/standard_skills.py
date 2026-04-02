from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any


_MENTOR_ANALYSIS_JSON_MAX_CHARS = 14_000


def _to_jsonable_for_mentor(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable_for_mentor(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable_for_mentor(v) for v in value]
    return value

from agent_service.app.application.dto import Review
from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces import LLMInterface
from agent_service.app.application.interfaces import MemoryInterface


def _filter_docs_by_types(
    docs: list[RetrievedDocument],
    *,
    allowed_types: set[str],
) -> list[RetrievedDocument]:
    filtered: list[RetrievedDocument] = []
    for d in docs:
        meta = d.metadata or {}
        if str(meta.get("type", "")) in allowed_types:
            filtered.append(d)
    return filtered


def _truncate_chars(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    return text[:max_chars].rsplit(" ", 1)[0].strip()


def _format_knowledge_docs(
    docs: list[RetrievedDocument],
    *,
    max_docs: int,
    max_total_chars: int,
) -> str:
    if not docs or max_docs <= 0 or max_total_chars <= 0:
        return "(no relevant knowledge found)"

    total = 0
    formatted: list[str] = []
    for i, item in enumerate(docs[:max_docs], start=1):
        text = (item.text or "").strip()
        if not text:
            continue

        meta = item.metadata or {}
        doc_type = str(meta.get("type", "") or "")
        source = str(meta.get("source", "") or "")
        header = ""
        if doc_type or source:
            header = f" (type={doc_type}, source={source})"

        remaining = max_total_chars - total
        if remaining <= 0:
            break

        text = _truncate_chars(text, max_chars=min(len(text), remaining))
        if not text:
            continue

        formatted.append(f"[KB Doc {i}]{header}\n{text}")
        total += len(text)

    return "\n\n".join(formatted) if formatted else "(no relevant knowledge found)"


@dataclass(frozen=True, slots=True)
class LLMGenerateSkill:
    llm: LLMInterface

    name: str = "llm_generate"
    description: str = "Calls the configured LLM and returns raw text."

    async def run(self, **kwargs: Any) -> str:
        system_prompt = str(kwargs["system_prompt"])
        user_prompt = str(kwargs["user_prompt"])
        return await self.llm.generate(system_prompt, user_prompt)


@dataclass(frozen=True, slots=True)
class ParseReviewJSONSkill:
    name: str = "parse_review_json"
    description: str = "Parses LLM raw output into a Review JSON schema."

    async def run(self, **kwargs: Any) -> Review:
        raw = str(kwargs["raw"])
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned.removeprefix("json").strip()

        try:
            data: dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            data = json.loads(cleaned[start : end + 1])

        try:
            score = int(data["score"])
            feedback = str(data["feedback"])
            suggestions = list(map(str, data.get("suggestions", [])))
        except Exception as e:
            raise ValueError(f"Invalid Review JSON payload: {e}") from e

        return Review(score=score, feedback=feedback, suggestions=suggestions)


@dataclass(frozen=True, slots=True)
class BuildReviewerPromptsSkill:
    name: str = "build_reviewer_prompts"
    description: str = "Builds system/user prompts for the code reviewer agent."

    async def run(self, **kwargs: Any) -> tuple[str, str]:
        code = str(kwargs["code"])
        task_description = str(kwargs["task_description"])

        system_prompt = (
            "You are a senior code reviewer.\n"
            "Analyze the provided code with respect to the task description.\n"
            "Return ONLY a single valid JSON object with EXACT schema:\n"
            "{\n"
            '  "score": <int 1..10>,\n'
            '  "feedback": <string>,\n'
            '  "suggestions": <array of string>\n'
            "}\n"
            "Hard constraints:\n"
            "- Output must be JSON only (no markdown, no code fences, no extra text).\n"
            "- score is an integer from 1 to 10.\n"
            '- feedback must be <= 600 characters.\n'
            "- suggestions must be an array of 0..8 actionable items (each <= 200 characters).\n"
            "- If the answer cannot be produced reliably, set score=1, feedback to a short error message, and suggestions=[]\n"
        )
        user_prompt = (
            f"Task description:\n{task_description}\n\n"
            f"Code:\n{code}\n"
        )
        return system_prompt, user_prompt


@dataclass(frozen=True, slots=True)
class AnalyzeCodeQualitySkill:
    memory: MemoryInterface

    name: str = "analyze_code_quality"
    description: str = "Builds reviewer prompts using RAG best-practice docs."

    retrieval_k: int = 10
    prompt_max_docs: int = 3
    prompt_max_total_chars: int = 5500

    allowed_types: tuple[str, ...] = ("best_practice",)

    async def run(self, **kwargs: Any) -> tuple[str, str]:
        code = str(kwargs["code"])
        task_description = str(kwargs["task_description"])

        knowledge_docs = await self.memory.retrieve(
            query=task_description,
            k=self.retrieval_k,
            types=set(self.allowed_types),
        )

        docs_text = _format_knowledge_docs(
            knowledge_docs,
            max_docs=self.prompt_max_docs,
            max_total_chars=self.prompt_max_total_chars,
        )

        system_prompt = (
            "Ты — senior code reviewer. Оцени код относительно задачи.\n"
            "Используй знания из базы знаний (KB) как опору: не выдумывай.\n"
            "Язык ответа в поле feedback: русский.\n"
            "Верни ТОЛЬКО один валидный JSON объект со СТРОГОЙ схемой:\n"
            "{\n"
            '  "score": <int 1..10>,\n'
            '  "feedback": <string>,\n'
            '  "suggestions": <array of string>\n'
            "}\n"
            "Правила для score (более объективно):\n"
            "- 10: требования выполнены полностью, есть только мелкие косметические замечания.\n"
            "- 8: есть небольшие проблемы, но основная логика/работа выполнены.\n"
            "- 6: заметные недочёты или неполная реализация ключевой части.\n"
            "- 4: существенные ошибки/несоответствия задаче.\n"
            "- 1: невозможно надёжно оценить или решение явно неверное/не компилируется.\n"
            "Жёсткие ограничения:\n"
            "- Ответ целиком должен быть JSON (без markdown/code fences/доп. текста снаружи JSON).\n"
            "- Поле feedback допускает Markdown для **жирного** (используй **...**), но избегай строк, начинающихся на '*' или '-' как маркеры.\n"
            "- feedback <= 380 символов.\n"
            "- suggestions: 0..6 пунктов, каждый <= 140 символов, без маркировки '*'-'-' в начале строки.\n"
            "- Если не можешь сформировать ответ надёжно, верни score=1, feedback с краткой причиной и suggestions=[]\n"
        )

        user_prompt = (
            f"Task description:\n{task_description}\n\n"
            f"Knowledge base (best practices):\n{docs_text}\n\n"
            f"Code:\n{code}\n"
        )
        return system_prompt, user_prompt


@dataclass(frozen=True, slots=True)
class BuildBugPromptsSkill:
    name: str = "build_bug_prompts"
    description: str = "Builds system/user prompts for the bug-finding agent."

    async def run(self, **kwargs: Any) -> tuple[str, str]:
        code = str(kwargs["code"])

        system_prompt = (
            "You are a QA Engineer focused on finding bugs and edge cases.\n"
            "Analyze the provided code.\n"
            "Return ONLY a single valid JSON object with EXACT schema:\n"
            "{\n"
            '  "score": <int 1..10>,\n'
            '  "feedback": <string>,\n'
            '  "suggestions": <array of string>\n'
            "}\n"
            "Hard constraints:\n"
            "- Output must be JSON only (no markdown, no code fences, no extra text).\n"
            "- score is an integer from 1 to 10 (10 means very safe).\n"
            "- feedback must be <= 600 characters.\n"
            "- suggestions must be an array of 0..8 actionable items (each <= 200 characters).\n"
            "- If you cannot be confident, set score=1, feedback to a short error message, suggestions=[]\n"
        )
        user_prompt = f"Code:\n{code}\n"
        return system_prompt, user_prompt


@dataclass(frozen=True, slots=True)
class DetectBugsSkill:
    memory: MemoryInterface

    name: str = "detect_bugs"
    description: str = "Builds bug-finding prompts using RAG bugs docs."

    retrieval_k: int = 12
    prompt_max_docs: int = 4
    prompt_max_total_chars: int = 6000

    allowed_types: tuple[str, ...] = ("bugs",)

    async def run(self, **kwargs: Any) -> tuple[str, str]:
        code = str(kwargs["code"])

        retrieval_query = f"bugs\n{code[:4000]}"
        knowledge_docs = await self.memory.retrieve(
            query=retrieval_query,
            k=self.retrieval_k,
            types=set(self.allowed_types),
        )

        docs_text = _format_knowledge_docs(
            knowledge_docs,
            max_docs=self.prompt_max_docs,
            max_total_chars=self.prompt_max_total_chars,
        )

        system_prompt = (
            "Ты — QA Engineer. Ищешь баги и edge cases.\n"
            "Используй знания из базы знаний (KB) как опору: не выдумывай.\n"
            "Язык ответа в поле feedback: русский.\n"
            "Верни ONLY один valid JSON объект со СТРОГОЙ схемой:\n"
            "{\n"
            '  "score": <int 1..10>,\n'
            '  "feedback": <string>,\n'
            '  "suggestions": <array of string>\n'
            "}\n"
            "Жёсткие ограничения:\n"
            "- Ответ целиком должен быть JSON (без markdown/code fences/доп. текста снаружи JSON).\n"
            "- Поле feedback допускает Markdown для **жирного** (используй **...**), но избегай строк, начинающихся на '*' или '-' как маркеры.\n"
            "- feedback <= 380 символов.\n"
            "- score — целое число от 1 до 10 (10 = очень надёжно, без критических багов).\n"
            "- suggestions: 0..6 пунктов, каждый <= 140 символов.\n"
            "- Если не можешь сформировать ответ надёжно, верни score=1, feedback с краткой причиной и suggestions=[]\n"
        )

        user_prompt = (
            f"Knowledge base (bugs & edge cases):\n{docs_text}\n\n"
            f"Code:\n{code}\n"
        )
        return system_prompt, user_prompt


@dataclass(frozen=True, slots=True)
class BuildMentorPromptsSkill:
    name: str = "build_mentor_prompts"
    description: str = "Builds prompts for the mentor agent."

    async def run(self, **kwargs: Any) -> tuple[str, str]:
        code = str(kwargs["code"])
        results = kwargs["results"]

        if isinstance(results, str):
            results_text = results
        else:
            try:
                payload = _to_jsonable_for_mentor(results)
                results_text = json.dumps(payload, ensure_ascii=False, indent=2)
            except Exception:
                results_text = str(results)

        if len(results_text) > _MENTOR_ANALYSIS_JSON_MAX_CHARS:
            head = _MENTOR_ANALYSIS_JSON_MAX_CHARS // 2
            tail = _MENTOR_ANALYSIS_JSON_MAX_CHARS - head
            omitted = len(results_text) - head - tail
            results_text = (
                results_text[:head]
                + f"\n\n... [обрезано ~{omitted} символов: слишком большой ответ reviewer/bug для одного запроса] ...\n\n"
                + results_text[-tail:]
            )

        system_prompt = (
            "Ты — senior software mentor.\n"
            "Получил код и результаты анализа.\n"
            "Сформируй единый итоговый фидбек на русском языке.\n"
            "Требования к формату для UI:\n"
            "- Разрешён Markdown: используй **жирный** для ключевых тезисов.\n"
            "- НЕ используй маркеры списка в виде строк, начинающихся на '*' или '-'.\n"
            "- Держи текст коротким: 3-5 предложений, <= 650 символов.\n"
            "- Не упоминай внутренние роли агентов.\n"
            "- Будь actionable: что менять, почему важно, как проверить.\n"
        )
        user_prompt = (
            f"Code:\n{code}\n\n"
            f"Other agents results:\n{results_text}\n"
        )
        return system_prompt, user_prompt


@dataclass(frozen=True, slots=True)
class RAGRetrieveSkill:
    memory: MemoryInterface

    name: str = "rag_retrieve"
    description: str = "Retrieves relevant documents from memory (RAG)."

    async def run(self, **kwargs: Any) -> list[RetrievedDocument]:
        query = str(kwargs["query"])
        k = int(kwargs.get("k", 5))
        types = kwargs.get("types")
        if types is not None and not isinstance(types, set):
            types = set(map(str, types))
        return await self.memory.retrieve(query=query, k=k, types=types)


@dataclass(frozen=True, slots=True)
class BuildRetrievalQuerySkill:
    name: str = "build_retrieval_query"
    description: str = "Builds a search query for RAG based on message+context."

    async def run(self, **kwargs: Any) -> str:
        message = str(kwargs["message"])
        context = kwargs["context"]

        task_ctx = self._task_context_text(context).strip()
        if task_ctx:
            return f"{message}\n\nКонтекст задачи:\n{task_ctx}"
        return message

    def _task_context_text(self, context: Any) -> str:
        if not isinstance(context, dict):
            return ""
        parts: list[str] = []
        if context.get("task_title"):
            parts.append(str(context["task_title"]))
        if context.get("task_description"):
            parts.append(str(context["task_description"]))
        return "\n".join(parts)

    def _to_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)


@dataclass(frozen=True, slots=True)
class BuildChatPromptsSkill:
    name: str = "build_chat_prompts"
    description: str = "Builds prompts for the chat team agent."

    def _format_task_context_for_prompt(self, context: Any) -> str:
        if not isinstance(context, dict):
            return "(нет контекста задачи)"
        title = context.get("task_title")
        desc = context.get("task_description")
        if title or desc:
            parts: list[str] = []
            if title:
                parts.append(f"Название задачи (пользователь открыл чат из этой задачи):\n{title}")
            if desc:
                parts.append(f"Описание задачи:\n{desc}")
            return "\n\n".join(parts)
        return (
            "Режим: общий командный чат без привязки к конкретной задаче.\n"
            "У тебя нет названия текущей задачи из этого режима — поля задачи намеренно не переданы.\n"
            "Не выдумывай название задачи и не называй текущей задачей подписи интерфейса "
            "(например «Рабочее пространство спринта», «Общий чат» и т.п.).\n"
            "Если в истории чата раньше встречалось такое как «имя задачи» — считай это ошибкой и не опирайся на это."
        )

    async def run(self, **kwargs: Any) -> tuple[str, str]:
        message = str(kwargs["message"])
        chat_history = kwargs["chat_history"]
        context = kwargs["context"]
        knowledge_docs = kwargs["knowledge_docs"]

        history_text = self._to_text(chat_history)
        context_text = self._format_task_context_for_prompt(context)
        docs_text = self._format_docs(knowledge_docs)

        system_prompt = (
            "Ты — единый экспертный собеседник.\n"
            "Формируй один финальный ответ на русском языке.\n"
            "Внутренние промежуточные размышления и стенограмму НЕ показывай.\n\n"
            "Требования к ответу:\n"
            "1) Дай ОДИН ответ без заголовков ролей и без упоминания того, что это командное обсуждение.\n"
            "2) Пиши по делу и профессионально; без воды.\n"
            "3) Используй message и chat_history.\n"
            "4) Используй knowledge context (KB) только если он помогает и не противоречит.\n"
            "5) Если данных недостаточно — укажи краткие допущения и задай 1–3 уточняющих вопроса.\n"
            "6) Объём: ориентируйся на ~200–450 слов.\n"
            "7) Если в блоке контекста указано, что это общий чат без задачи, не ссылайся на «текущую задачу» "
            "и не приписывай пользователю конкретное название задачи; отвечай в общих терминах или спроси, о какой задаче речь.\n"
        )

        user_prompt = (
            f"Контекст для модели (только задача или явный режим общего чата):\n{context_text}\n\n"
            f"RAG knowledge documents (excerpts):\n{docs_text}\n\n"
            f"Chat history:\n{history_text}\n\n"
            f"New message:\n{message}\n"
        )
        return system_prompt, user_prompt

    def _to_text(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    def _format_docs(self, docs: list[RetrievedDocument]) -> str:
        if not docs:
            return "(no relevant documents found)"
        formatted: list[str] = []
        for i, item in enumerate(docs, start=1):
            meta = item.metadata or {}
            doc_type = meta.get("type", "")
            source = meta.get("source", "")
            meta_suffix = ""
            if doc_type or source:
                meta_suffix = f" (type={doc_type}, source={source})"
            formatted.append(f"[Doc {i}]{meta_suffix}\n{item.text}")
        return "\n\n".join(formatted)


__all__ = [
    "LLMGenerateSkill",
    "ParseReviewJSONSkill",
    "BuildReviewerPromptsSkill",
    "BuildBugPromptsSkill",
    "AnalyzeCodeQualitySkill",
    "DetectBugsSkill",
    "BuildMentorPromptsSkill",
    "RAGRetrieveSkill",
    "BuildRetrievalQuerySkill",
    "BuildChatPromptsSkill",
]
