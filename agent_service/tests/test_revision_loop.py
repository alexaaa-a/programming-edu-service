from agent_service.app.application.orchestrators.review_orchestrator import _revision_block


def test_revision_block_empty_without_previous_feedback():
    assert _revision_block(attempt=2, previous_feedback=None) == ""
    assert _revision_block(attempt=2, previous_feedback="   ") == ""


def test_revision_block_mentions_attempt_and_previous_notes():
    text = _revision_block(
        attempt=2,
        previous_feedback="Скор 3/10. Голый except. Правки: лови конкретные исключения",
    )
    assert "попытка 2" in text
    assert "Голый except" in text
    assert "исправлено" in text
