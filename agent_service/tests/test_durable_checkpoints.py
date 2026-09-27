import hashlib

from agent_service.app.application.review.checkpoints import (
    content_hash,
    dump_review,
    load_review,
    review_graph_thread_id,
    review_run_key,
)
from agent_service.app.application.dto import Review


def test_content_hash_stable():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("Hello")


def test_dump_load_review_roundtrip():
    original = Review(score=7, feedback="ok", suggestions=["a"])
    restored = load_review(dump_review(original))
    assert restored is not None
    assert restored.score == 7
    assert restored.feedback == "ok"
    assert restored.suggestions == ["a"]


def test_review_run_key_includes_attempt():
    assert review_run_key(submission_id="1", attempt=2) == "review:1:a2"
    assert hashlib.sha256(b"x").hexdigest()[:24] == content_hash("x")


def test_review_graph_thread_id_changes_with_code():
    a = review_graph_thread_id(
        submission_id="1",
        attempt=1,
        code="v1",
        task_description="task",
    )
    b = review_graph_thread_id(
        submission_id="1",
        attempt=1,
        code="v2",
        task_description="task",
    )
    assert a.startswith("review:1:a1:")
    assert a != b
