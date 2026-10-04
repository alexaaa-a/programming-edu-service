import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ArrowLeft, ChevronRight, Loader2, MessageCircle } from "lucide-react";
import { toast } from "sonner";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import {
  CodeEditor,
  languageFromDirection,
  type EditorLang,
} from "../components/workspace/CodeEditor";
import { PrimaryButton } from "../components/onboarding/Field";
import { EmptyState } from "../components/EmptyState";
import { useRequireAuth } from "../hooks/useRequireAuth";
import {
  getBoard,
  getCareer,
  getMe,
  getMyAdminRole,
  getTaskSubmissions,
  spendBonus,
  runTaskTests,
  submitCode,
  submitPeerReview,
  updateTaskStatus,
} from "@/lib/api";
import { startBackgroundReviewPoll } from "@/lib/background-review";
import { reviewMarks, unanchoredCount } from "@/lib/review-marks";
import type { AdminRole, BoardResponse, Career, Submission, TaskResponse, TaskStatus, UserShow } from "@/lib/types";
import {
  SPEND_PRICE,
  boughtForTask,
  careerRights,
  formatRub,
  isNightIncident,
  hasUnusedEmma,
  presentTask,
  taskLock,
} from "@/lib/career-rights";
import { TestRunPanel } from "../components/workspace/TestRunPanel";
import type { TaskTestRun } from "@/lib/api";
import { scoreOutOfTen } from "@/lib/score";
import { countedRounds, evaluateCloseGate, MAX_ROUNDS } from "@/lib/close-gate";

function sortSubmissionsNewestFirst(subs: Submission[]): Submission[] {
  return [...subs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

function nextStatus(s: TaskStatus): TaskStatus | null {
  if (s === "todo") return "in_progress";
  if (s === "in_progress") return "review";
  if (s === "review") return "done";
  return null;
}

function flattenBoard(board: Awaited<ReturnType<typeof getBoard>>): TaskResponse[] {
  return [...board.todo, ...board.in_progress, ...board.review, ...board.done];
}

function canRevise(
  subs: Submission[],
  taskStatus: TaskStatus | undefined,
  maxRounds = MAX_ROUNDS,
): boolean {
  if (taskStatus !== "in_progress" && taskStatus !== "review") return false;
  if (subs.length === 0) return true;
  if (countedRounds(subs) >= maxRounds) return false;
  const newest = sortSubmissionsNewestFirst(subs)[0];
  return newest.status !== "pending";
}

function SpendRow({
  label,
  price,
  disabled,
  busy,
  onBuy,
}: {
  label: string;
  price: number;
  disabled: boolean;
  busy: boolean;
  onBuy: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <p className="text-sm">{label}</p>
      <button
        type="button"
        disabled={disabled}
        onClick={onBuy}
        className="shrink-0 text-xs text-primary disabled:text-muted-foreground"
      >
        {busy ? "Списываем…" : formatRub(price)}
      </button>
    </div>
  );
}

const statusCopy: Record<TaskStatus, string> = {
  todo: "К выполнению",
  in_progress: "В работе",
  review: "На ревью",
  done: "Готово",
};

export default function TaskPage() {
  useRequireAuth();
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [me, setMe] = useState<UserShow | null>(null);
  const [career, setCareer] = useState<Career | null>(null);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [latest, setLatest] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(true);
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [language, setLanguage] = useState<EditorLang>("python");
  const [submitting, setSubmitting] = useState(false);
  const [buying, setBuying] = useState<string | null>(null);
  const [testRun, setTestRun] = useState<TaskTestRun | null>(null);
  const [testsRunning, setTestsRunning] = useState(false);
  const [testsAvailable, setTestsAvailable] = useState(true);
  const [testsError, setTestsError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [focusLine, setFocusLine] = useState<number | null>(null);

  const idNum = taskId ? Number(taskId) : NaN;

  const loadTask = useCallback(async () => {
    if (Number.isNaN(idNum)) {
      setTask(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [profile, role, careerState] = await Promise.all([
        getMe(),
        getMyAdminRole(),
        getCareer(),
      ]);
      setMe(profile);
      setAdminRole(role.role);
      setCareer(careerState);

      const nextBoard = await getBoard();
      setBoard(nextBoard);
      const found = flattenBoard(nextBoard).find((t) => t.task_id === idNum);
      setTask(found ?? null);
      if (!found) {
        setCode("");
        setLatest(null);
        setSubmissions([]);
        return;
      }

      const subs = await getTaskSubmissions(found.task_id);
      const sorted = sortSubmissionsNewestFirst(subs);
      setSubmissions(sorted);
      if (sorted.length > 0) {
        const newest = sorted[0];
        setLatest(newest);
        setCode(newest.code);
      } else {
        setLatest(null);
        setCode("");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось загрузить задачу");
      setTask(null);
      setBoard(null);
      setCode("");
      setLatest(null);
      setSubmissions([]);
    } finally {
      setLoading(false);
    }
  }, [idNum]);

  useEffect(() => {
    void loadTask();
  }, [loadTask]);

  useEffect(() => {
    if (me?.direction) setLanguage(languageFromDirection(me.direction));
  }, [me?.direction]);

  useEffect(() => {
    if (!task || !latest || latest.status !== "pending") return;
    startBackgroundReviewPoll(latest.submission_id, task.task_id, task.title);
  }, [task, latest]);

  useEffect(() => {
    const handler = (e: Event) => {
      const d = (e as CustomEvent<{ taskId: number }>).detail;
      if (d.taskId === idNum) void loadTask();
    };
    window.addEventListener("submission-review-ready", handler);
    return () => window.removeEventListener("submission-review-ready", handler);
  }, [idNum, loadTask]);

  const attempt = countedRounds(submissions);
  const nextAttempt = attempt + 1;
  const pending = latest?.status === "pending";
  const reviewReady = Boolean(latest?.review);
  const extraRound = Boolean(task && boughtForTask(career?.purchases, "extra_round", task.task_id));
  const criteriaOpen = Boolean(task && boughtForTask(career?.purchases, "early_criteria", task.task_id));
  const maxRounds = extraRound ? MAX_ROUNDS + 1 : MAX_ROUNDS;
  const revisionAllowed = useMemo(
    () => canRevise(submissions, task?.status, maxRounds),
    [submissions, task?.status, maxRounds],
  );
  const codeLocked = !revisionAllowed;
  const isRevision = attempt >= 1 && revisionAllowed;
  const closeDecision = useMemo(
    () => evaluateCloseGate(submissions, maxRounds),
    [submissions, maxRounds],
  );
  const canClose = task?.status === "review" && closeDecision.allowed;

  // Замечания привязаны к строкам отправленного кода. Как только студент начал
  // править, подсветка уехала бы вместе со строками — поэтому она гаснет.
  const marksFresh = Boolean(latest?.review) && code === (latest?.code ?? "");
  const marks = useMemo(
    () => (marksFresh ? reviewMarks(latest?.review) : []),
    [marksFresh, latest],
  );
  const unanchored = marksFresh ? unanchoredCount(latest?.review) : 0;
  // Прошлая попытка: с ней сравнивается то, что сейчас в редакторе.
  const previousCode = useMemo(() => {
    const reviewed = submissions.filter((item) => item.submission_id !== latest?.submission_id);
    return reviewed.length > 0 ? reviewed[0].code : null;
  }, [submissions, latest]);
  const rights = careerRights(career?.grade, career?.appeal_used);
  const peerReview = task?.title === "Ревью стажёра";
  const lock = task && board ? taskLock(task, board, rights.pickFirstTask) : null;
  const locked = Boolean(lock);
  const brief = task
    ? presentTask(task.description, career?.grade, submissions.length > 0, criteriaOpen)
    : null;
  const emmaReady = hasUnusedEmma(career?.purchases);

  const handleRunTests = async () => {
    if (!task) return;
    setTestsRunning(true);
    setTestsError(null);
    try {
      const result = await runTaskTests(task.task_id, code);
      if (result === null) {
        setTestsAvailable(false);
        setTestRun(null);
        return;
      }
      setTestRun(result);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Не удалось прогнать тесты";
      setTestsError(message);
    } finally {
      setTestsRunning(false);
    }
  };

  const handleBuy = async (item: "extra_round" | "emma_session" | "early_criteria") => {
    if (!task) return;
    setBuying(item);
    try {
      const next = await spendBonus(item, task.task_id);
      setCareer(next);
      toast.success("Премия списана");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось списать премию");
    } finally {
      setBuying(null);
    }
  };

  const failingNote = (() => {
    const failed = latest?.review?.criteria?.filter((item) => !item.passed) ?? [];
    if (failed.length > 0) return failed.map((item) => item.text).join("; ");
    return latest?.review?.challenges?.[0]?.text || latest?.review?.feedback || "";
  })();

  const handleAdvance = async () => {
    if (!task) return;
    const next = nextStatus(task.status);
    if (!next) return;
    if (next === "done" && !canClose) {
      toast.error(closeDecision.reason);
      return;
    }
    setAdvancing(true);
    try {
      await updateTaskStatus(task.task_id, next);
      if (next === "done" && closeDecision.allowed && closeDecision.quality === "weak") {
        toast.message("Задача закрыта как слабая", {
          description: "К следующей можно, но это не полный зачёт команды.",
        });
      } else {
        toast.success("Статус обновлён");
      }
      await loadTask();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось обновить статус");
    } finally {
      setAdvancing(false);
    }
  };

  const handlePeerReview = async () => {
    if (!task || !note.trim()) {
      toast.error("Напиши, что не так в коде стажёра");
      return;
    }
    setSubmitting(true);
    try {
      const result = await submitPeerReview(task.task_id, note.trim());
      if (result.close_quality === "weak") {
        toast.message("Эмма закрыла ревью как слабое", { description: result.emma });
      } else {
        toast.success(result.emma);
      }
      setNote("");
      await loadTask();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось отдать заметку");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    if (codeLocked) {
      toast.error(
        pending
          ? "Предыдущая сдача ещё на проверке"
          : "Лимит попыток исчерпан или задача недоступна для сдачи",
      );
      return;
    }
    if (!task || !code.trim()) {
      toast.error("Сначала напишите код");
      return;
    }
    if (task.status !== "in_progress" && task.status !== "review") {
      toast.error("Сначала переведите задачу в работу или на ревью");
      return;
    }
    setSubmitting(true);
    try {
      const submissionId = await submitCode(task.task_id, code);
      if (task.status === "in_progress") {
        try {
          await updateTaskStatus(task.task_id, "review");
        } catch (err) {
          toast.error(err instanceof Error ? err.message : "Сдача ушла, статус на ревью не сменился");
        }
      }
      toast.info(isRevision ? "Правки ушли на повторное ревью" : "Отправлено команде", {
        description: isRevision
          ? "Команда сверит, что закрыто из прошлого фидбека."
          : "Эмма разберёт решение в фоне. Можно не ждать на этой странице.",
        duration: 8000,
      });
      startBackgroundReviewPoll(submissionId, task.task_id, task.title);
      await loadTask();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось отправить решение");
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit =
    Boolean(task) &&
    !codeLocked &&
    (task?.status === "in_progress" || task?.status === "review") &&
    code.trim().length > 0;

  const advanceLabel = peerReview
    ? null
    : task?.status === "todo"
      ? "Взять в работу"
      : task?.status === "in_progress"
        ? "Отдать на ревью"
        : canClose
          ? closeDecision.allowed && closeDecision.quality === "weak"
            ? "Закрыть как слабую"
            : "Закрыть задачу"
          : null;

  const submitLabel = submitting
    ? "Отправляем…"
    : pending
      ? "На проверке…"
      : isRevision
        ? `Отправить правки (${nextAttempt}/${maxRounds})`
        : attempt >= maxRounds
          ? "Попытки закончились"
          : "Отправить на ревью";

  const hint = pending
    ? "Ждём ревью. Пока идёт проверка, новую сдачу отправить нельзя."
    : isRevision
      ? `Попытка ${nextAttempt} из ${maxRounds}: поправь код по замечаниям и отправь снова.`
      : attempt >= maxRounds
        ? closeDecision.allowed && closeDecision.quality === "weak"
          ? `Лимит ${maxRounds} попыток исчерпан. Можно закрыть задачу как слабую.`
          : `Лимит ${maxRounds} попыток исчерпан. Открой отчёт или спроси команду в чате.`
        : "Сначала возьми задачу в работу — потом отправка.";

  return (
    <WorkspaceShell adminRole={adminRole} userName={me?.name} fullBleed>
      <div className="flex h-full min-h-0 flex-col">
        <header className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-3">
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="size-4" />
            <span className="hidden sm:inline">Дашборд</span>
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg leading-none">
              {loading ? "Задача" : (task?.title ?? "Не найдена")}
            </h1>
          </div>
          {task && (
            <span className="rounded-md border border-border px-2 py-1 font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
              {statusCopy[task.status]}
              {task.status === "done" && task.close_quality === "weak" ? " · слабо" : ""}
              {task.status === "done" && task.close_quality === "ok" ? " · зачёт" : ""}
            </span>
          )}
          {attempt > 0 && (
            <span className="rounded-md border border-border px-2 py-1 font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
              попытка {Math.min(attempt, maxRounds)}/{maxRounds}
            </span>
          )}
          {task && (
            <button
              type="button"
              onClick={() =>
                navigate("/chat", {
                  state: { taskTitle: task.title, taskId: task.task_id },
                })
              }
              className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
            >
              <MessageCircle className="size-4" />
              <span className="hidden sm:inline">Чат</span>
            </button>
          )}
        </header>

        {loading && (
          <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Собираем workspace…
          </div>
        )}

        {!loading && !task && (
          <EmptyState
            title="Задачи нет на доске"
            body="Этот id не в текущем спринте. Возьми задачу с сегодняшнего экрана."
            action={
              <PrimaryButton className="w-auto" onClick={() => navigate("/dashboard")}>
                На дашборд
              </PrimaryButton>
            }
          />
        )}

        {!loading && task && lock && (
          <EmptyState
            kicker="Пока закрыта"
            title={lock.reason}
            body={lock.why}
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {lock.openTask && (
                  <PrimaryButton
                    className="w-auto min-w-[200px]"
                    onClick={() => navigate(`/task/${lock.openTask!.task_id}`)}
                  >
                    {lock.openLabel}
                  </PrimaryButton>
                )}
                <button
                  type="button"
                  onClick={() => navigate("/dashboard")}
                  className="h-12 rounded-[10px] border border-border px-4 text-sm text-muted-foreground hover:border-primary/50 hover:text-foreground"
                >
                  На дашборд
                </button>
              </div>
            }
          />
        )}

        {!loading && task && !locked && (
          <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(280px,380px)_1fr]">
            <aside className="flex min-h-0 flex-col overflow-y-auto border-b border-border p-5 lg:border-r lg:border-b-0">
              <p className="font-mono text-[11px] text-primary">
                {rights.shortBrief && brief && brief.prose.length < task.description.trim().length
                  ? "Короткий бриф"
                  : "Бриф"}
              </p>
              {isNightIncident(task.title) && (
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  Пока в «к выполнению» — спринт можно закрыть без неё. Если взял в работу, сначала закрой. Полный зачёт даёт 15 000 ₽ в письме, слабое закрытие премию не даёт.
                </p>
              )}
              <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                {brief?.prose || "Джон не расписывает план — условие в названии и критериях."}
              </p>
              {(brief?.criteria.length ?? 0) > 0 && (
                <div className="mt-6">
                  <p className="font-mono text-[11px] text-muted-foreground">Критерии приёмки</p>
                  <ul className="mt-3 space-y-2">
                    {brief!.criteria.map((item) => (
                      <li key={item} className="text-sm leading-relaxed text-foreground/90">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {career &&
                !peerReview &&
                task.status !== "done" &&
                (career.bonus > 0 || extraRound || criteriaOpen || emmaReady) && (
                <div className="mt-6 rounded-[10px] border border-border p-4">
                  <p className="font-mono text-[11px] text-muted-foreground">Премия</p>
                  <p className="mt-2 text-sm">{formatRub(career.bonus)}</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    Непотраченное сгорит в письме следующего спринта.
                  </p>
                  <div className="mt-4 space-y-2">
                    <SpendRow
                      label={extraRound ? "Лишний раунд уже на этой задаче" : "Лишний раунд ревью"}
                      price={SPEND_PRICE.extra_round}
                      disabled={
                        extraRound || buying !== null || career.bonus < SPEND_PRICE.extra_round
                      }
                      busy={buying === "extra_round"}
                      onBuy={() => void handleBuy("extra_round")}
                    />
                    <SpendRow
                      label={
                        emmaReady
                          ? "Сессия Эммы ждёт в чате"
                          : "Сессия Эммы"
                      }
                      price={SPEND_PRICE.emma_session}
                      disabled={
                        emmaReady || buying !== null || career.bonus < SPEND_PRICE.emma_session
                      }
                      busy={buying === "emma_session"}
                      onBuy={() => void handleBuy("emma_session")}
                    />
                    {!rights.criteriaBeforeSubmit && (
                      <SpendRow
                        label={criteriaOpen ? "Критерии уже открыты" : "Критерии до сдачи"}
                        price={SPEND_PRICE.early_criteria}
                        disabled={
                          criteriaOpen ||
                          submissions.length > 0 ||
                          buying !== null ||
                          career.bonus < SPEND_PRICE.early_criteria
                        }
                        busy={buying === "early_criteria"}
                        onBuy={() => void handleBuy("early_criteria")}
                      />
                    )}
                  </div>
                  {emmaReady && (
                    <button
                      type="button"
                      onClick={() =>
                        navigate("/chat", {
                          state: {
                            taskTitle: task.title,
                            taskId: task.task_id,
                            emmaBriefing:
                              failingNote || "Последнее ревью без отдельного упавшего теста.",
                          },
                        })
                      }
                      className="mt-4 text-sm text-primary hover:underline"
                    >
                      Позвать Эмму на один ход
                    </button>
                  )}
                </div>
              )}

              {advanceLabel && (
                <button
                  type="button"
                  disabled={advancing}
                  onClick={() => void handleAdvance()}
                  className={
                    canClose && closeDecision.allowed && closeDecision.quality === "weak"
                      ? "mt-6 inline-flex items-center gap-1 self-start text-sm text-muted-foreground hover:text-foreground"
                      : "mt-6 inline-flex items-center gap-1 self-start text-sm text-foreground hover:text-primary"
                  }
                >
                  {advancing ? <Loader2 className="size-4 animate-spin" /> : advanceLabel}
                  {!advancing && <ChevronRight className="size-4" />}
                </button>
              )}
              {task.status === "review" && !canClose && (
                <p className="mt-3 max-w-sm text-xs leading-relaxed text-muted-foreground">
                  {closeDecision.reason}
                </p>
              )}
              {task.status === "done" && task.close_quality === "weak" && (
                <p className="mt-3 max-w-sm text-xs leading-relaxed text-warning">
                  Закрыта как слабая — команда не зачла на полный балл.
                </p>
              )}
              {task.status === "done" && task.close_quality === "ok" && (
                <p className="mt-3 max-w-sm text-xs leading-relaxed text-muted-foreground">
                  Закрыта по зачёту команды.
                </p>
              )}

              <div className="mt-8 rounded-[10px] border border-border bg-card p-4">
                <p className="font-mono text-[11px] text-muted-foreground">
                  Ревью команды
                </p>
                {!latest && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    Ещё не отправляли. Можно сдать до {maxRounds} раз: сначала проверка, потом правки.
                  </p>
                )}
                {latest && pending && (
                  <div className="mt-3">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="size-1.5 animate-pulse rounded-full bg-primary" />
                      <p className="text-sm font-medium">
                        {attempt > 1 ? "Повторное ревью…" : "Эмма смотрит код…"}
                      </p>
                    </div>
                    <p className="text-xs leading-relaxed text-muted-foreground">
                      Проверка в фоне. Можно уйти на дашборд — пришлём, когда будет готово.
                    </p>
                  </div>
                )}
                {latest?.status === "failed" && !reviewReady && (
                  <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2">
                    <p className="text-sm font-medium text-destructive">
                      Проверка не удалась
                    </p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Можно закрыть задачу как слабую (если попытки исчерпаны) или спросить команду
                      и отправить решение ещё раз.
                    </p>
                  </div>
                )}
                {reviewReady && latest?.review && (
                  <div className="mt-3">
                    <p className="text-3xl font-medium tracking-tight">
                      {scoreOutOfTen(latest.review.score)}
                      <span className="text-base text-muted-foreground"> / 10</span>
                    </p>
                    <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
                      {latest.review.feedback}
                    </p>
                    {(latest.review.criteria?.length ?? 0) > 0 && (
                      <ul className="mt-3 space-y-1.5">
                        {latest.review.criteria!.slice(0, 4).map((item) => (
                          <li key={item.id} className="flex gap-2 text-xs leading-snug">
                            <span
                              className={
                                item.passed
                                  ? "shrink-0 text-success"
                                  : "shrink-0 text-destructive"
                              }
                            >
                              {item.passed ? "✓" : "✗"}
                            </span>
                            {marksFresh && item.line ? (
                              <button
                                type="button"
                                onClick={() => {
                                  setComparing(false);
                                  setFocusLine(item.line ?? null);
                                }}
                                className="line-clamp-2 text-left text-muted-foreground hover:text-foreground"
                                title={`Строка ${item.line}`}
                              >
                                {item.text}
                                <span className="ml-1 font-mono text-[10px] text-primary">
                                  :{item.line}
                                </span>
                              </button>
                            ) : (
                              <span className="line-clamp-2 text-muted-foreground">{item.text}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                    {(latest.review.challenges?.length ?? 0) > 0 && (
                      <div className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2">
                        <p className="font-mono text-[11px] text-muted-foreground">
                          Независимая проверка
                        </p>
                        <ul className="mt-1.5 space-y-1">
                          {latest.review.challenges!.slice(0, 2).map((item, index) => (
                            <li key={`${item.text}-${index}`} className="text-xs leading-snug text-muted-foreground">
                              ✗ {item.text}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => navigate(`/report/${latest.submission_id}`)}
                      className="mt-3 text-sm text-primary hover:underline"
                    >
                      Открыть полный отчёт
                    </button>
                    {revisionAllowed && (
                      <p className="mt-3 text-xs text-muted-foreground">
                        Можно доработать и отправить ещё раз ({nextAttempt}/{maxRounds}).
                      </p>
                    )}
                    {task.status === "review" && !closeDecision.allowed && closeDecision.code === "revise" && (
                      <p className="mt-3 text-xs text-muted-foreground">
                        Закрыть задачу можно после балла 8 или когда закончатся попытки.
                      </p>
                    )}
                  </div>
                )}
                {submissions.length > 1 && (
                  <div className="mt-4 border-t border-border pt-3">
                    <p className="font-mono text-[11px] text-muted-foreground">
                      История сдач
                    </p>
                    <ul className="mt-2 space-y-1.5">
                      {submissions.map((sub, index) => (
                        <li key={sub.submission_id} className="flex items-center justify-between gap-2 text-xs">
                          <span className="text-muted-foreground">
                            Попытка {submissions.length - index}
                            {sub.review
                              ? ` · ${scoreOutOfTen(sub.review.score)}/10`
                              : sub.status === "failed"
                                ? " · сбой"
                                : sub.status === "pending"
                                  ? " · в работе"
                                  : ""}
                          </span>
                          {sub.review && (
                            <button
                              type="button"
                              onClick={() => navigate(`/report/${sub.submission_id}`)}
                              className="text-primary hover:underline"
                            >
                              отчёт
                            </button>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </aside>

            <section className="flex min-h-[46vh] flex-col bg-[#0B0D12] lg:min-h-0">
              {peerReview ? (
                <div className="flex flex-1 flex-col gap-4 p-5">
                  <p className="font-mono text-[11px] text-primary">Заметка Эмме</p>
                  {task.status === "done" ? (
                    <p className="max-w-xl text-sm leading-relaxed text-[#F4F1EA]">
                      {task.close_note
                        || (task.close_quality === "ok"
                          ? "Эмма приняла заметку."
                          : "Эмма не засчитала эту дыру.")}
                    </p>
                  ) : (
                    <>
                      <textarea
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        rows={6}
                        placeholder="Что не так — без патча"
                        className="w-full flex-1 rounded-[10px] border border-white/10 bg-transparent px-4 py-3 text-sm leading-relaxed text-[#F4F1EA] outline-none placeholder:text-white/30 focus:border-primary"
                      />
                      <PrimaryButton
                        className="w-auto min-w-[200px]"
                        disabled={submitting || !note.trim()}
                        onClick={() => void handlePeerReview()}
                      >
                        {submitting ? "Эмма читает…" : "Отдать Эмме"}
                      </PrimaryButton>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <CodeEditor
                    value={code}
                    onChange={(next) => {
                      setCode(next);
                      setComparing(false);
                    }}
                    language={language}
                    onLanguageChange={setLanguage}
                    readOnly={codeLocked}
                    marks={marks}
                    compareWith={comparing ? previousCode : null}
                    focusLine={focusLine}
                  />
                  {(marks.length > 0 || previousCode) && (
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border px-4 py-2 text-xs text-muted-foreground">
                      {marks.length > 0 && (
                        <span>
                          {marks.length} замечани
                          {marks.length === 1 ? "е" : marks.length < 5 ? "я" : "й"} в коде
                          {unanchored > 0 ? ` · ещё ${unanchored} без строки, в отчёте` : ""}
                        </span>
                      )}
                      {previousCode && (
                        <button
                          type="button"
                          onClick={() => setComparing((value) => !value)}
                          className="text-primary hover:underline"
                        >
                          {comparing ? "Вернуться к коду" : "Сравнить с прошлой попыткой"}
                        </button>
                      )}
                    </div>
                  )}
                  <TestRunPanel
                    run={testRun}
                    running={testsRunning}
                    available={testsAvailable}
                    error={testsError}
                    disabled={codeLocked || !code.trim()}
                    onRun={() => void handleRunTests()}
                  />
                  <div className="flex shrink-0 flex-wrap items-center gap-3 border-t border-border px-4 py-3">
                    <PrimaryButton
                      className="w-auto min-w-[200px]"
                      disabled={codeLocked || !canSubmit || submitting}
                      onClick={() => void handleSubmit()}
                    >
                      {submitting ? <Loader2 className="size-4 animate-spin" /> : null}
                      {submitLabel}
                    </PrimaryButton>
                    <p className="text-[12px] text-muted-foreground">{hint}</p>
                  </div>
                </>
              )}
            </section>
          </div>
        )}
      </div>
    </WorkspaceShell>
  );
}
