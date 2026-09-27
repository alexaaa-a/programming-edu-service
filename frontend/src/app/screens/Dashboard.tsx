import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowRight, Check } from "lucide-react";
import { toast } from "sonner";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { PrimaryButton } from "../components/onboarding/Field";
import { EmptyState } from "../components/EmptyState";
import { ConfettiBurst } from "../components/ConfettiBurst";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { TEAM } from "@/lib/team";
import { readStreak, shouldCelebrate, streakDaysLabel, touchStreak } from "@/lib/streak";
import {
  apiFetch,
  acceptCareerLetter,
  completeSprint,
  submitFridayDemo,
  getBoard,
  getCareer,
  getMyAdminRole,
  getMe,
  getMyTrajectory,
  getTemplateForStart,
  SprintHoldError,
  startProject,
  updateProfile,
} from "@/lib/api";
import type { AdminRole, BoardResponse, Career, Sprint, TaskResponse, UserShow, UserTrajectory } from "@/lib/types";
import {
  GRADE_LABEL as gradeLabel,
  careerRights,
  formatRub,
  presentTask,
  isNightIncident,
  taskIsOpen,
} from "@/lib/career-rights";
import { actionCta, actionTitle } from "@/lib/trajectory";
import { TrajectoryMeters } from "../components/workspace/TrajectoryMeters";
import { cn } from "../components/ui/utils";

function pickCurrentTask(board: BoardResponse): TaskResponse | null {
  const firstReal = (arr: TaskResponse[]) => arr.find((task) => !isNightIncident(task.title)) ?? null;
  return (
    firstReal(board.in_progress) ??
    firstReal(board.review) ??
    firstReal(board.todo) ??
    board.in_progress[0] ??
    board.review[0] ??
    board.todo[0] ??
    null
  );
}

function allDone(board: BoardResponse): boolean {
  const open = [...board.todo, ...board.in_progress, ...board.review].filter(
    (task) => !(isNightIncident(task.title) && task.status === "todo"),
  );
  const done = board.done.filter((task) => !isNightIncident(task.title));
  return open.length === 0 && done.length > 0;
}

function flattenBoard(board: BoardResponse): TaskResponse[] {
  return [...board.done, ...board.in_progress, ...board.review, ...board.todo];
}

const columnMeta = [
  { key: "todo" as const, label: "К выполнению" },
  { key: "in_progress" as const, label: "В работе" },
  { key: "review" as const, label: "Ревью" },
  { key: "done" as const, label: "Готово" },
];

const directionLabel: Record<string, string> = {
  backend: "Backend",
  frontend: "Frontend",
  fullstack: "Fullstack",
};

const levelLabel: Record<string, string> = {
  junior: "Junior",
  "junior-plus": "Junior+",
};

export default function Dashboard() {
  useRequireAuth();
  const navigate = useNavigate();
  const [me, setMe] = useState<UserShow | null>(null);
  const [sprint, setSprint] = useState<Sprint | null>(null);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);
  const [pitch, setPitch] = useState("");
  const [demoAnswer, setDemoAnswer] = useState("");
  const [forceArmed, setForceArmed] = useState(false);
  const [serverHold, setServerHold] = useState(false);
  const [serverHoldReason, setServerHoldReason] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState(false);
  const [streak, setStreak] = useState(readStreak);
  const [trajectory, setTrajectory] = useState<UserTrajectory | null>(null);
  const [career, setCareer] = useState<Career | null>(null);
  const [needsProject, setNeedsProject] = useState(false);
  const [starting, setStarting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setNeedsProject(false);
    try {
      const profile = await getMe();
      if (!profile.direction || !profile.level) {
        navigate("/direction", { replace: true });
        return;
      }
      setMe(profile);
      try {
        setCareer(await getCareer());
      } catch {
        setCareer(null);
      }
      const role = await getMyAdminRole();
      setAdminRole(role.role);

      let sp: Sprint | null = null;
      const sprintRes = await apiFetch("/api/task/v1/sprint/current");
      if (sprintRes.ok) {
        sp = (await sprintRes.json()) as Sprint;
      } else if (sprintRes.status === 404) {
        setSprint(null);
        setBoard(null);
        setTrajectory(null);
        setForceArmed(false);
        setNeedsProject(true);
        return;
      } else {
        throw new Error(await sprintRes.text());
      }
      setNeedsProject(false);
      setSprint(sp);

      const b = await getBoard();
      setBoard(b);
      setForceArmed(false);
      const focus = pickCurrentTask(b) ?? b.done[b.done.length - 1] ?? null;
      try {
        setTrajectory(await getMyTrajectory(focus?.task_id));
      } catch {
        setTrajectory(null);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось загрузить дашборд");
      setSprint(null);
      setBoard(null);
      setTrajectory(null);
      setForceArmed(false);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  const startNewProject = async (direction?: string) => {
    setStarting(true);
    try {
      if (direction) {
        await updateProfile({ direction });
      }
      const tpl = await getTemplateForStart();
      await startProject(tpl.template_id);
      toast.success("Проект запущен");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось начать проект");
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    setStreak(touchStreak());
  }, []);

  useEffect(() => {
    if (loading || !board) return;
    const id = window.location.hash.replace("#", "");
    if (!id) return;
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [loading, board]);

  const current = board ? pickCurrentTask(board) : null;
  const firstName = me?.name ?? "друг";

  const counts = useMemo(() => {
    if (!board) return { total: 0, done: 0, weak: 0 };
    const total =
      board.todo.length + board.in_progress.length + board.review.length + board.done.length;
    const weak = board.done.filter((task) => task.close_quality === "weak").length;
    return { total, done: board.done.length, weak };
  }, [board]);

  const dayInSprint = sprint?.started_at
    ? Math.max(
        1,
        Math.floor((Date.now() - new Date(sprint.started_at).getTime()) / 86400000) + 1,
      )
    : 1;

  const pathTasks = board ? flattenBoard(board) : [];
  const sprintHold = Boolean(board) && allDone(board!) && serverHold;
  const holdReason =
    serverHoldReason ||
    trajectory?.reason ||
    "Траектория ещё тяжёлая — рано открывать следующий спринт.";

  const rights = careerRights(career?.grade, career?.appeal_used);
  const isAdmin = adminRole === "admin" || adminRole === "superadmin";
  const canForceSprint = isAdmin || rights.appeal;
  const choosingFirst =
    Boolean(board) &&
    rights.pickFirstTask &&
    board!.in_progress.length === 0 &&
    board!.review.length === 0 &&
    board!.todo.length > 1;
  const pendingLetter = career?.pending_letter ?? null;
  const pendingDemo = career?.pending_demo ?? null;

  const handleSubmitDemo = async () => {
    setCompleting(true);
    try {
      await submitFridayDemo(pitch, demoAnswer);
      setPitch("");
      setDemoAnswer("");
      toast.success("Демо сдано. Письмо на столе.");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось сдать демо");
    } finally {
      setCompleting(false);
    }
  };

  const handleAcceptLetter = async () => {
    setCompleting(true);
    try {
      await acceptCareerLetter();
      toast.success("Условия приняты");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось принять письмо");
    } finally {
      setCompleting(false);
    }
  };

  const handleCompleteSprint = async (force = false) => {
    if (!board || !allDone(board)) return;
    if (force && !canForceSprint) return;
    if (force && sprintHold && !forceArmed) {
      setForceArmed(true);
      return;
    }
    setCompleting(true);
    try {
      const step = await completeSprint(force);
      setServerHold(false);
      setServerHoldReason(null);
      setForceArmed(false);
      if (step === "letter" || step === "demo") {
        await load();
        return;
      }
      if (force || sprintHold) {
        toast.message("Следующий спринт открыт принудительно", {
          description: "Слабые узлы остаются в траектории — это не полный зачёт.",
        });
      } else {
        toast.success("Спринт закрыт. Дальше — новый.");
        if (sprint && shouldCelebrate(`sprint:${sprint.sprint_id}:done`)) {
          setCelebrate(true);
        }
      }
      await load();
    } catch (e) {
      if (e instanceof SprintHoldError) {
        setServerHold(true);
        setServerHoldReason(e.message || null);
        setForceArmed(Boolean(e.forceAllowed && canForceSprint));
        toast.message(e.message || "Спринт пока на hold", {
          description: e.forceAllowed && canForceSprint
            ? "Можно открыть следующий осознанно — это не полный зачёт."
            : "Пока остаёмся на hold — спроси команду или дождись наставника.",
        });
        return;
      }
      toast.error(e instanceof Error ? e.message : "Не удалось завершить спринт");
    } finally {
      setCompleting(false);
    }
  };

  return (
    <WorkspaceShell adminRole={adminRole} userName={me?.name}>
      <ConfettiBurst fire={celebrate} />
      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 lg:py-10">
        <header className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[11px] text-primary">
              {me?.direction ? directionLabel[me.direction] ?? me.direction : "Desk"}
              {me?.level ? ` · ${levelLabel[me.level] ?? me.level}` : ""}
            </p>
            <h1 className="mt-2 text-4xl leading-[1.1] sm:text-5xl">
              Привет, {firstName}
            </h1>
          </div>
          <div className="flex items-center gap-4">
            {career && (
              <div className="text-right">
                <p className="font-mono text-[11px] text-primary">{gradeLabel[career.grade]}</p>
                <p className="font-display mt-0.5 text-2xl leading-none">{formatRub(career.salary)}</p>
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                  опцион {formatRub(career.equity)}
                </p>
                {career.bonus > 0 && (
                  <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                    премия {formatRub(career.bonus)} · сгорит в письме
                  </p>
                )}
              </div>
            )}
            <button
              type="button"
              onClick={() => navigate("/statistics")}
              className="text-right"
            >
              <p className="font-mono text-[11px] text-muted-foreground">
                За столом
              </p>
              <p className="mt-0.5 text-sm font-medium">
                {streak.count} {streakDaysLabel(streak.count)} подряд
              </p>
            </button>
            <div className="flex items-center gap-2">
              {TEAM.map((member) => (
                <div
                  key={member.name}
                  title={`${member.name} · ${member.role}`}
                  className="flex size-8 items-center justify-center rounded-full text-[11px] font-medium text-[#1c140e]"
                  style={{ background: member.accent }}
                >
                  {member.name.charAt(0)}
                </div>
              ))}
            </div>
          </div>
        </header>

        {pendingDemo && !pendingLetter && (
          <section className="mb-10 rounded-[10px] border border-primary/30 bg-card p-7 sm:p-9">
            <p className="font-mono text-[11px] text-primary">Пятница</p>
            <h2 className="mt-3 text-3xl">Демо для Сары</h2>
            <p className="mt-4 max-w-xl text-sm leading-relaxed">{pendingDemo.sara_line}</p>
            <label className="mt-6 block text-sm text-muted-foreground" htmlFor="friday-pitch">
              Питч, 2–4 предложения
            </label>
            <textarea
              id="friday-pitch"
              value={pitch}
              onChange={(event) => setPitch(event.target.value)}
              rows={4}
              className="mt-2 w-full rounded-[10px] border border-border bg-background px-4 py-3 text-sm leading-relaxed outline-none focus:border-primary"
            />
            <p className="mt-6 max-w-xl text-sm leading-relaxed">{pendingDemo.question}</p>
            <label className="mt-4 block text-sm text-muted-foreground" htmlFor="friday-answer">
              Ответ
            </label>
            <textarea
              id="friday-answer"
              value={demoAnswer}
              onChange={(event) => setDemoAnswer(event.target.value)}
              rows={3}
              className="mt-2 w-full rounded-[10px] border border-border bg-background px-4 py-3 text-sm leading-relaxed outline-none focus:border-primary"
            />
            <p className="mt-4 max-w-xl text-sm text-muted-foreground">
              Тонкий питч режет только премию. Грейд считается по закрытиям задач.
            </p>
            <PrimaryButton
              className="mt-6 w-auto min-w-[200px]"
              disabled={completing || !pitch.trim() || !demoAnswer.trim()}
              onClick={() => void handleSubmitDemo()}
            >
              {completing ? "Сдаём…" : "Сдать демо"}
            </PrimaryButton>
          </section>
        )}

        {pendingLetter && (
          <section className="mb-10 rounded-[10px] border border-primary/30 bg-card p-7 sm:p-9">
            <p className="font-mono text-[11px] text-primary">Performance review</p>
            <h2 className="mt-3 text-3xl">Письмо Джона</h2>
            <p className="mt-2 font-mono text-[12px] text-muted-foreground">
              {new Date(pendingLetter.at).toLocaleDateString("ru-RU", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </p>
            <p className="font-display mt-6 text-3xl leading-none">
              {formatRub(pendingLetter.old_salary)}
              <span className="mx-3 text-muted-foreground">→</span>
              {formatRub(pendingLetter.new_salary)}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              {gradeLabel[pendingLetter.old_grade]} → {gradeLabel[pendingLetter.new_grade]}
              {pendingLetter.bonus_paid > 0 ? ` · премия ${formatRub(pendingLetter.bonus_paid)}` : " · премии нет"}
            </p>
            <ul className="mt-6 space-y-2">
              {pendingLetter.facts.map((fact) => (
                <li key={fact} className="text-sm leading-relaxed text-foreground/90">
                  {fact}
                </li>
              ))}
            </ul>
            <p className="mt-6 max-w-xl text-sm leading-relaxed text-muted-foreground">{pendingLetter.text}</p>
            <PrimaryButton
              className="mt-8 w-auto min-w-[220px]"
              disabled={completing}
              onClick={() => void handleAcceptLetter()}
            >
              {completing ? "Открываем…" : "Принять условия"}
            </PrimaryButton>
          </section>
        )}

        {loading && (
          <p className="py-24 text-center text-sm text-muted-foreground">Собираем спринт…</p>
        )}

        {!loading && needsProject && (
          <EmptyState
            kicker="Проект"
            title="Нет активного спринта"
            body={
              rights.chooseDirection
                ? "Оффер: направление следующего проекта выбираешь сам."
                : "Можно начать новый учебный проект с командой Desk — или отдохнуть, если прошлый уже закрыт."
            }
            action={
              rights.chooseDirection ? (
                <div className="flex flex-wrap gap-2">
                  {(
                    [
                      ["backend", "Backend"],
                      ["frontend", "Frontend"],
                      ["fullstack", "Fullstack"],
                    ] as const
                  ).map(([id, label]) => (
                    <PrimaryButton
                      key={id}
                      className="w-auto min-w-[140px]"
                      disabled={starting}
                      onClick={() => void startNewProject(id)}
                    >
                      {starting ? "Запускаем…" : label}
                    </PrimaryButton>
                  ))}
                </div>
              ) : (
                <PrimaryButton
                  className="w-auto min-w-[180px]"
                  disabled={starting}
                  onClick={() => void startNewProject()}
                >
                  {starting ? "Запускаем…" : "Начать проект"}
                </PrimaryButton>
              )
            }
          />
        )}

        {!loading && !needsProject && !board && (
          <EmptyState
            kicker="Дашборд"
            title="Спринт не собрался"
            body="Сеть или шаблон. Обнови страницу — или зайди ещё раз после онбординга."
            action={
              <PrimaryButton className="w-auto min-w-[160px]" onClick={() => void load()}>
                Повторить
              </PrimaryButton>
            }
          />
        )}

        {!loading && board && (
          <>
            <section className="overflow-hidden rounded-[10px] border border-border bg-card">
              <div className="grid lg:grid-cols-[1.4fr_0.8fr]">
                <div className="p-7 sm:p-9">
                  <p className="font-mono text-[11px] text-primary">
                    Сегодня
                  </p>
                  {choosingFirst ? (
                    <>
                      <h2 className="mt-4 max-w-xl text-2xl font-medium tracking-tight sm:text-3xl">
                        Какую задачу берёшь первой?
                      </h2>
                      <p className="mt-4 max-w-xl text-sm text-muted-foreground">
                        На Junior+ доска не диктует порядок, пока ни одна задача не в работе.
                      </p>
                      <ul className="mt-6 space-y-2">
                        {board!.todo.map((task) => (
                          <li key={task.task_id}>
                            <button
                              type="button"
                              onClick={() => navigate(`/task/${task.task_id}`)}
                              className="w-full rounded-[10px] border border-border px-4 py-3 text-left text-sm hover:border-primary/50"
                            >
                              {task.title}
                              {isNightIncident(task.title) ? " · необязательно" : ""}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : current ? (
                    <>
                      <h2 className="mt-4 max-w-xl text-2xl font-medium tracking-tight sm:text-3xl">
                        {trajectory ? actionTitle(trajectory.action) : current.title}
                      </h2>
                      <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground">
                        {trajectory?.reason ??
                          presentTask(current.description, career?.grade, false).prose}
                      </p>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Задача: {current.title}
                        {current.status === "in_progress"
                          ? " · в работе"
                          : current.status === "review"
                            ? " · на ревью"
                            : " · к выполнению"}
                      </p>
                      <div className="mt-8 flex flex-wrap items-center gap-3">
                        <PrimaryButton
                          className="w-auto min-w-[180px]"
                          onClick={() =>
                            trajectory?.action === "chat"
                              ? navigate("/chat", {
                                  state: { taskTitle: current.title, taskId: current.task_id },
                                })
                              : navigate(`/task/${current.task_id}`)
                          }
                        >
                          {trajectory ? actionCta(trajectory.action) : "Открыть задачу"}
                          <ArrowRight className="size-4" />
                        </PrimaryButton>
                      </div>
                    </>
                  ) : allDone(board) ? (
                    sprintHold ? (
                      <>
                        <h2 className="mt-4 text-2xl font-medium tracking-tight sm:text-3xl">
                          {actionTitle("hold_sprint")}
                        </h2>
                        <p className="mt-4 max-w-xl text-sm text-muted-foreground">
                          {holdReason}
                        </p>
                        {forceArmed && canForceSprint && (
                          <p className="mt-3 max-w-xl text-xs leading-relaxed text-amber-400">
                            {rights.appeal && !isAdmin
                              ? "Одна апелляция за спринт. Оклад от неё не растёт: удержание просто пропускается."
                              : "Это не зачёт. Следующий спринт откроется со слабыми узлами в траектории."}
                          </p>
                        )}
                        <div className="mt-8 flex flex-wrap items-center gap-3">
                          <PrimaryButton
                            className="w-auto min-w-[200px]"
                            onClick={() => navigate("/chat")}
                          >
                            Спросить команду
                            <ArrowRight className="size-4" />
                          </PrimaryButton>
                          {canForceSprint &&
                            (forceArmed ? (
                              <>
                                <button
                                  type="button"
                                  disabled={completing}
                                  onClick={() => void handleCompleteSprint(true)}
                                  className="h-12 px-4 text-sm text-amber-300 hover:text-amber-200 disabled:opacity-40"
                                >
                                  {completing
                                    ? "Открываем…"
                                    : rights.appeal && !isAdmin
                                      ? "Потратить апелляцию"
                                      : "Открыть всё равно"}
                                </button>
                                <button
                                  type="button"
                                  disabled={completing}
                                  onClick={() => setForceArmed(false)}
                                  className="h-12 px-4 text-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
                                >
                                  Отмена
                                </button>
                              </>
                            ) : (
                              <button
                                type="button"
                                disabled={completing}
                                onClick={() => setForceArmed(true)}
                                className="h-12 px-4 text-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
                              >
                                {rights.appeal && !isAdmin
                                  ? "Оспорить удержание"
                                  : "Всё равно открыть следующий"}
                              </button>
                            ))}
                        </div>
                      </>
                    ) : (
                      <>
                        <h2 className="mt-4 text-2xl font-medium tracking-tight sm:text-3xl">
                          {trajectory &&
                          trajectory.action !== "hold_sprint" &&
                          trajectory.action !== "close_weak"
                            ? actionTitle(trajectory.action)
                            : "Спринт закрыт по задачам"}
                        </h2>
                        <p className="mt-4 max-w-xl text-sm text-muted-foreground">
                          {trajectory?.action === "hold_sprint"
                            ? "Задачи закрыты. Завершай спринт — письмо отметит тонкую траекторию, оклад от этого не режется."
                            : (trajectory?.reason ??
                              "Команда может выдохнуть. Зафиксируй спринт, чтобы взять следующий.")}
                        </p>
                        {pendingLetter ? (
                          <p className="mt-6 text-sm text-muted-foreground">
                            Письмо уже на столе. Следующий спринт откроется после «Принять условия».
                          </p>
                        ) : pendingDemo ? (
                          <p className="mt-6 text-sm text-muted-foreground">
                            Сначала пятничное демо. Письмо придёт после питча.
                          </p>
                        ) : (
                          <PrimaryButton
                            className="mt-8 w-auto min-w-[200px]"
                            disabled={completing}
                            onClick={() => void handleCompleteSprint()}
                          >
                            {completing ? "Закрываем…" : "Завершить спринт"}
                          </PrimaryButton>
                        )}
                      </>
                    )
                  ) : (
                    <h2 className="mt-4 text-2xl font-medium">На доске пока пусто</h2>
                  )}
                </div>
                <aside className="border-t border-border p-7 sm:p-9 lg:border-t-0 lg:border-l">
                  <dl className="space-y-5">
                    <div>
                      <dt className="font-mono text-[11px] text-muted-foreground">
                        Спринт
                      </dt>
                      <dd className="mt-1 text-lg font-medium">
                        {sprint ? `№ ${sprint.order}` : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="font-mono text-[11px] text-muted-foreground">
                        Закрыто
                      </dt>
                      <dd className="mt-1 text-lg font-medium">
                        {counts.done}
                        <span className="text-muted-foreground"> / {counts.total}</span>
                        {counts.weak > 0 && (
                          <span className="ml-2 font-mono text-[11px] text-amber-400">
                            {counts.weak} слабо
                          </span>
                        )}
                      </dd>
                      <div className="mt-3 h-1 overflow-hidden rounded-full bg-foreground/10">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{
                            width: `${counts.total ? Math.round((counts.done / counts.total) * 100) : 0}%`,
                          }}
                        />
                      </div>
                    </div>
                    {trajectory ? (
                      <TrajectoryMeters trajectory={trajectory} />
                    ) : (
                      <div>
                        <dt className="font-mono text-[11px] text-muted-foreground">
                          День в спринте
                        </dt>
                        <dd className="mt-1 text-lg font-medium">{dayInSprint}</dd>
                      </div>
                    )}
                  </dl>
                </aside>
              </div>
            </section>

            <section id="path" className="mt-12 scroll-mt-8">
              <div className="mb-5 flex items-end justify-between gap-4">
                <div>
                  <h2 className="text-lg font-medium tracking-tight">Путь спринта</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Мята — зачёт, янтарь — слабое закрытие.
                  </p>
                </div>
              </div>
              <div className="flex gap-0 overflow-x-auto pb-2">
                {pathTasks.length === 0 && (
                  <p className="py-8 text-sm text-muted-foreground">
                    Узлов пока нет — доска пустая.
                  </p>
                )}
                {pathTasks.map((task, i) => {
                  const done = task.status === "done";
                  const weak = done && task.close_quality === "weak";
                  const now = current?.task_id === task.task_id;
                  const open = taskIsOpen(task, board, rights.pickFirstTask);
                  return (
                    <div key={task.task_id} className="flex min-w-0 items-center">
                      {i > 0 && (
                        <div
                          className={cn(
                            "h-px w-8 shrink-0 sm:w-12",
                            weak ? "bg-amber-400/60" : done || now ? "bg-primary/50" : "bg-foreground/10",
                          )}
                        />
                      )}
                      <button
                        type="button"
                        disabled={!open}
                        onClick={() => open && navigate(`/task/${task.task_id}`)}
                        className="flex min-w-[88px] flex-col items-center gap-2 disabled:cursor-default"
                      >
                        <span
                          className={cn(
                            "flex size-10 items-center justify-center rounded-full border text-xs font-medium transition-colors",
                            weak && "border-amber-400 bg-amber-400/15 text-amber-300",
                            done && !weak && "border-primary bg-primary text-primary-foreground",
                            now && !done && "border-primary bg-primary/15 text-primary",
                            !done && !now && "border-border text-muted-foreground",
                          )}
                        >
                          {done ? <Check className="size-4" /> : i + 1}
                        </span>
                        <span className="line-clamp-2 max-w-[100px] text-center text-[11px] leading-snug text-muted-foreground">
                          {task.title}
                        </span>
                      </button>
                    </div>
                  );
                })}
              </div>
            </section>

            <section id="board" className="mt-14 scroll-mt-8">
              <div className="mb-5">
                <h2 className="text-3xl">Доска</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Как в команде: не список уроков, а канбан спринта.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {columnMeta.map((col) => (
                  <div
                    key={col.key}
                    className="min-h-[220px] rounded-[10px] border border-border bg-card/60 p-3"
                  >
                    <div className="mb-3 flex items-baseline justify-between px-1">
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {col.label}
                      </p>
                      <span className="text-[11px] text-muted-foreground">
                        {board[col.key].length}
                      </span>
                    </div>
                    <ul className="space-y-2">
                      {board[col.key].length === 0 && (
                        <li className="px-1 py-8 text-center text-[12px] text-muted-foreground">
                          Пусто
                        </li>
                      )}
                      {board[col.key].map((t) => {
                        const isNow = current?.task_id === t.task_id;
                        const open = taskIsOpen(t, board, rights.pickFirstTask);
                        const preview = presentTask(t.description, career?.grade, false).prose;
                        return (
                          <li key={t.task_id}>
                            <button
                              type="button"
                              disabled={!open}
                              onClick={() => open && navigate(`/task/${t.task_id}`)}
                              className={cn(
                                "w-full rounded-xl border px-3 py-3 text-left transition-colors disabled:cursor-default disabled:opacity-60",
                                isNow
                                  ? "border-primary/60 bg-primary/10"
                                  : "border-transparent bg-foreground/[0.03] hover:border-border",
                              )}
                            >
                              <p className="text-sm font-medium leading-snug">
                                {t.title}
                                {isNightIncident(t.title) && col.key === "todo" ? " · необязательно" : ""}
                              </p>
                              <p className="mt-1 line-clamp-2 text-[12px] text-muted-foreground">
                                {open ? preview : "По очереди — сначала текущая задача"}
                              </p>
                              {t.close_quality === "weak" && (
                                <p className="mt-2 font-mono text-[11px] text-amber-300">
                                  слабо
                                </p>
                              )}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </section>

            <section className="mt-14 mb-8">
              <div className="mb-5 flex items-end justify-between">
                <div>
                  <h2 className="text-lg font-medium tracking-tight">Команда</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Сара, Майк, Эмма и Джон — на связи в чате.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate("/chat")}
                  className="text-sm text-primary hover:underline"
                >
                  Открыть чат
                </button>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {TEAM.map((member) => (
                  <button
                    key={member.name}
                    type="button"
                    onClick={() => navigate("/chat")}
                    className="flex items-center gap-3 rounded-[10px] border border-border bg-card px-4 py-4 text-left transition-colors hover:border-foreground/15"
                  >
                    <span
                      className="flex size-10 shrink-0 items-center justify-center rounded-full text-sm font-medium text-[#1c140e]"
                      style={{ background: member.accent }}
                    >
                      {member.name.charAt(0)}
                    </span>
                    <span>
                      <span className="block text-sm font-medium">{member.name}</span>
                      <span className="block text-[12px] text-muted-foreground">
                        {member.role} · {member.presence}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </WorkspaceShell>
  );
}
