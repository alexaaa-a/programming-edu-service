import asyncio
from dataclasses import replace

import pytest

from agent_service.app.application.tools.hidden_tests import (
    HiddenTestCase,
    HiddenTestRun,
    parse_junit,
    run_hidden_tests,
)
from agent_service.app.application.tools.models import ToolReport
from agent_service.app.application.tools.past_reviews import hidden_tests_cap, score_cap_from_report


TESTS = """
from solution import order_total

def test_sum():
    assert order_total([{"price": 100, "qty": 2}]) == 200

def test_discount_rounds_down():
    assert order_total([{"price": 1999, "qty": 3}], 15) == 5098

def test_empty_cart():
    assert order_total([]) == 0
"""

GOOD = """
def order_total(items, promo_percent=0):
    total = sum(item["price"] * item["qty"] for item in items)
    return total - total * promo_percent // 100
"""

ROUNDS_WRONG = """
def order_total(items, promo_percent=0):
    total = sum(item["price"] * item["qty"] for item in items)
    return int(total * (1 - promo_percent / 100))
"""


def test_passing_solution_reports_every_test():
    run = asyncio.run(run_hidden_tests(GOOD, TESTS))
    assert run.status == "passed"
    assert (run.passed, run.total, run.failed) == (3, 3, 0)
    assert run.all_passed is True
    assert run.failed_names == []


def test_failing_solution_names_the_failing_test_and_keeps_the_rest():
    run = asyncio.run(run_hidden_tests(ROUNDS_WRONG, TESTS))
    assert run.status == "failed"
    assert (run.passed, run.total) == (2, 3)
    assert run.failed_names == ["test_discount_rounds_down"]
    failure = next(case for case in run.cases if not case.passed)
    assert "5098" in failure.message


def test_broken_solution_is_an_error_not_a_failed_test():
    run = asyncio.run(run_hidden_tests("def order_total(:", TESTS))
    assert run.status == "error"
    assert run.total == 0
    assert "не импортируется" in run.detail
    assert "/tmp" not in run.detail


def test_missing_function_is_an_import_error():
    run = asyncio.run(run_hidden_tests("def other(): return 1", TESTS))
    assert run.status == "error"
    assert "ImportError" in run.detail


def test_no_tests_or_no_code_is_unavailable():
    assert asyncio.run(run_hidden_tests(GOOD, "   ")).status == "unavailable"
    assert asyncio.run(run_hidden_tests("", TESTS)).status == "unavailable"


def test_file_without_tests_is_reported_as_broken_task():
    run = asyncio.run(run_hidden_tests(GOOD, "x = 1"))
    assert run.status == "error"
    assert "ни одного теста" in run.detail


def test_parse_junit_reads_pytest_report():
    xml = """<?xml version="1.0"?>
    <testsuites><testsuite name="pytest" tests="3">
      <testcase classname="test_task" name="test_a"/>
      <testcase classname="test_task" name="test_b">
        <failure message="assert 1 == 2">E assert 1 == 2</failure>
      </testcase>
      <testcase classname="test_task" name="test_skipped"><skipped/></testcase>
    </testsuite></testsuites>"""
    run = parse_junit(xml)
    assert run is not None
    assert (run.total, run.passed, run.failed) == (2, 1, 1)
    assert run.failed_names == ["test_b"]
    assert run.ratio == pytest.approx(0.5)


def test_parse_junit_survives_garbage():
    assert parse_junit("not xml") is None
    assert parse_junit("<testsuite/>") is None


def test_cap_follows_the_share_of_passing_tests():
    def run(passed: int, total: int) -> HiddenTestRun:
        return HiddenTestRun(status="failed", total=total, passed=passed, failed=total - passed)

    assert hidden_tests_cap(run(0, 4)) == 2
    assert hidden_tests_cap(run(2, 4)) == 5
    assert hidden_tests_cap(run(3, 4)) == 7
    assert hidden_tests_cap(run(19, 20)) == 7
    assert hidden_tests_cap(HiddenTestRun(status="passed", total=4, passed=4)) is None
    assert hidden_tests_cap(None) is None


def test_cap_treats_a_broken_run_as_a_broken_solution():
    assert hidden_tests_cap(HiddenTestRun(status="error", detail="не импортируется")) == 2
    assert hidden_tests_cap(HiddenTestRun(status="timeout")) == 3


def test_report_cap_takes_the_strictest_signal():
    failing = HiddenTestRun(status="failed", total=4, passed=3, failed=1)
    report = ToolReport(language="python", hidden=failing)
    # 3 из 4 — потолок 7, но сломанная компиляция строже
    assert score_cap_from_report(report) == 7
    assert score_cap_from_report(replace(report, compile_ok=False)) == 2


def test_prompt_block_states_the_test_result_as_a_fact():
    passing = ToolReport(
        language="python",
        hidden=HiddenTestRun(status="passed", total=3, passed=3),
    )
    block = passing.as_prompt_block()
    assert "пройдены все 3" in block
    assert "не пиши, что решение не работает" in block.lower()

    failing = ToolReport(
        language="python",
        hidden=HiddenTestRun(
            status="failed",
            total=3,
            passed=1,
            failed=2,
            cases=[
                HiddenTestCase(name="test_empty", passed=False, message="IndexError"),
                HiddenTestCase(name="test_limit", passed=False),
            ],
        ),
    )
    block = failing.as_prompt_block()
    assert "прошло 1 из 3" in block.lower()
    assert "test_empty" in block
    assert failing.as_dict()["hidden_tests"]["failed_names"] == ["test_empty", "test_limit"]


def test_report_without_tests_says_so():
    report = ToolReport(language="python")
    assert report.as_dict()["hidden_tests"] is None
    assert "Тесты задачи" not in report.as_prompt_block()
