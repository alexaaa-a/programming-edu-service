import { Lock } from "lucide-react";
import type { Career, CareerGrade } from "@/lib/types";
import { BadgeGlyph } from "../BadgeGlyph";
import { cn } from "../ui/utils";

const GRADE_LADDER: { id: CareerGrade; label: string }[] = [
  { id: "intern", label: "Стажёр" },
  { id: "junior", label: "Джуниор" },
  { id: "junior_plus", label: "Джуниор+" },
  { id: "strong", label: "Сильный джун" },
  { id: "offer", label: "Оффер" },
];

function Ladder({ grade }: { grade: CareerGrade }) {
  const current = Math.max(
    GRADE_LADDER.findIndex((step) => step.id === grade),
    0,
  );
  return (
    <ol className="mt-4 flex items-center gap-1.5">
      {GRADE_LADDER.map((step, index) => (
        <li key={step.id} className="flex-1" title={step.label}>
          <div
            className={cn(
              "h-1 rounded-full transition-colors",
              index < current
                ? "bg-primary/45"
                : index === current
                  ? "bg-primary"
                  : "bg-foreground/10",
            )}
          />
          <p
            className={cn(
              "mt-2 truncate font-mono text-[10px]",
              index === current ? "text-primary" : "text-muted-foreground",
            )}
          >
            {step.label}
          </p>
        </li>
      ))}
    </ol>
  );
}

function QuestRow({
  title,
  hint,
  current,
  target,
  left,
}: {
  title: string;
  hint: string;
  current: number;
  target: number;
  left: number;
}) {
  const pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
  return (
    <li className="py-3">
      <div className="flex items-baseline justify-between gap-3">
        <p className="min-w-0 text-sm leading-snug">{title}</p>
        <p className="shrink-0 whitespace-nowrap font-mono text-[11px] text-muted-foreground">
          {target > 1 ? `${current}/${target}` : left === 0 ? "готово" : "осталось 1"}
        </p>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{hint}</p>
      {target > 1 ? (
        <div className="mt-2 h-px overflow-hidden rounded-full bg-foreground/10">
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      ) : null}
    </li>
  );
}

export function CareerQuests({
  career,
  className,
}: {
  career: Career;
  className?: string;
}) {
  const progress = career.progress;
  const badges = career.badges ?? [];
  const quests = career.quests ?? [];
  const nextUp = quests.slice(0, 3);
  const total = career.badge_total ?? badges.length;
  const earned = new Set(badges.map((badge) => badge.id));

  if (!progress && badges.length === 0 && quests.length === 0) {
    return null;
  }

  const streak = progress?.streak_ok ?? 0;
  const best = progress?.best_streak ?? 0;

  return (
    <section className={cn("rounded-[10px] border border-border bg-card", className)}>
      <div className="grid lg:grid-cols-[1fr_1fr]">
        <div className="p-7 sm:p-9">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-mono text-[11px] text-primary">Путь в команде</p>
            <p className="font-mono text-[11px] text-muted-foreground">
              {badges.length} из {total}
            </p>
          </div>
          <Ladder grade={career.grade} />

          {progress ? (
            <dl className="mt-7 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
              <div>
                <dt className="font-mono text-[11px] text-muted-foreground">Серия зачётов</dt>
                <dd className="mt-1 text-lg font-medium">
                  {streak}
                  {best > streak ? (
                    <span className="ml-2 font-mono text-[11px] text-muted-foreground">
                      рекорд {best}
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="font-mono text-[11px] text-muted-foreground">Зачтено задач</dt>
                <dd className="mt-1 text-lg font-medium">
                  {progress.closes_ok}
                  {progress.closes_weak > 0 ? (
                    <span className="ml-2 font-mono text-[11px] text-warning">
                      {progress.closes_weak} слабо
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt className="font-mono text-[11px] text-muted-foreground">Спринтов закрыто</dt>
                <dd className="mt-1 text-lg font-medium">{progress.sprints}</dd>
              </div>
            </dl>
          ) : null}

          {nextUp.length > 0 ? (
            <div className="mt-7">
              <p className="font-mono text-[11px] text-muted-foreground">Ближайшие цели</p>
              <ul className="mt-1 divide-y divide-border">
                {nextUp.map((quest) => (
                  <QuestRow
                    key={quest.id}
                    title={quest.title}
                    hint={quest.hint}
                    current={quest.current}
                    target={quest.target}
                    left={quest.left}
                  />
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-7 text-sm text-muted-foreground">
              Все бейджи собраны. Дальше только грейд и оффер.
            </p>
          )}
        </div>

        <aside className="border-t border-border p-7 sm:p-9 lg:border-t-0 lg:border-l">
          <p className="font-mono text-[11px] text-muted-foreground">Полка бейджей</p>
          <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {badges.map((badge) => (
              <li
                key={badge.id}
                title={`${badge.hint} · ${new Date(badge.at).toLocaleDateString("ru-RU")}`}
                className="rounded-[10px] border border-primary/30 bg-primary/5 p-3 motion-safe:animate-[badge-pop_420ms_var(--ease-out)]"
              >
                <BadgeGlyph id={badge.id} className="size-4 text-primary" />
                <p className="mt-2 text-[12px] leading-snug">{badge.title}</p>
              </li>
            ))}
            {quests.map((quest) =>
              earned.has(quest.id) ? null : (
                <li
                  key={quest.id}
                  title={quest.hint}
                  className="rounded-[10px] border border-dashed border-border p-3"
                >
                  <Lock className="size-4 text-muted-foreground" aria-hidden="true" />
                  <p className="mt-2 text-[12px] leading-snug text-muted-foreground">
                    {quest.title}
                  </p>
                </li>
              ),
            )}
          </ul>
          {badges.length === 0 ? (
            <p className="mt-5 text-[11px] leading-relaxed text-muted-foreground">
              Полка пустая: первый бейдж приходит с первой закрытой задачей.
              Считается только зачёт на доске, не время в редакторе.
            </p>
          ) : (
            <p className="mt-5 text-[11px] leading-relaxed text-muted-foreground">
              Бейдж выдаётся один раз и остаётся в профиле. Наведи курсор, чтобы
              увидеть, за что он.
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}
