from submission_service.app.application.drills.models import Drill


def _drill(
        id: str,
        skill_id: str,
        title: str,
        prompt: str,
        starter: str,
        tests: str,
        reference: str,
        minutes: int = 5,
) -> Drill:
    return Drill(
        id=id,
        skill_id=skill_id,
        title=title,
        prompt=prompt.strip() + "\n",
        starter=starter.strip() + "\n",
        tests=tests.strip() + "\n",
        reference=reference.strip() + "\n",
        minutes=minutes,
    )


DRILLS: tuple[Drill, ...] = (
    _drill(
        id="requirements-cancel",
        skill_id="requirements",
        title="Отмена заказа по правилам",
        prompt="""
Правила отмены заказа:

- статус new — отменить можно всегда;
- статус paid — только если с момента заказа прошло меньше 24 часов;
- статусы shipped, delivered, cancelled — нельзя;
- любой другой статус — ValueError.

Ровно 24 часа — уже поздно.
""",
        starter="""
def can_cancel(status: str, hours_since_order: float) -> bool:
    ...
""",
        tests="""
import pytest
from solution import can_cancel


def test_new_is_always_cancellable():
    assert can_cancel("new", 0) is True
    assert can_cancel("new", 1000) is True


def test_paid_depends_on_the_window():
    assert can_cancel("paid", 23.9) is True
    assert can_cancel("paid", 24) is False


def test_late_statuses_are_final():
    assert can_cancel("shipped", 0) is False
    assert can_cancel("delivered", 0) is False
    assert can_cancel("cancelled", 0) is False


def test_unknown_status_raises():
    with pytest.raises(ValueError):
        can_cancel("paused", 0)
""",
        reference="""
STATUSES = {"new", "paid", "shipped", "delivered", "cancelled"}


def can_cancel(status: str, hours_since_order: float) -> bool:
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    if status == "new":
        return True
    if status == "paid":
        return hours_since_order < 24
    return False
""",
    ),
    _drill(
        id="edge-average",
        skill_id="edge_cases",
        title="Среднее, которое не падает",
        prompt="""
Посчитай среднее по списку чисел. В списке попадаются None — их нужно
пропускать.

Пустой список и список из одних None дают 0.0. Результат всегда float.
""",
        starter="""
def average(values: list[float | None]) -> float:
    ...
""",
        tests="""
from solution import average


def test_plain_average():
    assert average([1, 2, 3]) == 2.0


def test_none_values_are_skipped():
    assert average([1, None, 3]) == 2.0


def test_empty_input_is_zero():
    assert average([]) == 0.0
    assert average([None, None]) == 0.0


def test_result_is_a_float():
    assert isinstance(average([1, 1]), float)
""",
        reference="""
def average(values):
    numbers = [value for value in values if value is not None]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)
""",
    ),
    _drill(
        id="edge-chunk",
        skill_id="edge_cases",
        title="Нарезка на страницы",
        prompt="""
Разрежь список на куски по size элементов.

Последний кусок может быть короче. Пустой список даёт пустой результат.
size меньше 1 — ValueError. Исходный список не меняется.
""",
        starter="""
def chunk(items: list, size: int) -> list[list]:
    ...
""",
        tests="""
import pytest
from solution import chunk


def test_last_chunk_may_be_shorter():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_empty_list_gives_nothing():
    assert chunk([], 3) == []


def test_size_larger_than_the_list():
    assert chunk([1, 2], 10) == [[1, 2]]


def test_bad_size_raises():
    with pytest.raises(ValueError):
        chunk([1, 2], 0)


def test_source_list_is_not_touched():
    items = [1, 2, 3]
    chunk(items, 2)
    assert items == [1, 2, 3]
""",
        reference="""
def chunk(items, size):
    if size < 1:
        raise ValueError("size must be positive")
    return [list(items[start: start + size]) for start in range(0, len(items), size)]
""",
    ),
    _drill(
        id="validation-page",
        skill_id="validation",
        title="Номер страницы из запроса",
        prompt="""
Из запроса приходит номер страницы: целое число или строка из цифр.

Верни int в диапазоне 1..1000. Пробелы по краям строки допустимы.
Всё остальное — ValueError: дробное, отрицательное, не число, вне диапазона.
True и False — тоже не числа, хотя Python думает иначе.
""",
        starter="""
def parse_page(raw: object) -> int:
    ...
""",
        tests="""
import pytest
from solution import parse_page


def test_numbers_and_digit_strings_pass():
    assert parse_page(7) == 7
    assert parse_page("7") == 7
    assert parse_page("  7  ") == 7


def test_range_is_checked():
    with pytest.raises(ValueError):
        parse_page(0)
    with pytest.raises(ValueError):
        parse_page(1001)


def test_not_a_number():
    with pytest.raises(ValueError):
        parse_page("7.5")
    with pytest.raises(ValueError):
        parse_page(None)


def test_bool_is_not_a_page():
    with pytest.raises(ValueError):
        parse_page(True)
""",
        reference="""
def parse_page(raw):
    if isinstance(raw, bool):
        raise ValueError("page must be a number")
    if isinstance(raw, int):
        page = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        page = int(raw.strip())
    else:
        raise ValueError("page must be a number")
    if not 1 <= page <= 1000:
        raise ValueError("page out of range")
    return page
""",
    ),
    _drill(
        id="validation-email",
        skill_id="validation",
        title="Почта в одном виде",
        prompt="""
Приведи почту к одному виду: убери пробелы по краям, переведи в нижний
регистр.

В адресе ровно одна собака, и обе части непустые. Иначе ValueError.
""",
        starter="""
def normalize_email(raw: str) -> str:
    ...
""",
        tests="""
import pytest
from solution import normalize_email


def test_trimmed_and_lowered():
    assert normalize_email("  Ivan@Example.COM ") == "ivan@example.com"


def test_one_at_sign_only():
    with pytest.raises(ValueError):
        normalize_email("ivan@@example.com")
    with pytest.raises(ValueError):
        normalize_email("ivan.example.com")


def test_both_parts_are_required():
    with pytest.raises(ValueError):
        normalize_email("@example.com")
    with pytest.raises(ValueError):
        normalize_email("ivan@")
""",
        reference="""
def normalize_email(raw):
    value = (raw or "").strip().lower()
    parts = value.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("bad email")
    return value
""",
    ),
    _drill(
        id="errors-to-int",
        skill_id="error_handling",
        title="Перехват ровно того, что ждали",
        prompt="""
Переведи значение в int. Если это не получается — верни default.

Ловить можно только ValueError и TypeError. Любое другое исключение должно
дойти до вызывающего кода: except Exception прячет чужие поломки.
""",
        starter="""
def to_int(value: object, default: int = 0) -> int:
    ...
""",
        tests="""
import pytest
from solution import to_int


def test_plain_conversion():
    assert to_int("5") == 5
    assert to_int(5) == 5


def test_default_on_bad_input():
    assert to_int("x") == 0
    assert to_int(None) == 0
    assert to_int("x", default=-1) == -1


def test_other_errors_are_not_swallowed():
    class Weird:
        def __int__(self):
            raise KeyError("boom")

    with pytest.raises(KeyError):
        to_int(Weird())
""",
        reference="""
def to_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
""",
    ),
    _drill(
        id="errors-retry",
        skill_id="error_handling",
        title="Повтор только нужной ошибки",
        prompt="""
Вызови call() и повтори его, если он упал с TimeoutError. Всего не больше
attempts попыток.

Успех возвращается сразу. Любое другое исключение пробрасывается с первой
попытки — повторять его бессмысленно. Если все попытки вышли по таймауту,
пробрось последний TimeoutError.
""",
        starter="""
def retry(call, attempts: int = 3):
    ...
""",
        tests="""
import pytest
from solution import retry


def test_second_attempt_wins():
    calls = []

    def call():
        calls.append(1)
        if len(calls) < 2:
            raise TimeoutError("slow")
        return "ok"

    assert retry(call) == "ok"
    assert len(calls) == 2


def test_other_errors_are_not_retried():
    calls = []

    def call():
        calls.append(1)
        raise ValueError("bad")

    with pytest.raises(ValueError):
        retry(call)
    assert len(calls) == 1


def test_all_attempts_spent():
    calls = []

    def call():
        calls.append(1)
        raise TimeoutError("slow")

    with pytest.raises(TimeoutError):
        retry(call, attempts=3)
    assert len(calls) == 3
""",
        reference="""
def retry(call, attempts=3):
    last = None
    for _ in range(max(1, attempts)):
        try:
            return call()
        except TimeoutError as error:
            last = error
    raise last
""",
    ),
    _drill(
        id="testing-cases",
        skill_id="testing",
        title="Случаи, которые ловят ошибку",
        prompt="""
Функция считает итог со скидкой целыми числами:

    итог = total - total * percent // 100

Где-то в проде живёт её версия с ошибкой округления: она считает через float.
Тестов на неё нет.

Верни из cases() список случаев (total, percent, expected) — не меньше трёх.
Все они должны сходиться с правильной формулой, и хотя бы один должен
расходиться с версией через float.
""",
        starter="""
def cases() -> list[tuple[int, int, int]]:
    ...
""",
        tests="""
from solution import cases


def correct(total, percent):
    return total - total * percent // 100


def buggy(total, percent):
    return int(total * (1 - percent / 100))


def test_at_least_three_cases():
    assert len(cases()) >= 3


def test_every_case_matches_the_spec():
    for total, percent, expected in cases():
        assert correct(total, percent) == expected, (total, percent)


def test_some_case_catches_the_rounding_bug():
    assert any(buggy(total, percent) != expected for total, percent, expected in cases())
""",
        reference="""
def cases():
    return [
        (100, 0, 100),
        (5997, 15, 5098),
        (0, 50, 0),
    ]
""",
    ),
    _drill(
        id="algorithms-top",
        skill_id="algorithms",
        title="Топ по счётчику",
        prompt="""
Из словаря «ключ → счётчик» верни n пар (ключ, счётчик), отсортированных по
счётчику по убыванию.

При равных счётчиках первым идёт меньший ключ. n меньше 1 даёт пустой список,
n больше размера словаря — весь словарь.
""",
        starter="""
def top_n(counts: dict[int, int], n: int) -> list[tuple[int, int]]:
    ...
""",
        tests="""
from solution import top_n


def test_sorted_by_count():
    assert top_n({1: 5, 2: 9, 3: 1}, 2) == [(2, 9), (1, 5)]


def test_ties_go_by_key():
    assert top_n({5: 2, 1: 2, 3: 2}, 3) == [(1, 2), (3, 2), (5, 2)]


def test_small_and_large_n():
    assert top_n({1: 1}, 0) == []
    assert top_n({1: 1}, 10) == [(1, 1)]
    assert top_n({}, 3) == []
""",
        reference="""
def top_n(counts, n):
    if n < 1:
        return []
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ordered[:n]
""",
    ),
    _drill(
        id="algorithms-ranges",
        skill_id="algorithms",
        title="Слияние интервалов",
        prompt="""
Объедини пересекающиеся интервалы (start, end) и верни их по возрастанию
начала.

Соприкасающиеся интервалы тоже объединяются: (1, 3) и (3, 5) дают (1, 5).
Пустой вход даёт пустой список. Исходный список не меняется.
""",
        starter="""
def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    ...
""",
        tests="""
from solution import merge_ranges


def test_overlapping_ranges_merge():
    assert merge_ranges([(1, 4), (2, 6), (8, 9)]) == [(1, 6), (8, 9)]


def test_touching_ranges_merge():
    assert merge_ranges([(1, 3), (3, 5)]) == [(1, 5)]


def test_input_order_does_not_matter():
    assert merge_ranges([(8, 9), (1, 4)]) == [(1, 4), (8, 9)]


def test_empty_and_untouched():
    source = [(1, 2)]
    assert merge_ranges([]) == []
    merge_ranges(source)
    assert source == [(1, 2)]
""",
        reference="""
def merge_ranges(ranges):
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged
""",
    ),
    _drill(
        id="structures-group",
        skill_id="data_structures",
        title="Группировка заказов",
        prompt="""
Сгруппируй заказы по статусу: верни словарь «статус → список id» в том
порядке, в каком заказы шли на входе.

Пустой вход даёт пустой словарь. Заказ: {"id": int, "status": str}.
""",
        starter="""
def group_by_status(orders: list[dict]) -> dict[str, list[int]]:
    ...
""",
        tests="""
from solution import group_by_status


def test_groups_keep_input_order():
    orders = [
        {"id": 1, "status": "new"},
        {"id": 2, "status": "paid"},
        {"id": 3, "status": "new"},
    ]
    assert group_by_status(orders) == {"new": [1, 3], "paid": [2]}


def test_empty_input():
    assert group_by_status([]) == {}


def test_single_status():
    assert group_by_status([{"id": 9, "status": "paid"}]) == {"paid": [9]}
""",
        reference="""
def group_by_status(orders):
    grouped = {}
    for order in orders:
        grouped.setdefault(order["status"], []).append(order["id"])
    return grouped
""",
    ),
    _drill(
        id="structures-unique",
        skill_id="data_structures",
        title="Без повторов, но по порядку",
        prompt="""
Убери повторы из списка, сохранив порядок первых появлений.

Вход может быть длинным, поэтому проверка «уже видели» должна быть по
множеству, а не поиском по списку.
""",
        starter="""
def unique_in_order(items: list) -> list:
    ...
""",
        tests="""
from solution import unique_in_order


def test_first_occurrence_wins():
    assert unique_in_order([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_empty_and_unique_inputs():
    assert unique_in_order([]) == []
    assert unique_in_order([1, 2]) == [1, 2]


def test_long_input_is_not_quadratic():
    items = list(range(30000)) + list(range(30000))
    assert unique_in_order(items) == list(range(30000))
""",
        reference="""
def unique_in_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
""",
    ),
    _drill(
        id="quality-labels",
        skill_id="code_quality",
        title="Таблица вместо лестницы if",
        prompt="""
Верни человеческое название статуса: new — «Новый», paid — «Оплачен»,
shipped — «Отправлен», delivered — «Доставлен», cancelled — «Отменён».
Любой другой статус — «Неизвестно».

Соответствие опиши таблицей (словарём). Проверка смотрит и на поведение, и на
код: в решении должно остаться не больше одного if.
""",
        starter="""
def status_label(status: str) -> str:
    ...
""",
        tests="""
import ast
import inspect

import solution
from solution import status_label


def test_known_labels():
    assert status_label("new") == "Новый"
    assert status_label("paid") == "Оплачен"
    assert status_label("shipped") == "Отправлен"
    assert status_label("delivered") == "Доставлен"
    assert status_label("cancelled") == "Отменён"


def test_unknown_label():
    assert status_label("paused") == "Неизвестно"


def test_the_code_is_table_driven():
    tree = ast.parse(inspect.getsource(solution))
    ifs = [node for node in ast.walk(tree) if isinstance(node, ast.If)]
    assert len(ifs) <= 1, "лестница if осталась — вынеси соответствие в словарь"
""",
        reference="""
LABELS = {
    "new": "Новый",
    "paid": "Оплачен",
    "shipped": "Отправлен",
    "delivered": "Доставлен",
    "cancelled": "Отменён",
}


def status_label(status):
    return LABELS.get(status, "Неизвестно")
""",
    ),
    _drill(
        id="api-page-response",
        skill_id="api_design",
        title="Контракт страницы",
        prompt="""
Собери тело ответа для постраничного списка: ровно пять ключей — items, page,
page_size, total, pages.

pages — сколько всего страниц при таком page_size, округление вверх. При
total = 0 это 0. Лишних ключей в ответе быть не должно: по этому телу пишут
клиент.
""",
        starter="""
def page_response(items: list, page: int, page_size: int, total: int) -> dict:
    ...
""",
        tests="""
from solution import page_response


def test_contract_keys():
    body = page_response([1, 2], 1, 20, 2)
    assert set(body) == {"items", "page", "page_size", "total", "pages"}


def test_pages_round_up():
    assert page_response([], 1, 20, 45)["pages"] == 3
    assert page_response([], 1, 20, 40)["pages"] == 2


def test_empty_result():
    body = page_response([], 1, 20, 0)
    assert body["pages"] == 0 and body["items"] == []
""",
        reference="""
def page_response(items, page, page_size, total):
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
    }
""",
    ),
    _drill(
        id="storage-insert",
        skill_id="data_storage",
        title="Вставка с параметрами",
        prompt="""
Вставь заказ в таблицу orders(id INTEGER PRIMARY KEY, customer TEXT NOT NULL).

Значения передавай параметрами запроса, а не склейкой строк: в имени клиента
встречаются кавычки. Ошибку базы не глуши — пусть дойдёт до вызывающего кода.
""",
        starter="""
import sqlite3


def insert_order(conn: sqlite3.Connection, order: dict) -> None:
    ...
""",
        tests="""
import sqlite3

import pytest
from solution import insert_order


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer TEXT NOT NULL)")
    return connection


def test_quotes_survive(conn):
    insert_order(conn, {"id": 1, "customer": "O'Brien \\"the first\\""})
    rows = conn.execute("SELECT id, customer FROM orders").fetchall()
    assert rows == [(1, "O'Brien \\"the first\\"")]


def test_duplicate_id_is_not_swallowed(conn):
    insert_order(conn, {"id": 1, "customer": "Ivan"})
    with pytest.raises(sqlite3.IntegrityError):
        insert_order(conn, {"id": 1, "customer": "Petr"})


def test_several_orders_land(conn):
    insert_order(conn, {"id": 1, "customer": "Ivan"})
    insert_order(conn, {"id": 2, "customer": "Petr"})
    rows = conn.execute("SELECT id FROM orders ORDER BY id").fetchall()
    assert rows == [(1,), (2,)]
""",
        reference="""
import sqlite3


def insert_order(conn, order):
    conn.execute(
        "INSERT INTO orders (id, customer) VALUES (?, ?)",
        (order["id"], order["customer"]),
    )
""",
    ),
    _drill(
        id="async-fetch-all",
        skill_id="async_concurrency",
        title="Запросы параллельно",
        prompt="""
Собери статусы по списку id: для каждого id вызывается корутина
fetch_one(id). Верни словарь «id → результат».

Запросы должны идти параллельно, а не по очереди. Пустой список даёт пустой
словарь.
""",
        starter="""
import asyncio


async def fetch_all(ids: list[int], fetch_one) -> dict[int, object]:
    ...
""",
        tests="""
import asyncio

from solution import fetch_all


def test_results_are_keyed_by_id():
    async def main():
        async def fetch_one(order_id):
            return order_id * 2

        return await fetch_all([1, 2, 3], fetch_one)

    assert asyncio.run(main()) == {1: 2, 2: 4, 3: 6}


def test_empty_input():
    async def main():
        async def fetch_one(order_id):
            raise AssertionError("не должно вызываться")

        return await fetch_all([], fetch_one)

    assert asyncio.run(main()) == {}


def test_requests_run_at_the_same_time():
    async def main():
        barrier = asyncio.Barrier(3)

        async def fetch_one(order_id):
            # ждёт, пока сюда зайдут все три: последовательный код тут встанет
            await barrier.wait()
            return "ok"

        return await asyncio.wait_for(fetch_all([1, 2, 3], fetch_one), timeout=3)

    assert asyncio.run(main()) == {1: "ok", 2: "ok", 3: "ok"}
""",
        reference="""
import asyncio


async def fetch_all(ids, fetch_one):
    if not ids:
        return {}
    results = await asyncio.gather(*(fetch_one(order_id) for order_id in ids))
    return dict(zip(ids, results))
""",
    ),
    _drill(
        id="security-redact",
        skill_id="security",
        title="Секреты не доезжают до логов",
        prompt="""
Перед записью в лог подготовь копию данных: значения ключей password, token,
secret и authorization замени на "***". Регистр ключа значения не имеет.

Внутрь вложенных словарей и списков тоже нужно зайти. Исходные данные менять
нельзя: их дальше использует код.
""",
        starter="""
def redact(payload: dict) -> dict:
    ...
""",
        tests="""
from solution import redact


def test_top_level_secrets():
    assert redact({"user": "ivan", "password": "123"}) == {"user": "ivan", "password": "***"}


def test_case_does_not_matter():
    assert redact({"Token": "abc"}) == {"Token": "***"}


def test_nested_structures():
    data = {"items": [{"secret": "s"}], "meta": {"authorization": "Bearer x", "id": 1}}
    assert redact(data) == {"items": [{"secret": "***"}], "meta": {"authorization": "***", "id": 1}}


def test_source_is_not_modified():
    data = {"password": "123"}
    redact(data)
    assert data == {"password": "123"}
""",
        reference="""
HIDDEN = {"password", "token", "secret", "authorization"}


def redact(payload):
    if isinstance(payload, dict):
        return {
            key: "***" if str(key).lower() in HIDDEN else redact(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact(item) for item in payload]
    return payload
""",
    ),
    _drill(
        id="ui-reducer",
        skill_id="frontend_ui",
        title="Состояние экрана без сюрпризов",
        prompt="""
Экран списка живёт в состоянии {"status": "idle", "items": [], "error": ""}.

Собери чистую функцию перехода:

- {"type": "load"} — status становится "loading", error очищается;
- {"type": "loaded", "items": [...]} — status "ready", items из действия;
- {"type": "failed", "error": "..."} — status "error", текст в error, items
  остаются прежними;
- любое другое действие — состояние не меняется.

Старое состояние менять нельзя: возвращай новое.
""",
        starter="""
def reduce(state: dict, action: dict) -> dict:
    ...
""",
        tests="""
from solution import reduce


IDLE = {"status": "idle", "items": [], "error": ""}


def test_load_clears_the_error():
    state = {"status": "error", "items": [], "error": "упало"}
    assert reduce(state, {"type": "load"}) == {"status": "loading", "items": [], "error": ""}


def test_loaded_takes_the_items():
    assert reduce(IDLE, {"type": "loaded", "items": [1, 2]}) == {
        "status": "ready",
        "items": [1, 2],
        "error": "",
    }


def test_failed_keeps_the_items():
    state = {"status": "ready", "items": [1], "error": ""}
    assert reduce(state, {"type": "failed", "error": "сеть"}) == {
        "status": "error",
        "items": [1],
        "error": "сеть",
    }


def test_unknown_action_changes_nothing():
    assert reduce(IDLE, {"type": "whatever"}) == IDLE


def test_the_old_state_is_not_mutated():
    state = {"status": "idle", "items": [], "error": ""}
    reduce(state, {"type": "loaded", "items": [1]})
    assert state == {"status": "idle", "items": [], "error": ""}
""",
        reference="""
def reduce(state, action):
    kind = action.get("type")
    if kind == "load":
        return {**state, "status": "loading", "error": ""}
    if kind == "loaded":
        return {**state, "status": "ready", "items": action.get("items", []), "error": ""}
    if kind == "failed":
        return {**state, "status": "error", "error": action.get("error", "")}
    return state
""",
    ),
    _drill(
        id="observability-record",
        skill_id="observability",
        title="Запись в лог без лишнего",
        prompt="""
Собери запись для лога: словарь с ключами event, duration_ms, user_id и level.

duration_ms — целое число (округляй), level — "warn" при duration_ms от 1000 и
"info" ниже. Токен в запись попадать не должен ни под каким ключом: по логам
ищут проблемы, а не доступы.
""",
        starter="""
def log_record(event: str, duration_ms: float, user_id: int, token: str = "") -> dict:
    ...
""",
        tests="""
from solution import log_record


def test_required_keys_only():
    record = log_record("review.done", 12.4, 7, token="secret-abc")
    assert set(record) == {"event", "duration_ms", "user_id", "level"}


def test_duration_is_an_int():
    record = log_record("review.done", 12.6, 7)
    assert record["duration_ms"] == 13 and isinstance(record["duration_ms"], int)


def test_level_depends_on_duration():
    assert log_record("e", 999, 1)["level"] == "info"
    assert log_record("e", 1000, 1)["level"] == "warn"


def test_the_token_never_leaks():
    record = log_record("review.done", 5, 7, token="secret-abc")
    assert "secret-abc" not in str(record)
""",
        reference="""
def log_record(event, duration_ms, user_id, token=""):
    duration = int(round(duration_ms))
    return {
        "event": event,
        "duration_ms": duration,
        "user_id": user_id,
        "level": "warn" if duration >= 1000 else "info",
    }
""",
    ),
)


DRILL_BY_ID: dict[str, Drill] = {drill.id: drill for drill in DRILLS}

DRILLS_BY_SKILL: dict[str, tuple[Drill, ...]] = {}
for _drill_item in DRILLS:
    DRILLS_BY_SKILL[_drill_item.skill_id] = DRILLS_BY_SKILL.get(_drill_item.skill_id, ()) + (_drill_item,)
