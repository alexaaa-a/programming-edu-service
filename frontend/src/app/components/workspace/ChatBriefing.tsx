import { actionTitle, focusKindLabel, type UserTrajectory } from "@/lib/trajectory";

export function ChatBriefing({
  trajectory,
  taskTitle,
}: {
  trajectory: UserTrajectory;
  taskTitle?: string;
}) {
  const failed = trajectory.failed_criteria.filter(Boolean).slice(0, 4);
  const focus = trajectory.focus ?? null;
  return (
    <div className="shrink-0 border-b border-border bg-card/40 px-4 py-3 sm:px-6">
      <p className="font-mono text-[11px] text-primary">Брифинг команды</p>
      <p className="mt-1 text-sm font-medium">{actionTitle(trajectory.action)}</p>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{trajectory.reason}</p>
      <p className="mt-1 text-[11px] text-muted-foreground">
        {taskTitle ? `Задача: ${taskTitle}` : null}
        {taskTitle && trajectory.current_score != null ? " · " : null}
        {trajectory.current_score != null ? `Балл ${trajectory.current_score}/10` : null}
        {trajectory.current_attempts > 0 ? ` · попытка ${trajectory.current_attempts}` : null}
      </p>
      {focus ? (
        <div className="mt-2.5 rounded-lg border border-border/70 bg-background/40 px-3 py-2">
          <p className="text-[11px]">
            <span className="text-primary">{focusKindLabel(focus.kind)}:</span>{" "}
            <span className="font-medium">{focus.title}</span>
          </p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{focus.steps[0]}</p>
        </div>
      ) : null}
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
