from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class ChatMetrics:
    answer_non_empty: bool
    must_contain_any_found: int
    must_contain_any_total: int
    must_contain_any_recall: float


def count_keywords_found(
        answer: str,
        expected_keywords: Iterable[str],
        case_sensitive: bool = False,
) -> tuple[int, int]:
    keywords = [k for k in expected_keywords if isinstance(k, str) and k.strip()]
    total = len(keywords)
    if total == 0:
        return 0, 0

    answer_cmp = answer if case_sensitive else answer.lower()
    found = 0
    for kw in keywords:
        kw_cmp = kw if case_sensitive else kw.lower()
        if kw_cmp in answer_cmp:
            found += 1
    return found, total


def keyword_match_score(
        answer: str,
        expected_keywords: Iterable[str],
        case_sensitive: bool = False,
) -> float:
    found, total = count_keywords_found(answer, expected_keywords, case_sensitive=case_sensitive)
    return (found / total) if total else 0.0


def mention_groups_score(text: str, groups: Sequence[Sequence[str]]) -> tuple[float, int, int]:
    cleaned = [tuple(term for term in group if str(term).strip()) for group in groups]
    cleaned = [group for group in cleaned if group]
    if not cleaned:
        return 1.0, 0, 0
    haystack = (text or "").lower()
    hits = 0
    for group in cleaned:
        if any(str(term).lower() in haystack for term in group):
            hits += 1
    return hits / len(cleaned), hits, len(cleaned)


def score_within_range(
        score: int | float,
        expected_score_range: Sequence[int],
        inclusive: bool = True,
) -> bool:
    if not expected_score_range or len(expected_score_range) != 2:
        return False
    lo = float(expected_score_range[0])
    hi = float(expected_score_range[1])
    if lo > hi:
        lo, hi = hi, lo

    value = float(score)
    if inclusive:
        return lo <= value <= hi
    return lo < value < hi


def response_length(answer: str, unit: str = "chars") -> int:
    if unit == "chars":
        return len(answer)
    if unit == "words":
        stripped = answer.strip()
        if not stripped:
            return 0
        return len(stripped.split())
    raise ValueError(f"Unknown unit: {unit!r}. Use 'chars' or 'words'.")


def compute_chat_metrics(answer: str, must_contain_any: Iterable[str]) -> ChatMetrics:
    found, total = count_keywords_found(answer, must_contain_any, case_sensitive=False)
    if total == 0:
        return ChatMetrics(
            answer_non_empty=bool(answer and answer.strip()),
            must_contain_any_found=0,
            must_contain_any_total=0,
            must_contain_any_recall=0.0,
        )

    recall = found / total if total else 0.0
    return ChatMetrics(
        answer_non_empty=bool(answer and answer.strip()),
        must_contain_any_found=found,
        must_contain_any_total=total,
        must_contain_any_recall=recall,
    )
