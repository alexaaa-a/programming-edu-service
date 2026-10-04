import { useNavigate } from "react-router";
import { ArrowRight, MessageCircle } from "lucide-react";
import {
  focusKindLabel,
  pct01,
  recommendationLabel,
  skillStatusLabel,
  velocityLabel,
  type TrajectorySkill,
  type UserTrajectory,
} from "@/lib/trajectory";
import { cn } from "../ui/utils";

function SkillRow({ skill, active }: { skill: TrajectorySkill; active: boolean }) {
  const pct = pct01(skill.mastery);
  return (
    <li>
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <p className={cn("min-w-0 leading-snug text-[12px]", active ? "text-foreground" : "text-muted-foreground")}>
          {skill.title}
        </p>
        <p
          className={cn(
            "shrink-0 whitespace-nowrap font-mono text-[11px]",
            skill.status === "gap" || skill.status === "fading"
              ? "text-warning"
              : skill.status === "mastered"
                ? "text-success"
                : "text-muted-foreground",
          )}
        >
          {skillStatusLabel(skill.status)} · {pct}%
        </p>
      </div>
      <div className="h-px overflow-hidden rounded-full bg-foreground/10">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700 ease-out",
            skill.status === "mastered"
              ? "bg-success"
              : skill.status === "gap" || skill.status === "fading"
                ? "bg-warning"
                : "bg-primary/60",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </li>
  );
}

export function TrajectoryFocus({
  trajectory,
  taskTitles,
  chatTask,
  className,
  id,
  isTaskOpen,
}: {
  trajectory: UserTrajectory;
  taskTitles?: Record<number, string>;
  chatTask?: { taskId: number; taskTitle?: string } | null;
  className?: string;
  id?: string;
  isTaskOpen?: (taskId: number) => boolean;
}) {
  const navigate = useNavigate();
  const focus = trajectory.focus ?? null;
  const recommendations = trajectory.recommendations ?? [];
  const skills = trajectory.skills ?? [];
  const velocity = velocityLabel(trajectory.velocity);

  if (!focus && recommendations.length === 0 && skills.length === 0) {
    return null;
  }

  const askMentor = (ask: string) =>
    navigate("/chat", {
      state: chatTask ? { ...chatTask, draft: ask } : { draft: ask },
    });

  return (
    <section id={id} className={cn("rounded-[10px] border border-border bg-card", className)}>
      <div className="grid gap-0 lg:grid-cols-[1.4fr_1fr]">
        <div className="p-7 sm:p-9">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-[11px] text-primary">Фокус траектории</p>
            {focus ? (
              <span className="rounded-md border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                {focusKindLabel(focus.kind)}
              </span>
            ) : null}
          </div>

          {focus ? (
            <>
              <h3 className="mt-3 text-xl font-medium tracking-tight">{focus.title}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Владение {pct01(focus.mastery)}% · ожидаемый успех {pct01(focus.predicted_success)}%
              </p>
              <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted-foreground">{focus.why}</p>

              {focus.evidence.length > 0 ? (
                <ul className="mt-4 space-y-1">
                  {focus.evidence.map((item) => (
                    <li key={item} className="text-xs leading-relaxed text-warning">
                      ✗ {item}
                    </li>
                  ))}
                </ul>
              ) : null}

              <ol className="mt-5 space-y-2.5">
                {focus.steps.map((step, index) => (
                  <li key={step} className="flex gap-3 text-sm leading-relaxed">
                    <span className="mt-0.5 font-mono text-[11px] text-primary">{index + 1}</span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>

              <button
                type="button"
                onClick={() => askMentor(focus.ask)}
                className="mt-6 inline-flex items-center gap-2 rounded-[10px] border border-border px-4 py-2.5 text-sm hover:border-primary/50"
              >
                <MessageCircle className="size-4" />
                Спросить: {focus.mentor_name}
              </button>
              <p className="mt-2 max-w-xl text-[11px] text-muted-foreground">«{focus.ask}»</p>
            </>
          ) : null}

          {recommendations.length > 0 ? (
            <div className="mt-8">
              <p className="font-mono text-[11px] text-muted-foreground">План</p>
              <ul className="mt-3 divide-y divide-border">
                {recommendations.map((item, index) => {
                  const taskTitle = item.task_id != null ? taskTitles?.[item.task_id] : undefined;
                  return (
                    <li key={`${item.kind}-${index}`} className="py-3">
                      <div className="sm:flex sm:items-baseline sm:gap-3">
                        <span className="mb-1 block shrink-0 font-mono text-[10px] text-muted-foreground sm:mb-0 sm:w-20">
                          {recommendationLabel(item.kind)}
                        </span>
                        <div className="min-w-0">
                          <p className="text-sm">
                            {item.kind === "next_task" && taskTitle
                              ? `Следующая задача: ${taskTitle}`
                              : item.title}
                          </p>
                          {item.detail ? (
                            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{item.detail}</p>
                          ) : null}
                          {item.task_id != null &&
                          (isTaskOpen?.(item.task_id) ?? true) ? (
                            <button
                              type="button"
                              onClick={() => navigate(`/task/${item.task_id}`)}
                              className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                            >
                              Открыть задачу
                              <ArrowRight className="size-3" />
                            </button>
                          ) : null}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </div>

        {skills.length > 0 ? (
          <aside className="border-t border-border p-7 sm:p-9 lg:border-t-0 lg:border-l">
            <div className="flex items-baseline justify-between gap-3">
              <p className="font-mono text-[11px] text-muted-foreground">Карта навыков</p>
              {velocity ? <p className="font-mono text-[11px] text-primary">{velocity}</p> : null}
            </div>
            <ul className="mt-4 space-y-4">
              {skills.slice(0, 8).map((skill) => (
                <SkillRow key={skill.id} skill={skill} active={skill.id === focus?.skill_id} />
              ))}
            </ul>
            <p className="mt-5 text-[11px] leading-relaxed text-muted-foreground">
              Владение — вероятность, что навык освоен, по всем ревью с учётом забывания. Освоен — от 95%.
            </p>
          </aside>
        ) : null}
      </div>
    </section>
  );
}
