import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { getMe, getMyAdminRole, getMySubmissionStats, getMyTrajectory } from "@/lib/api";
import type { AdminRole, UserSubmissionStats, UserTrajectory } from "@/lib/types";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { TrajectoryMeters } from "../components/workspace/TrajectoryMeters";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { PrimaryButton } from "../components/onboarding/Field";
import { scoreOutOfTen } from "@/lib/score";
import { readStreak, streakDaysLabel, touchStreak } from "@/lib/streak";

function ratio(part: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((part / total) * 100)));
}

function Bar({ value, label, count }: { value: number; label: string; count: number }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span>{label}</span>
        <span className="font-mono text-[12px] text-muted-foreground">
          {count} · {value}%
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-foreground/10">
        <div className="h-full rounded-full bg-primary" style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export default function Statistics() {
  useRequireAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<UserSubmissionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState<string | undefined>();
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [streak, setStreak] = useState(readStreak);
  const [trajectory, setTrajectory] = useState<UserTrajectory | null>(null);

  useEffect(() => {
    setStreak(touchStreak());
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [data, me, role] = await Promise.all([
          getMySubmissionStats(),
          getMe(),
          getMyAdminRole(),
        ]);
        setStats(data);
        setUserName(me.name);
        setAdminRole(role.role);
        try {
          setTrajectory(await getMyTrajectory());
        } catch {
          setTrajectory(null);
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Не удалось загрузить статистику");
        setStats(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const reviewedPct = useMemo(
    () => ratio(stats?.reviewed_submissions ?? 0, stats?.total_submissions ?? 0),
    [stats],
  );
  const pendingPct = useMemo(
    () => ratio(stats?.pending_submissions ?? 0, stats?.total_submissions ?? 0),
    [stats],
  );
  const failedPct = useMemo(
    () => ratio(stats?.failed_submissions ?? 0, stats?.total_submissions ?? 0),
    [stats],
  );

  const avg = stats?.average_score == null ? null : scoreOutOfTen(stats.average_score);
  const best = stats?.best_score == null ? null : scoreOutOfTen(stats.best_score);
  const emptyCycle = (stats?.total_submissions ?? 0) === 0;

  const focus = emptyCycle
    ? "Первая отправка запустит цикл. Не копи отправки без ревью."
    : (stats?.pending_submissions ?? 0) > 0
      ? "Дождись ревью по открытым отправкам — не копить очередь."
      : avg != null && avg < 7
        ? "Средний скор просит больше итераций: читай отчёт до следующей задачи."
        : "Держи ритм: одна задача — одно ревью — один следующий шаг.";

  return (
    <WorkspaceShell adminRole={adminRole} userName={userName}>
      <div className="mx-auto max-w-4xl px-5 py-8 sm:px-8 lg:py-10">
        <p className="font-mono text-[11px] text-primary">Прогресс</p>
        <h1 className="mt-3 text-4xl leading-[1.1]">Как ты растёшь</h1>
        <p className="mt-2 max-w-lg text-sm text-muted-foreground">
          Один цикл: написал → получил ревью → поправил. Смотрим, как часто ты его замыкаешь.
        </p>

        {loading && <LoadingState label="Считаем метрики…" />}

        {!loading && !stats && (
          <EmptyState
            title="Статистика недоступна"
            body="Сервис отправок не ответил. Попробуй ещё раз с дашборда."
            action={
              <PrimaryButton className="w-auto" onClick={() => navigate("/dashboard")}>
                На дашборд
              </PrimaryButton>
            }
          />
        )}

        {!loading && stats && (
          <>
            <div className="mt-10 grid grid-cols-2 gap-3 lg:grid-cols-5">
              {[
                {
                  label: "Стрик",
                  value: `${streak.count} ${streakDaysLabel(streak.count)}`,
                },
                { label: "Рекорд", value: String(streak.longest) },
                { label: "Отправок", value: String(stats.total_submissions) },
                { label: "Средний скор", value: avg == null ? "—" : `${avg}/10` },
                { label: "Лучший", value: best == null ? "—" : `${best}/10` },
              ].map((card) => (
                <div key={card.label} className="rounded-[10px] border border-border bg-card p-5">
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {card.label}
                  </p>
                  <p className="mt-2 text-2xl font-medium tracking-tight">{card.value}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[12px] text-muted-foreground">
              Стрик — дни подряд, когда ты открывал Desk. Просто счётчик привычки, без штрафов за пропуск.
            </p>

            {emptyCycle ? (
              <div className="mt-6">
                <EmptyState
                  kicker="Цикл"
                  title="Ещё нет отправок"
                  body="Открой задачу, напиши решение, получи ревью. Здесь появится, закрываешь ли ты круг."
                  action={
                    <PrimaryButton className="w-auto" onClick={() => navigate("/dashboard")}>
                      К сегодняшней задаче
                    </PrimaryButton>
                  }
                />
              </div>
            ) : (
              <section className="mt-6 rounded-[10px] border border-border bg-card p-6 sm:p-8">
                <h2 className="text-sm font-medium">Цикл проверки</h2>
                <div className="mt-6 space-y-5">
                  <Bar label="Проверено" value={reviewedPct} count={stats.reviewed_submissions} />
                  <Bar label="Ждёт команду" value={pendingPct} count={stats.pending_submissions} />
                  <Bar label="Сбой проверки" value={failedPct} count={stats.failed_submissions} />
                </div>
              </section>
            )}

            {trajectory && (
              <section className="mt-6 rounded-[10px] border border-border bg-card p-6 sm:p-8">
                <h2 className="text-sm font-medium">Модель траектории</h2>
                <p className="mt-2 max-w-xl text-[12px] leading-relaxed text-muted-foreground">
                  Четыре числа, по которым траектория решает, что предложить дальше. На дашборде
                  их нет намеренно: там нужен следующий шаг, а не приборная панель.
                </p>
                <TrajectoryMeters className="mt-6" trajectory={trajectory} />
                <dl className="mt-6 space-y-2 text-[12px] leading-relaxed text-muted-foreground">
                  <div>
                    <dt className="inline font-medium text-foreground">Мастерство. </dt>
                    <dd className="inline">Средняя вероятность, что навык освоен, по всем встреченным навыкам.</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium text-foreground">Трудность. </dt>
                    <dd className="inline">Насколько текущая задача выше твоего уровня: 1 минус ожидаемый успех.</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium text-foreground">Темп. </dt>
                    <dd className="inline">Как часто ты замыкаешь круг «сдал — получил ревью — поправил».</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium text-foreground">Готовность. </dt>
                    <dd className="inline">
                      Ожидаемая доля критериев, которые пройдут в задачах спринта. Порог для
                      следующего спринта — 72%.
                    </dd>
                  </div>
                </dl>
              </section>
            )}

            <section className="mt-6 rounded-[10px] border border-border bg-card p-6 sm:p-8">
              <p className="font-mono text-[11px] text-muted-foreground">
                Сегодня фокус
              </p>
              <p className="mt-3 max-w-xl text-lg font-medium tracking-tight">{focus}</p>
            </section>
          </>
        )}
      </div>
    </WorkspaceShell>
  );
}
