from datetime import datetime, timedelta, timezone

from submission_service.app.application.dto.submission import (
    ChallengeResultDTO,
    CriterionResultDTO,
    ReviewDTO,
    SubmissionDTO,
)
from submission_service.app.application.trajectory import TaskInfo, compute_trajectory
from submission_service.app.application.trajectory.calibration import (
    calibrate,
    constraint_margins,
)
from submission_service.app.application.trajectory.knowledge import (
    BktParams,
    KnowledgeTracer,
    Observation,
    condition,
    slip_probability,
)
from submission_service.app.application.trajectory.planner import available_tasks, choose_next_task
from submission_service.app.application.trajectory.simulation import SimConfig, simulate
from submission_service.app.application.trajectory.skills import classify, task_profile


NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
EDGE = "Обработать пустой список и отрицательные числа"
SQL = "Запрос к базе данных параметризован и защищён от SQL-инъекций"
TESTS = "Добавить pytest-тесты на основной сценарий"
LOGIC = "Функция возвращает сумму двух чисел"


def _sub(
        task_id: int,
        at: datetime,
        criteria: list[tuple[str, bool]],
        submission_id: int,
        score: int | None = None,
        challenges: list[tuple[str, str]] | None = None,
) -> SubmissionDTO:
    passed = sum(1 for _, ok in criteria if ok)
    value = score if score is not None else 1 + round(9 * passed / max(1, len(criteria)))
    return SubmissionDTO(
        submission_id=submission_id,
        user_id=7,
        task_id=task_id,
        code="x",
        status="reviewed",
        review=ReviewDTO(
            score=value,
            feedback="",
            suggestions=[],
            criteria=[
                CriterionResultDTO(id=f"c{i}", text=text, passed=ok, note="")
                for i, (text, ok) in enumerate(criteria)
            ],
            challenges=[
                ChallengeResultDTO(text=text, severity=severity)
                for text, severity in (challenges or [])
            ],
        ),
        created_at=at,
        reviewed_at=at,
    )


def _obs(skill: str, outcome: float, weight: float = 1.0) -> Observation:
    return Observation(skill_id=skill, outcome=outcome, weight=weight, source="criterion")


def test_classifier_maps_criteria_to_skills():
    assert classify(EDGE)[0][0] == "edge_cases"
    assert classify(SQL)[0][0] in {"data_storage", "security"}
    assert {skill for skill, _ in classify(SQL)} == {"data_storage", "security"}
    assert classify(TESTS)[0][0] == "testing"
    assert classify(LOGIC) == [("requirements", 1.0)]
    assert abs(sum(share for _, share in classify(SQL)) - 1.0) < 1e-9


def test_task_profile_is_normalized_distribution():
    profile = task_profile(f"{EDGE}. {TESTS}. {LOGIC}.")
    assert abs(sum(profile.values()) - 1.0) < 1e-9
    assert {"edge_cases", "testing", "requirements"} <= set(profile)


def test_default_params_satisfy_calibration_constraints():
    margins = constraint_margins(BktParams())
    assert min(margins.values()) > 0.02
    best = calibrate()
    defaults = BktParams()
    assert (best.params.p_init, best.params.p_learn, best.params.p_slip, best.params.p_guess) == (
        defaults.p_init,
        defaults.p_learn,
        defaults.p_slip,
        defaults.p_guess,
    )


def test_three_successes_in_a_row_reach_mastery_two_do_not():
    tracer = KnowledgeTracer(BktParams(individual_prior=False))
    tracer.observe(NOW, [_obs("edge_cases", 1)])
    tracer.observe(NOW + timedelta(hours=1), [_obs("edge_cases", 1)])
    assert tracer.state("edge_cases", NOW + timedelta(hours=1)).status != "mastered"
    tracer.observe(NOW + timedelta(hours=2), [_obs("edge_cases", 1)])
    assert tracer.state("edge_cases", NOW + timedelta(hours=2)).status == "mastered"


def test_partial_credit_sits_between_success_and_failure():
    params = BktParams()
    ok = condition(0.3, [_obs("x", 1.0)], params)
    half = condition(0.3, [_obs("x", 0.5)], params)
    bad = condition(0.3, [_obs("x", 0.0)], params)
    assert bad < half < ok


def test_low_weight_evidence_moves_belief_less():
    params = BktParams()
    strong = condition(0.6, [_obs("x", 0.0, weight=1.0)], params)
    weak = condition(0.6, [_obs("x", 0.0, weight=0.25)], params)
    assert strong < weak < 0.6


def test_slip_probability_separates_mastered_from_new():
    params = BktParams()
    assert slip_probability(0.98, params) >= 0.5
    assert slip_probability(params.p_init, params) < 0.1


def test_forgetting_turns_mastered_skill_into_fading():
    tracer = KnowledgeTracer(BktParams(individual_prior=False))
    for hours in (0, 1, 2):
        tracer.observe(NOW + timedelta(hours=hours), [_obs("testing", 1)])
    fresh = tracer.state("testing", NOW + timedelta(hours=3))
    stale = tracer.state("testing", NOW + timedelta(days=90))
    assert fresh.status == "mastered"
    assert stale.status == "fading"
    assert stale.p_now < fresh.p_now
    assert stale.p_now >= BktParams().p_init


def test_spaced_successes_slow_down_forgetting():
    massed = KnowledgeTracer(BktParams(individual_prior=False))
    spaced = KnowledgeTracer(BktParams(individual_prior=False))
    for step in range(3):
        massed.observe(NOW + timedelta(hours=step), [_obs("testing", 1)])
        spaced.observe(NOW + timedelta(days=step * 3), [_obs("testing", 1)])
    later = NOW + timedelta(days=60)
    assert spaced.state("testing", later).half_life_days > massed.state("testing", later).half_life_days
    assert spaced.state("testing", later).p_now > massed.state("testing", later).p_now


def test_individual_prior_follows_student_history():
    strong = KnowledgeTracer()
    weak = KnowledgeTracer()
    for step in range(4):
        strong.observe(NOW + timedelta(hours=step), [_obs(f"s{step}", 1)])
        weak.observe(NOW + timedelta(hours=step), [_obs(f"s{step}", 0)])
    assert strong.individual_prior() > BktParams().p_init > weak.individual_prior()
    assert strong.state("unseen", NOW).p_now == strong.individual_prior()
    assert KnowledgeTracer().individual_prior() == BktParams().p_init


def test_challenge_lowers_mastery_of_its_skill():
    base = [(LOGIC, True)]
    clean = compute_trajectory([_sub(1, NOW, base, 1)], task_id=1, now=NOW)
    flagged = compute_trajectory(
        [_sub(1, NOW, base, 1, challenges=[("Падает на пустом списке", "high")])],
        task_id=1,
        now=NOW,
    )
    edge = {skill.id: skill for skill in flagged.skills}
    assert "edge_cases" in edge
    assert edge["edge_cases"].mastery < BktParams().p_init
    assert all(skill.id != "edge_cases" for skill in clean.skills)


def test_knowledge_gap_sends_to_chat_with_concrete_focus():
    result = compute_trajectory(
        [_sub(5, NOW, [(EDGE, False), ("Обработать деление на ноль", False), (LOGIC, True)], 1, score=6)],
        task_id=5,
        now=NOW,
        current_task_status="review",
    )
    assert result.action == "chat"
    assert result.focus is not None
    assert result.focus.kind == "learn"
    assert result.focus.skill_id == "edge_cases"
    assert result.focus.mentor_name == "Эмма"
    assert len(result.focus.steps) == 3
    assert "спроси Эмму" in result.reason
    kinds = [item.kind for item in result.recommendations]
    assert kinds[:2] == ["fix", "fix"]
    assert "learn" in kinds


def test_slip_on_mastered_skill_suggests_revise_not_chat():
    history = [
        _sub(task, NOW - timedelta(days=10 - task), [(EDGE, True), (LOGIC, True)], task)
        for task in range(1, 5)
    ]
    history.append(
        _sub(9, NOW, [(EDGE, False), (LOGIC, True), ("Вернуть результат в формате списка", True)], 9, score=7)
    )
    result = compute_trajectory(history, task_id=9, now=NOW, current_task_status="review")
    assert result.action == "revise"
    assert result.focus is not None
    assert result.focus.kind == "fix"
    assert result.focus.skill_id == "edge_cases"


def test_next_task_prefers_started_work_then_learning_edge():
    history = [
        _sub(task, NOW - timedelta(days=6 - task), [(LOGIC, True), (EDGE, task > 2)], task)
        for task in range(1, 5)
    ]
    tasks = [
        TaskInfo(task_id=4, status="done", description=LOGIC, title="Сделано", order=0),
        TaskInfo(
            task_id=10,
            status="todo",
            description="Функция возвращает произведение двух чисел.",
            title="Произведение",
            order=1,
        ),
        TaskInfo(
            task_id=11,
            status="todo",
            description=f"{EDGE}. Проверить граничные значения.",
            title="Границы",
            order=2,
        ),
    ]
    result = compute_trajectory(history, task_id=4, now=NOW, current_task_status="done", tasks=tasks)
    assert result.action == "next_task"
    assert result.next_task_id == 10
    assert any(item.kind == "next_task" and item.task_id == 10 for item in result.recommendations)

    free = compute_trajectory(
        history,
        task_id=4,
        now=NOW,
        current_task_status="done",
        tasks=tasks,
        can_pick_task=True,
    )
    assert free.next_task_id == 11

    started = tasks + [
        TaskInfo(task_id=12, status="in_progress", description=LOGIC, title="В работе", order=3)
    ]
    tracer = KnowledgeTracer()
    assert choose_next_task(started, tracer.snapshot(NOW), current_task_id=4).task_id == 12


def test_board_rules_decide_what_can_be_recommended():
    tracer = KnowledgeTracer()
    knowledge = tracer.snapshot(NOW)
    queue = [
        TaskInfo(task_id=1, status="todo", description=LOGIC, title="Первая", order=0),
        TaskInfo(task_id=2, status="todo", description=EDGE, title="Вторая", order=1),
    ]
    assert [task.task_id for task in available_tasks(queue)] == [1]
    assert [task.task_id for task in available_tasks(queue, can_pick=True)] == [1, 2]

    waiting = [TaskInfo(task_id=1, status="review", description=LOGIC, title="Первая", order=0)] + queue[1:]
    assert available_tasks(waiting) == []
    assert choose_next_task(waiting, knowledge, current_task_id=1) is None

    with_incident = waiting + [
        TaskInfo(task_id=9, status="todo", description=EDGE, title="Ночной инцидент", order=999)
    ]
    assert [task.task_id for task in available_tasks(with_incident)] == [9]


def test_recommendation_text_matches_the_board_rule():
    tracer = KnowledgeTracer()
    knowledge = tracer.snapshot(NOW)
    queue = [
        TaskInfo(task_id=1, status="todo", description=LOGIC, title="Первая", order=0),
        TaskInfo(task_id=2, status="todo", description=EDGE, title="Вторая", order=1),
    ]
    forced = choose_next_task(queue, knowledge, current_task_id=None)
    assert forced is not None and forced.only_choice is True

    chosen = choose_next_task(queue, knowledge, current_task_id=None, can_pick=True)
    assert chosen is not None and chosen.only_choice is False


def test_all_done_and_ready_opens_next_sprint():
    history = [
        _sub(task, NOW - timedelta(days=5 - task), [(LOGIC, True), (TESTS, True)], task)
        for task in range(1, 5)
    ]
    tasks = [TaskInfo(task_id=task, status="done", description=LOGIC) for task in range(1, 5)]
    result = compute_trajectory(history, task_id=4, now=NOW, current_task_status="done", tasks=tasks)
    assert result.action == "next_sprint"
    assert result.block_next_sprint is False
    assert result.readiness >= result.readiness_threshold
    assert result.focus is not None
    assert result.focus.kind == "stretch"


def test_start_without_history_prepares_for_task_skills():
    tasks = [TaskInfo(task_id=3, status="in_progress", description=f"{SQL}.")]
    result = compute_trajectory([], task_id=3, now=NOW, tasks=tasks)
    assert result.action == "start"
    assert result.focus is not None
    assert result.focus.kind == "prepare"
    assert result.focus.skill_id in {"data_storage", "security"}
    assert "Перед сдачей проверь" in result.reason


def test_velocity_is_positive_while_learning():
    history = [
        _sub(task, NOW - timedelta(days=3 - task), [(EDGE, True), (TESTS, True)], task)
        for task in range(1, 4)
    ]
    result = compute_trajectory(history, now=NOW)
    assert result.velocity > 0


def test_simulation_beats_legacy_formula_and_random_focus():
    report = simulate(SimConfig(students=120, tasks_per_student=20, seed=3))
    model = report.predictor("bkt_forgetting")
    legacy = report.predictor("legacy")
    assert model.auc > legacy.auc
    assert model.brier < legacy.brier
    assert model.log_loss < legacy.log_loss
    assert report.focus_by("bkt_forgetting").hit_rate > 1.5 * report.focus_by("random").hit_rate
    assert report.focus_by("bkt_forgetting").regret < report.focus_by("random").regret


def test_closed_task_does_not_ask_to_fix_its_criteria():
    history = [
        _sub(task, NOW - timedelta(days=4 - task), [(LOGIC, True), (TESTS, True)], task)
        for task in range(1, 4)
    ]
    history.append(_sub(4, NOW, [(LOGIC, True), (TESTS, True), (EDGE, False)], 4, score=9))
    tasks = [
        TaskInfo(task_id=4, status="done", description=LOGIC),
        TaskInfo(task_id=5, status="todo", description=EDGE),
    ]
    result = compute_trajectory(history, task_id=4, now=NOW, current_task_status="done", tasks=tasks)
    assert result.action == "next_task"
    assert all(item.kind != "fix" for item in result.recommendations)
    assert result.focus is not None
    assert result.focus.skill_id == "edge_cases"


def test_empty_criteria_texts_fall_back_to_score():
    weak = compute_trajectory([_sub(1, NOW, [("", True)], 1, score=3)], task_id=1, now=NOW)
    strong = compute_trajectory([_sub(1, NOW, [("", True)], 1, score=9)], task_id=1, now=NOW)
    assert weak.skills and strong.skills
    assert weak.skills[0].status == "gap"
    assert weak.skills[0].mastery < strong.skills[0].mastery
