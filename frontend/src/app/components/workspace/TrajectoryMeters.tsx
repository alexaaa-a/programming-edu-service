import { pct01, type UserTrajectory } from "@/lib/trajectory";
import { cn } from "../ui/utils";

function Meter({
  label,
  value,
  invert,
}: {
  label: string;
  value: number;
  invert?: boolean;
}) {
  const pct = pct01(value);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <p className="text-[12px] text-muted-foreground">
          {label}
        </p>
        <p className="font-mono text-[11px] text-muted-foreground">{pct}%</p>
      </div>
      <div className="h-px overflow-hidden rounded-full bg-foreground/10">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700 ease-out",
            invert
              ? pct >= 50
                ? "bg-warning"
                : "bg-primary/70"
              : "bg-primary",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function TrajectoryMeters({
  trajectory,
  className,
}: {
  trajectory: UserTrajectory;
  className?: string;
}) {
  return (
    <div className={cn("space-y-4", className)}>
      <Meter label="Мастерство" value={trajectory.mastery} />
      <Meter label="Трудность" value={trajectory.difficulty} invert />
      <Meter label="Темп" value={trajectory.pace} />
      <Meter label="Готовность" value={trajectory.readiness} />
    </div>
  );
}
