import { actionTitle, pct01, type UserTrajectory } from "@/lib/trajectory";

export function ChatBriefing({
  trajectory,
  taskTitle,
}: {
  trajectory: UserTrajectory;
  taskTitle?: string;
}) {
  const failed = trajectory.failed_criteria.filter(Boolean).slice(0, 4);
  return (
    <div className="shrink-0 border-b border-border bg-card/40 px-4 py-3 sm:px-6">
      <p className="font-mono text-[11px] text-primary">
        Брифинг команды
      </p>
      <p className="mt-1 text-sm font-medium">{actionTitle(trajectory.action)}</p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{trajectory.reason}</p>
      {taskTitle ? (
        <p className="mt-1 text-[11px] text-muted-foreground">Задача: {taskTitle}</p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-muted-foreground">
        <span>M {pct01(trajectory.mastery)}%</span>
        <span>D {pct01(trajectory.difficulty)}%</span>
        <span>P {pct01(trajectory.pace)}%</span>
        <span>R {pct01(trajectory.readiness)}%</span>
        {trajectory.current_score != null ? <span>{trajectory.current_score}/10</span> : null}
        {trajectory.current_attempts > 0 ? (
          <span>попытка {trajectory.current_attempts}</span>
        ) : null}
      </div>
      {failed.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {failed.map((item) => (
            <span
              key={item}
              className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground"
            >
              {item}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
