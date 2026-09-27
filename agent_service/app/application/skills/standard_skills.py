import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

from agent_service.app.application.dto import Review
from agent_service.app.application.dto.rag import RetrievedDocument
from agent_service.app.application.interfaces import LLMInterface
from agent_service.app.application.interfaces import MemoryInterface
from agent_service.app.application.team import JOHN, TeamMember
from agent_service.app.application.memory.provenance import format_provenance
from agent_service.app.application.review.context_compact import compact_agent_results


_MENTOR_ANALYSIS_JSON_MAX_CHARS = 14_000


def _to_jsonable_for_mentor(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, dict):
        return {str(k): _to_jsonable_for_mentor(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable_for_mentor(v) for v in value]
    return value


def _filter_docs_by_types(
        docs: list[RetrievedDocument],
        allowed_types: set[str],
) -> list[RetrievedDocument]:
    filtered: list[RetrievedDocument] = []
    for d in docs:
        meta = d.metadata or {}
        if str(meta.get("type", "")) in allowed_types:
            filtered.append(d)
    return filtered


def _truncate_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    return text[:max_chars].rsplit(" ", 1)[0].strip()


def _tool_facts_block(kwargs: dict[str, Any]) -> str:
    facts = str(kwargs.get("tool_facts") or "").strip()
    if not facts:
        return ""
    return (
        "Факты инструментов (это измерения, не мнение; не спорь с ними "
        "и не ставь score выше указанного потолка):\n"
        f"{facts}\n\n"
    )


def _format_knowledge_docs(
        docs: list[RetrievedDocument],
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

        provenance = format_provenance(item.metadata)
        header = f" ({provenance})" if provenance else ""

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
            "Факты инструментов важнее впечатления:\n"
            "- если синтаксис или компиляция сломаны — score не выше 2;\n"
            "- если тесты в песочнице упали — score не выше 4;\n"
            "- не отрицай находки static/sandbox/tests.\n"
            "- если инструменты язык не проверяют — не понижай score из-за отсутствия lint/compile/tests.\n"
            "- если в фактах есть прошлое ревью / повторная сдача — сравни с ним и не копируй устаревшие замечания.\n"
            "- если есть критерии приёмки — оцени соответствие им в первую очередь.\n"
            "Жёсткие ограничения:\n"
            "- Ответ целиком должен быть JSON (без markdown/code fences/доп. текста снаружи JSON).\n"
            "- Поле feedback допускает Markdown для **жирного** (используй **...**), но избегай строк, начинающихся на '*' или '-' как маркеры.\n"
            "- feedback <= 380 символов.\n"
            "- suggestions: 0..6 пунктов, каждый <= 140 символов, без маркировки '*'-'-' в начале строки.\n"
            "- Если не можешь сформировать ответ надёжно, верни score=1, feedback с краткой причиной и suggestions=[]\n"
        )

        user_prompt = (
            f"{_tool_facts_block(kwargs)}"
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
            "- Не спорь с фактами инструментов: сломанный синтаксис/компиляция и упавшие тесты — это баги.\n"
            "- Если инструменты язык не проверяют — не выдумывай падения компилятора.\n"
        )

        user_prompt = (
            f"{_tool_facts_block(kwargs)}"
            f"Knowledge base (bugs & edge cases):\n{docs_text}\n\n"
            f"Code:\n{code}\n"
        )
        return system_prompt, user_prompt


@dataclass(frozen=True, slots=True)
class BuildAdversarialPromptsSkill:
    name: str = "build_adversarial_prompts"
    description: str = "Builds prompts for the adversarial reviewer that challenges the team."

    async def run(self, **kwargs: Any) -> tuple[str, str]:
        code = str(kwargs["code"])
        task_description = str(kwargs["task_description"])
        team_summary = str(kwargs.get("team_summary") or "")

        system_prompt = (
            "Ты — состязательный проверяющий. Твоя задача — НЕ соглашаться с командой по умолчанию.\n"
            "Опровергай вывод ревьюера и QA: что пропустили, где оценка завышена, какие риски скрыты.\n"
            "Опирайся на код, бриф, критерии приёмки и факты инструментов. Не выдумывай падений вне фактов.\n"
            "Язык полей feedback/challenges/missed: русский.\n"
            "Верни ТОЛЬКО один валидный JSON объект:\n"
            "{\n"
            '  "agrees": <bool>,\n'
            '  "severity": "low"|"medium"|"high",\n'
            '  "score_cap": <int 1..10 или null>,\n'
            '  "challenges": <array of string>,\n'
            '  "missed": <array of string>,\n'
            '  "feedback": <string>\n'
            "}\n"
            "Правила:\n"
            "- agrees=true только если оценка команды справедлива и серьёзных упущений нет;\n"
            "- если синтаксис/компиляция сломаны, а команда ставит >2 — agrees=false, score_cap<=2, severity=high;\n"
            "- если тесты упали, а команда ставит >4 — agrees=false, score_cap<=4, severity=high;\n"
            "- score_cap — верхняя оценка, которую ты готов допустить (или null);\n"
            "- challenges: 0..5 коротких возражений (<=140 символов), без маркеров '*'/'-';\n"
            "- missed: 0..5 упущений команды;\n"
            "- feedback <= 280 символов, без упоминания внутренних ролей агентов;\n"
            "- ответ целиком JSON, без markdown/code fences.\n"
        )
        user_prompt = (
            f"{_tool_facts_block(kwargs)}"
            f"Task description:\n{task_description}\n\n"
            f"Team review summary:\n{team_summary}\n\n"
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
                payload = compact_agent_results(_to_jsonable_for_mentor(results))
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

        variant_hint = ""
        facts = str(kwargs.get("tool_facts") or "")
        if facts.startswith("Вариант "):
            first_line, _, rest = facts.partition("\n")
            variant_hint = first_line.strip()
            kwargs = {**kwargs, "tool_facts": rest.strip()}

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
            "- Если есть факты инструментов (синтаксис, компиляция, тесты, линт) — кратко скажи о них по-русски и не спорь с ними.\n"
            "- Если в результатах есть scorecard — опирайся на этот разбор. Итоговый балл уже посчитан, не ставь другой.\n"
            "- Если это повторная сдача: явно скажи, что исправлено после прошлого ревью, а что ещё нет.\n"
            "- Если есть критерии приёмки — кратко перечисли закрытые и открытые, не спорь с их статусом.\n"
            "- Если есть независимая/состязательная проверка с возражениями — коротко учти их в фидбеке, "
            "не называй внутренние роли.\n"
            "- Не выдавай готовое решение целиком: без больших блоков кода и без полного исправленного файла. "
            "Только точечные правки и идеи.\n"
            "- Если передан путь агентов — не пересказывай его целиком, опирайся на итог.\n"
            "- Опирайся на сжатое резюме коллег и факты инструментов, не восстанавливай полную историю.\n"
        )
        if variant_hint:
            system_prompt += f"- Следуй углу варианта: {variant_hint}\n"
        user_prompt = (
            f"{_tool_facts_block(kwargs)}"
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
        user_tag = ""
        if isinstance(context, dict):
            uid = str(context.get("user_id") or "").strip()
            sid = str(context.get("session_id") or "").strip()
            bits: list[str] = []
            if uid:
                bits.append(f"user_id={uid}")
            if sid:
                bits.append(f"session_id={sid}")
            if bits:
                user_tag = "[" + " ".join(bits) + "]\n"
        if task_ctx:
            return f"{user_tag}{message}\n\nКонтекст задачи:\n{task_ctx}"
        return f"{user_tag}{message}" if user_tag else message

    def _task_context_text(self, context: Any) -> str:
        if not isinstance(context, dict):
            return ""
        parts: list[str] = []
        if context.get("task_title"):
            parts.append(str(context["task_title"]))
        if context.get("task_description"):
            parts.append(str(context["task_description"]))
        if context.get("trajectory_briefing"):
            parts.append(str(context["trajectory_briefing"]))
        failed = context.get("failed_criteria")
        if isinstance(failed, list) and failed:
            parts.append("Не закрыто: " + "; ".join(str(item) for item in failed[:4]))
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
        briefing = str(context.get("trajectory_briefing") or "").strip()
        parts: list[str] = []
        if title:
            parts.append(f"Название задачи (пользователь открыл чат из этой задачи):\n{title}")
        if desc:
            parts.append(f"Описание задачи:\n{desc}")
        emma = str(context.get("emma_briefing") or "").strip()
        if emma:
            parts.append(
                "Платная сессия Эммы. Падающий тест из последнего ревью:\n"
                f"{emma}\n"
                "Разбери, что он проверяет и куда смотреть в коде. "
                "Готовое решение, патч и полный исправленный код не пиши."
            )
        if briefing:
            parts.append(
                "Бриф траектории студента (опирайся на шаг, балл и незакрытые критерии; "
                "не читай лекцию про формулу):\n"
                f"{briefing}"
            )
        if parts:
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
        member = kwargs.get("member")
        if not isinstance(member, TeamMember):
            member = JOHN
        briefing = str(kwargs.get("briefing") or "").strip()
        voice = str(kwargs.get("voice") or "user")

        history_text = self._to_text(chat_history)
        context_text = self._format_task_context_for_prompt(context)
        docs_text = self._format_docs(knowledge_docs)

        if voice == "internal":
            system_prompt = (
                f"{member.persona}\n\n"
                f"Сейчас ты пишешь ВНУТРЕННЮЮ заметку для команды, не ответ джуну.\n"
                f"Зона: {member.focus}.\n"
                "3–6 коротких предложений. Без приветствия, без markdown-заголовков, без «как ИИ».\n"
                "Только факты и риски из своей роли. Не подменяй решение тимлида.\n"
            )
        else:
            huddle_line = ""
            if briefing:
                huddle_line = (
                    "Команда уже сверилась. Можешь коротко опереться на заметки коллег, "
                    "но пишешь от своего лица одним ответом. Не публикуй стенограмму.\n"
                )
            system_prompt = (
                f"{member.persona}\n\n"
                f"Отвечаешь в командном чате Desk как {member.name}, {member.role}. "
                f"Зона: {member.focus}.\n"
                "Язык: русский. Один ответ, без заголовка с именем, без «я языковая модель».\n"
                f"{huddle_line}"
                "По делу, без воды. KB используй только если не противоречит сообщению и задаче.\n"
                "Если данных мало — одно допущение и 1–2 уточнения.\n"
                "Общий чат без задачи: не выдумывай название задачи.\n"
                "Если есть бриф траектории — отвечай из него: следующий шаг, балл и незакрытый критерий кода. "
                "Помоги по коду: куда смотреть и какой случай проверить. Готовый патч и исправленную функцию не пиши.\n"
                "Если спрашивают, что написать или что делать, дай один конкретный вопрос к коду, а не пересказ брифа.\n"
                "Слабое закрытие не запрещает следующий спринт: задачу закрывают слабой и спринт завершают с доски. "
                "Письмо отметит слабый зачёт, оклад не режется. Не говори, что к новому спринту рано из-за слабого зачёта.\n"
                "Правила доски — спринт, премия, оклад, «к выполнению» — не критерии кода. Их не разбирай как дыру в функции.\n"
                "Не предлагай закрыть задачу, если шаг — правка или разбор замечаний.\n"
                "Объём: примерно 80–180 слов.\n"
            )

        briefing_block = f"Заметки коллег (не показывать дословно):\n{briefing}\n\n" if briefing else ""
        user_prompt = (
            f"Контекст задачи или режим общего чата:\n{context_text}\n\n"
            f"{briefing_block}"
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
        from agent_service.app.application.memory.provenance import format_provenance

        formatted: list[str] = []
        for i, item in enumerate(docs, start=1):
            provenance = format_provenance(item.metadata)
            meta_suffix = f" ({provenance})" if provenance else ""
            formatted.append(f"[Doc {i}]{meta_suffix}\n{item.text}")
        return "\n\n".join(formatted)


__all__ = [
    "LLMGenerateSkill",
    "ParseReviewJSONSkill",
    "BuildReviewerPromptsSkill",
    "BuildBugPromptsSkill",
    "AnalyzeCodeQualitySkill",
    "DetectBugsSkill",
    "BuildAdversarialPromptsSkill",
    "BuildMentorPromptsSkill",
    "RAGRetrieveSkill",
    "BuildRetrievalQuerySkill",
    "BuildChatPromptsSkill",
]
