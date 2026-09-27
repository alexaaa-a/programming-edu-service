import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { getMe, getMyAdminRole, getMyTrajectory, getSubmission, getTaskSubmissions } from "@/lib/api";
import { startBackgroundReviewPoll } from "@/lib/background-review";
import { countedRounds, MAX_ROUNDS } from "@/lib/close-gate";
import type { AdminRole, Submission, UserTrajectory } from "@/lib/types";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { MarkdownBody } from "../components/MarkdownBody";
import { PrimaryButton } from "../components/onboarding/Field";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { ConfettiBurst } from "../components/ConfettiBurst";
import { scoreOutOfTen, scorePercent } from "@/lib/score";
import { shouldCelebrate } from "@/lib/streak";
import { actionCta, actionTitle } from "@/lib/trajectory";
import { TrajectoryFocus } from "../components/workspace/TrajectoryFocus";

function ScoreRing({ value }: { value: number }) {
  const pct = scorePercent(value);
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  return (
    <div className="relative mx-auto size-36">
      <svg className="size-36 -rotate-90" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} fill="none" stroke="rgba(246,241,232,0.08)" strokeWidth="3" />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          stroke="#e4b48a"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 700ms cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-5xl leading-none">{scoreOutOfTen(value)}</span>
        <span className="text-[11px] text-muted-foreground">из 10</span>
      </div>
    </div>
  );
}

function nextStepCopy(
  score: number,
  canRevise: boolean,
): { title: string; body: string } {
  const n = scoreOutOfTen(score);
  if (n >= 8) {
    return {
      title: "Можно закрывать задачу",
      body: "Команда довольна. Зафиксируй статус «Готово» и бери следующий узел пути.",
    };
  }
  if (canRevise) {
    if (n >= 5) {
      return {
        title: "Доработай и пришли снова",
        body: "База есть, но ревью просит правок. Вернись в workspace, исправь замечания и отправь вторую попытку.",
      };
    }
    return {
      title: "Исправь и сдай повторно",
      body: "Скор низкий. Разбери бриф и замечания, поправь код и отправь ещё раз — команда сверит прогресс.",
    };
  }
  if (n >= 5) {
    return {
      title: "Лимит попыток исчерпан",
      body: "Правки уже были. Открой чат с командой или закрой задачу и перейди к следующей.",
    };
  }
  return {
    title: "Лимит попыток исчерпан",
    body: "Две сдачи уже использованы. Спроси Эмму или Джона в чате и возьми следующий узел пути.",
  };
}

export default function SprintReport() {
  useRequireAuth();
  const { submissionId } = useParams<{ submissionId: string }>();
  const navigate = useNavigate();
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [attemptCount, setAttemptCount] = useState<number | null>(0);
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState<string | undefined>();
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [celebrate, setCelebrate] = useState(false);
  const [trajectory, setTrajectory] = useState<UserTrajectory | null>(null);

  const idNum = submissionId ? Number(submissionId) : NaN;

  useEffect(() => {
    void (async () => {
      try {
        const [me, role] = await Promise.all([getMe(), getMyAdminRole()]);
        setUserName(me.name);
        setAdminRole(role.role);
      } catch {
        /* ignore */
      }
    })();
  }, []);

  useEffect(() => {
    if (Number.isNaN(idNum)) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const sub = await getSubmission(idNum);
        if (!cancelled) {
          setSubmission(sub);
          try {
            const all = await getTaskSubmissions(sub.task_id);
            setAttemptCount(countedRounds(all));
          } catch {
            setAttemptCount(null);
          }
          try {
            setTrajectory(await getMyTrajectory(sub.task_id));
          } catch {
            setTrajectory(null);
          }
          const passed = sub.review && scoreOutOfTen(sub.review.score) >= 8;
          if (passed) {
            setCelebrate(shouldCelebrate(`report:${sub.submission_id}`));
          }
        }
      } catch (e) {
        if (!cancelled) {
          toast.error(e instanceof Error ? e.message : "Не удалось загрузить отчёт");
          setSubmission(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [idNum]);

  useEffect(() => {
    if (!submission || submission.review) return;
    if (submission.status !== "pending") return;
    startBackgroundReviewPoll(submission.submission_id, submission.task_id);
    const handler = (e: Event) => {
      const d = (e as CustomEvent<{ submissionId: number }>).detail;
      if (d?.submissionId !== submission.submission_id) return;
      void getSubmission(submission.submission_id)
        .then(async (sub) => {
          setSubmission(sub);
          try {
            setTrajectory(await getMyTrajectory(sub.task_id));
          } catch {
            /* keep previous trajectory CTA */
          }
        })
        .catch(() => {
          /* keep pending UI */
        });
    };
    window.addEventListener("submission-review-ready", handler);
    return () => window.removeEventListener("submission-review-ready", handler);
  }, [submission]);

  const review = submission?.review;
  const canRevise =
    review != null &&
    (attemptCount == null || attemptCount < MAX_ROUNDS) &&
    scoreOutOfTen(review.score) < 8;
  const fallback = review ? nextStepCopy(review.score, canRevise) : null;
  const next = trajectory
    ? { title: actionTitle(trajectory.action), body: trajectory.reason }
    : fallback;

  const goPrimary = () => {
    if (!submission) return;
    if (trajectory?.action === "chat") {
      navigate("/chat", {
        state: { taskId: submission.task_id, draft: trajectory.focus?.ask },
      });
      return;
    }
    if (trajectory?.action === "next_sprint" || trajectory?.action === "hold_sprint") {
      navigate("/dashboard");
      return;
    }
    navigate(`/task/${submission.task_id}`);
  };

  const primaryLabel = trajectory
    ? actionCta(trajectory.action)
    : canRevise
      ? "Исправить и сдать снова"
      : "К задаче";

  return (
    <WorkspaceShell adminRole={adminRole} userName={userName}>
      <ConfettiBurst fire={celebrate} />
      <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8 lg:py-10">
        <p className="font-mono text-[11px] text-primary">Ревью команды</p>
        <h1 className="mt-3 text-4xl leading-[1.1] sm:text-5xl">Отчёт по решению</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Разбор решения от команды: что сработало, что поправить и что делать дальше.
        </p>

        {loading && <LoadingState label="Собираем отчёт…" />}

        {!loading && !submission && (
          <EmptyState
            title="Отчёт не найден"
            body="Ссылка устарела или ревью ещё не создано. Вернись к задаче с доски."
            action={
              <PrimaryButton className="w-auto" onClick={() => navigate("/dashboard")}>
                На дашборд
              </PrimaryButton>
            }
          />
        )}

        {!loading && submission && !review && submission.status === "failed" && (
          <div className="mt-10 rounded-[10px] border border-destructive/30 bg-destructive/10 p-8">
            <p className="text-sm font-medium text-destructive">
              Проверка не удалась
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              {submission.reviewed_at
                ? "Команда не смогла завершить ревью. Можно вернуться к задаче и отправить решение ещё раз — эта попытка уже учтена."
                : "Технический сбой при проверке. Можно вернуться к задаче и отправить решение ещё раз — эта попытка не сжигает лимит."}
            </p>
            <button
              type="button"
              onClick={() => navigate(`/task/${submission.task_id}`)}
              className="mt-6 text-sm text-primary hover:underline"
            >
              Открыть workspace
            </button>
          </div>
        )}

        {!loading && submission && !review && submission.status !== "failed" && (
          <div className="mt-10 rounded-[10px] border border-border bg-card p-8">
            <div className="mb-3 flex items-center gap-2">
              <span className="size-1.5 animate-pulse rounded-full bg-primary" />
              <p className="text-sm font-medium">Эмма ещё смотрит код</p>
            </div>
            <p className="text-sm text-muted-foreground">
              Страница обновится, когда ревью доедет. Можно вернуться к задаче.
            </p>
            <button
              type="button"
              onClick={() => navigate(`/task/${submission.task_id}`)}
              className="mt-6 text-sm text-primary hover:underline"
            >
              Открыть workspace
            </button>
          </div>
        )}

        {!loading && review && (
          <>
            <section className="mt-10 grid gap-4 sm:grid-cols-[auto_1fr] sm:items-center rounded-[10px] border border-border bg-card p-8">
              <ScoreRing value={review.score} />
              <div>
                <p className="font-mono text-[11px] text-muted-foreground">
                  Следующий шаг
                </p>
                <h2 className="mt-2 text-xl font-medium tracking-tight">{next?.title}</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{next?.body}</p>
              </div>
            </section>

            {trajectory && (
              <TrajectoryFocus
                className="mt-4"
                trajectory={trajectory}
                chatTask={submission ? { taskId: submission.task_id } : null}
                showMeters
              />
            )}

            <section className="mt-8">
              <h2 className="mb-3 text-sm font-medium">Обратная связь</h2>
              <div className="rounded-[10px] border border-border bg-card p-6">
                <MarkdownBody text={review.feedback} />
              </div>
            </section>

            {(review.criteria?.length ?? 0) > 0 && (
              <section className="mt-8">
                <h2 className="mb-3 text-sm font-medium">Критерии приёмки</h2>
                <ul className="space-y-2">
                  {review.criteria!.map((item) => (
                    <li
                      key={item.id}
                      className="flex gap-3 rounded-xl border border-border bg-card px-4 py-3"
                    >
                      <span
                        className={
                          item.passed
                            ? "mt-0.5 shrink-0 font-mono text-sm text-success"
                            : "mt-0.5 shrink-0 font-mono text-sm text-destructive"
                        }
                        aria-hidden
                      >
                        {item.passed ? "✓" : "✗"}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm leading-relaxed">{item.text}</p>
                        {item.note ? (
                          <p className="mt-1 text-xs text-muted-foreground">{item.note}</p>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {(review.challenges?.length ?? 0) > 0 && (
              <section className="mt-8">
                <h2 className="mb-3 text-sm font-medium">Независимая проверка</h2>
                <ul className="space-y-2">
                  {review.challenges!.map((item, index) => (
                    <li
                      key={`${item.text}-${index}`}
                      className="flex gap-3 rounded-xl border border-border bg-card px-4 py-3"
                    >
                      <span className="mt-0.5 shrink-0 font-mono text-sm text-warning" aria-hidden>
                        ✗
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm leading-relaxed">{item.text}</p>
                        {item.severity ? (
                          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                            {item.severity === "high"
                              ? "серьёзно"
                              : item.severity === "low"
                                ? "мягко"
                                : "средне"}
                          </p>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {(review.agent_path?.length ?? 0) > 0 && (
              <section className="mt-8">
                <h2 className="mb-3 text-sm font-medium">Путь проверки</h2>
                <ol className="space-y-2">
                  {review.agent_path!.map((step, index) => (
                    <li
                      key={`${step.name}-${index}`}
                      className="flex gap-3 rounded-xl border border-border bg-card px-4 py-3"
                    >
                      <span className="mt-0.5 shrink-0 font-mono text-xs text-muted-foreground">
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm leading-relaxed">
                          <span
                            className={
                              step.status === "ok"
                                ? "text-success"
                                : step.status === "error"
                                  ? "text-destructive"
                                  : "text-warning"
                            }
                          >
                            {step.status === "ok" ? "✓" : step.status === "error" ? "✗" : "!"}
                          </span>{" "}
                          {step.name}
                        </p>
                        {step.detail ? (
                          <p className="mt-1 text-xs text-muted-foreground">{step.detail}</p>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            )}

            {review.suggestions.length > 0 && (
              <section className="mt-8">
                <h2 className="mb-3 text-sm font-medium">Что поправить</h2>
                <ul className="space-y-2">
                  {review.suggestions.map((s, i) => (
                    <li key={i} className="rounded-xl border border-border bg-card px-4 py-3">
                      <MarkdownBody text={s} />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <div className="mt-10 flex flex-wrap gap-3">
              <PrimaryButton
                type="button"
                className="w-auto min-w-[180px]"
                onClick={goPrimary}
              >
                {primaryLabel}
                <ArrowRight className="size-4" />
              </PrimaryButton>
              <button
                type="button"
                onClick={() => navigate("/dashboard")}
                className="h-12 px-4 text-sm text-muted-foreground hover:text-foreground"
              >
                На дашборд
              </button>
              <button
                type="button"
                onClick={() =>
                  navigate("/chat", {
                    state: { taskId: submission!.task_id },
                  })
                }
                className="h-12 px-4 text-sm text-muted-foreground hover:text-foreground"
              >
                Спросить команду
              </button>
            </div>
          </>
        )}
      </div>
    </WorkspaceShell>
  );
}
