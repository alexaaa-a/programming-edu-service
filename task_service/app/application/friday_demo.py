import re

from task_service.app.application.career import FridayDemo

SARA_LINE = (
    "Пятница. Две-четыре фразы: что сделали и зачем это продукту. Без слайдов."
)

_SENTENCE_SPLIT = re.compile(r"[.!?…]+")


def build_friday_demo(
        criterion: str | None,
        trajectory_blocked: bool = False,
) -> FridayDemo:
    if criterion:
        question = (
            f"Один вопрос. Что с критерием «{criterion}» — закрыли или унесли дальше?"
        )
    else:
        question = "Один вопрос. Что в этом спринте ты бы переделал в первую очередь?"
    return FridayDemo(
        sara_line=SARA_LINE,
        question=question,
        criterion=criterion,
        trajectory_blocked=trajectory_blocked,
    )


def score_friday_demo(
        pitch: str,
        answer: str,
        addresses: bool | None = None,
) -> tuple[bool | None, str | None]:
    pitch_text = pitch.strip()
    answer_text = answer.strip()
    if not pitch_text or not answer_text:
        return None, "empty"
    sentences = sum(
        1
        for part in _SENTENCE_SPLIT.split(pitch_text)
        if len(part.split()) >= 2
    )
    held = 2 <= sentences <= 4 and len(answer_text.split()) >= 4
    if held and addresses is False:
        held = False
    return held, None
