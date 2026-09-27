from task_service.app.application.interfaces.career_llm import PeerGrade, PeerSnippet

PEER_REVIEW_TITLE = "Ревью стажёра"
PEER_REVIEW_GRADES = frozenset({"junior_plus", "strong", "offer"})
PEER_REVIEW_INTRO = "Стажёр прислал кусок. Одна настоящая дыра. Напиши, что не так — патч не нужен."
FALLBACK_CODE = """def top_scores(scores: list[int], limit: int) -> list[int]:
    ordered = sorted(scores)
    return ordered[:limit]"""
FALLBACK_BUG = "sorted без reverse отдаёт меньшие значения, а не наибольшие."
PEER_REVIEW_DESCRIPTION = f"{PEER_REVIEW_INTRO}\n\n{FALLBACK_CODE}\n"

FOUND_LINE = "Эмма: да, дыра в сортировке. Стажёр отдал меньшие, не большие."
MISSED_LINE = "Эмма: это не та дыра. Сортировка идёт по возрастанию — в топ попали меньшие."


def is_peer_review_task(title: str) -> bool:
    return title.strip() == PEER_REVIEW_TITLE


def peer_review_task_for(grade: str | None) -> tuple[str, str] | None:
    if grade not in PEER_REVIEW_GRADES:
        return None
    return PEER_REVIEW_TITLE, PEER_REVIEW_DESCRIPTION


def found_the_bug(note: str) -> bool:
    text = note.lower().replace("ё", "е")
    names_top = any(
        token in text
        for token in ("по убыван", "убыванию", "наибольш", "самые больш", "большие", "больших")
    )
    if "reverse" in text and any(
        token in text
        for token in ("топ", "сортир", "sorted", "наибольш", "убыван", "больших", "большие", "score")
    ):
        names_top = True
    if "максимальн" in text and any(
        token in text for token in ("значен", "score", "балл", "топ", "числ", "результат")
    ):
        names_top = True
    if "возрастани" in text and any(
        token in text
        for token in ("наибольш", "большие", "больших", "убыван", "reverse", "вместо", "а не", "не те")
    ):
        return True
    smaller_vs_larger = (
        "меньш" in text
        and any(token in text for token in ("большие", "больших", "наибольш"))
        and any(token in text for token in ("вместо", "а не", "ошиб", "баг", "не так", "не те"))
    )
    if smaller_vs_larger:
        return True
    if not names_top:
        return False
    return any(
        token in text
        for token in (
            "ошиб",
            "баг",
            "не так",
            "вместо",
            "а не",
            "дыр",
            "не те",
            "не топ",
            "должен",
            "надо",
            "нужн",
            "sorted",
            "сортир",
            "топ",
            "score",
        )
    )


def emma_line(found: bool) -> str:
    return FOUND_LINE if found else MISSED_LINE


def _snippet_ok(snippet: PeerSnippet) -> bool:
    code = snippet.code.strip()
    bug = " ".join(snippet.bug.split())
    if not (40 <= len(code) <= 2500) or not (12 <= len(bug) <= 400):
        return False
    if "def " not in code or bug.lower() in code.lower():
        return False
    return True


async def compose_peer_review(grade: str | None, llm) -> tuple[str, str, str] | None:
    if peer_review_task_for(grade) is None:
        return None
    snippet = None
    if llm is not None:
        try:
            snippet = await llm.generate_peer_snippet()
        except Exception:
            snippet = None
    if snippet is None or not _snippet_ok(snippet):
        return PEER_REVIEW_TITLE, PEER_REVIEW_DESCRIPTION, FALLBACK_BUG
    description = f"{PEER_REVIEW_INTRO}\n\n{snippet.code.strip()}\n"
    return PEER_REVIEW_TITLE, description, " ".join(snippet.bug.split())


async def judge_peer_note(
        note: str,
        description: str,
        review_bug: str | None,
        llm,
) -> tuple[bool, str] | None:
    bug = " ".join((review_bug or "").split())
    if bug and bug != FALLBACK_BUG:
        graded = None
        if llm is not None:
            try:
                graded = await llm.grade_peer_note(description, bug, note)
            except Exception:
                graded = None
        if not isinstance(graded, PeerGrade) or not graded.emma.strip():
            return None
        return graded.found, graded.emma.strip()
    found = found_the_bug(note)
    return found, emma_line(found)
