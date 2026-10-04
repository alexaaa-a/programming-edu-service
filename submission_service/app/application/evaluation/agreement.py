from dataclasses import dataclass
from typing import Iterable, Sequence


PASS_SCORE = 8


@dataclass(frozen=True, slots=True)
class Observation:
    score: float
    tests_total: int
    tests_passed: int
    tests_status: str = "failed"

    @property
    def usable(self) -> bool:
        return self.tests_status in {"passed", "failed"} and self.tests_total > 0

    @property
    def tests_green(self) -> bool:
        return self.tests_status == "passed" and self.tests_passed >= self.tests_total

    @property
    def review_pass(self) -> bool:
        return normalize_score(self.score) >= PASS_SCORE

    @property
    def pass_ratio(self) -> float:
        if self.tests_total <= 0:
            return 0.0
        return self.tests_passed / self.tests_total


def normalize_score(raw: float) -> float:
    value = float(raw)
    if value > 10:
        value = value / 10.0
    return max(0.0, min(10.0, value))


@dataclass(frozen=True, slots=True)
class AgreementReport:
    total: int = 0
    used: int = 0
    both_pass: int = 0
    both_fail: int = 0
    false_pass: int = 0
    false_fail: int = 0
    score_gap: float = 0.0

    @property
    def agreement(self) -> float:
        if self.used <= 0:
            return 0.0
        return (self.both_pass + self.both_fail) / self.used

    @property
    def false_pass_rate(self) -> float:
        passes = self.both_pass + self.false_pass
        if passes <= 0:
            return 0.0
        return self.false_pass / passes

    @property
    def false_fail_rate(self) -> float:
        fails = self.both_fail + self.false_fail
        if fails <= 0:
            return 0.0
        return self.false_fail / fails

    @property
    def kappa(self) -> float:
        n = self.used
        if n <= 0:
            return 0.0
        observed = self.agreement
        review_pass = (self.both_pass + self.false_pass) / n
        tests_pass = (self.both_pass + self.false_fail) / n
        expected = review_pass * tests_pass + (1 - review_pass) * (1 - tests_pass)
        if expected >= 1.0:
            return 1.0 if observed >= 1.0 else 0.0
        return (observed - expected) / (1 - expected)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "total": self.total,
            "used": self.used,
            "agreement": round(self.agreement, 4),
            "kappa": round(self.kappa, 4),
            "false_pass": self.false_pass,
            "false_fail": self.false_fail,
            "false_pass_rate": round(self.false_pass_rate, 4),
            "false_fail_rate": round(self.false_fail_rate, 4),
            "both_pass": self.both_pass,
            "both_fail": self.both_fail,
            "score_gap": round(self.score_gap, 3),
        }

    def as_text(self) -> str:
        if self.used == 0:
            return (
                f"Сдач: {self.total}. С прогоном тестов: 0. "
                "Пока не на чем считать согласие."
            )
        lines = [
            f"Сдач: {self.total}, из них с тестами: {self.used}",
            f"Согласие: {self.agreement:.1%}, каппа Коэна: {self.kappa:.3f}",
            f"Ложный зачёт: {self.false_pass} ({self.false_pass_rate:.1%} зачётов ревью)",
            f"Ложный отказ: {self.false_fail} ({self.false_fail_rate:.1%} отказов ревью)",
            f"Средний разрыв балла и доли тестов: {self.score_gap:+.2f} из 10",
        ]
        return "\n".join(lines)


def evaluate(observations: Iterable[Observation]) -> AgreementReport:
    items: Sequence[Observation] = list(observations)
    usable = [item for item in items if item.usable]
    if not usable:
        return AgreementReport(total=len(items))

    both_pass = both_fail = false_pass = false_fail = 0
    gap = 0.0
    for item in usable:
        if item.review_pass and item.tests_green:
            both_pass += 1
        elif not item.review_pass and not item.tests_green:
            both_fail += 1
        elif item.review_pass:
            false_pass += 1
        else:
            false_fail += 1
        gap += normalize_score(item.score) - (1 + 9 * item.pass_ratio)

    return AgreementReport(
        total=len(items),
        used=len(usable),
        both_pass=both_pass,
        both_fail=both_fail,
        false_pass=false_pass,
        false_fail=false_fail,
        score_gap=gap / len(usable),
    )


def observations_from_submissions(submissions: Iterable[object]) -> list[Observation]:
    out: list[Observation] = []
    for item in submissions:
        review = getattr(item, "review", None)
        if review is None:
            continue
        tests = getattr(review, "tests", None)
        if tests is None:
            continue
        out.append(
            Observation(
                score=float(getattr(review, "score", 0) or 0),
                tests_total=int(getattr(tests, "total", 0) or 0),
                tests_passed=int(getattr(tests, "passed", 0) or 0),
                tests_status=str(getattr(tests, "status", "") or ""),
            )
        )
    return out
