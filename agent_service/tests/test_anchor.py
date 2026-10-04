from agent_service.app.application.review.anchor import anchor, anchor_line
from agent_service.app.application.review.acceptance import _parse_checks_json
from agent_service.app.application.review.acceptance import AcceptanceCriterion, AcceptanceRubric


CODE = """def paginate(orders, page, page_size):
    if page < 1:
        raise ValueError("page")
    total = len(orders)
    pages = total // page_size
    start = (page - 1) * page_size
    return {"items": orders[start:start + page_size], "pages": pages}


class OrderView:
    def render(self, order):
        return str(order)
"""


def test_the_model_line_wins_when_it_fits_the_code():
    found = anchor("что-то не так", CODE, hint=5)
    assert found is not None and (found.line, found.source) == (5, "model")


def test_a_line_outside_the_code_is_ignored():
    # 99-й строки нет: привязка ищется по тексту, а не ставится наугад
    assert anchor_line("деление в pages", CODE, hint=99) == 5


def test_the_text_may_name_the_line_itself():
    found = anchor("Ошибка в строке 4", CODE)
    assert found is not None and (found.line, found.source) == (4, "text")
    assert anchor_line("ruff: solution.py:2: unused", CODE) == 2


def test_a_quoted_snippet_is_looked_up_in_the_code():
    found = anchor("деление `total // page_size` падает при нуле", CODE)
    assert found is not None and (found.line, found.source) == (5, "snippet")


def test_a_symbol_points_at_its_declaration_not_its_use():
    found = anchor("метод render ничего не проверяет", CODE)
    assert found is not None and (found.line, found.source) == (11, "symbol")
    assert anchor_line("класс OrderView лишний", CODE) == 10


def test_a_symbol_without_a_declaration_points_at_the_first_use():
    assert anchor_line("переменная pages считается неверно", CODE) == 5


def test_prose_in_quotes_is_not_taken_for_a_code_snippet():
    # цитата из брифа целиком в коде не ищется: иначе подсветка уедет куда попало
    found = anchor('критерий «пустой список даёт items=[] и pages=0»', CODE)
    assert found is not None and found.source == "symbol"
    assert found.line == 7  # строка, где собираются items и pages

    # а кавычки с русским текстом и без знакомых имён не дают привязки вовсе
    assert anchor_line('критерий «список выводится страницами»', CODE) is None


def test_a_remark_with_nothing_to_hold_on_to_stays_unanchored():
    assert anchor_line("Код в целом сыроват, стоит подумать над структурой", CODE) is None
    assert anchor_line("return None", "") is None


def test_common_words_are_not_addresses():
    # import, return, class есть почти в любом коде: по ним привязываться нельзя
    assert anchor_line("return вместо исключения", "x = 1\nreturn x\n") is None


def test_the_grader_reads_a_line_from_the_model():
    rubric = AcceptanceRubric(criteria=[AcceptanceCriterion(id="c1", text="Проверяет аргументы")])
    checks = _parse_checks_json(
        '{"checks":[{"id":"c1","passed":false,"note":"нет проверки page_size","line":"3"}]}',
        rubric,
    )
    assert checks[0].line == 3


def test_a_garbage_line_from_the_model_becomes_none():
    rubric = AcceptanceRubric(criteria=[AcceptanceCriterion(id="c1", text="Проверяет аргументы")])
    for raw in ('"line": "nope"', '"line": 0', '"line": null', '"line": true'):
        checks = _parse_checks_json(
            '{"checks":[{"id":"c1","passed":false,"note":"нет проверки",' + raw + "}]}",
            rubric,
        )
        assert checks[0].line is None, raw
