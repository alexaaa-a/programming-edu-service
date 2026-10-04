import { Check, Loader2, Play, X } from "lucide-react";
import type { TaskTestRun } from "@/lib/api";
import { cn } from "../ui/utils";

export function TestRunPanel({
  run,
  running,
  available,
  error,
  onRun,
  disabled,
}: {
  run: TaskTestRun | null;
  running: boolean;
  available: boolean;
  error: string | null;
  onRun: () => void;
  disabled?: boolean;
}) {
  if (!available) return null;

  return (
    <div className="shrink-0 border-t border-border px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onRun}
          disabled={running || disabled}
          className="inline-flex items-center gap-2 rounded-[10px] border border-border px-3.5 py-2 text-sm hover:border-primary/50 disabled:opacity-60"
        >
          {running ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
          {running ? "Гоняем тесты…" : "Запустить тесты"}
        </button>
        <Summary run={run} running={running} error={error} />
      </div>

      {run && run.failures.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {run.failures.slice(0, 6).map((item) => (
            <li key={item.name} className="flex gap-2 text-[12px] leading-snug">
              <X className="mt-0.5 size-3 shrink-0 text-warning" />
              <span className="min-w-0">
                <span className="font-mono text-foreground">{item.name}</span>
                {item.message ? (
                  <span className="text-muted-foreground"> · {item.message}</span>
                ) : null}
              </span>
            </li>
          ))}
          {run.failures.length > 6 && (
            <li className="text-[11px] text-muted-foreground">
              и ещё {run.failures.length - 6}
            </li>
          )}
        </ul>
      )}

      {run?.status === "passed" && (
        <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
          Тесты проверяют поведение, а не качество кода. Ревью всё равно смотрит на структуру,
          имена и крайние случаи, которых в тестах нет.
        </p>
      )}
    </div>
  );
}

function Summary({
  run,
  running,
  error,
}: {
  run: TaskTestRun | null;
  running: boolean;
  error: string | null;
}) {
  if (running) {
    return <p className="text-[12px] text-muted-foreground">Код ушёл в песочницу.</p>;
  }
  if (error) {
    return <p className="text-[12px] text-warning">{error}</p>;
  }
  if (!run) {
    return (
      <p className="text-[12px] text-muted-foreground">
        Проверка не тратит попытку: гоняй сколько нужно.
      </p>
    );
  }
  if (run.status === "passed") {
    return (
      <p className="inline-flex items-center gap-1.5 text-[12px] text-success">
        <Check className="size-3.5" />
        Прошли все {run.total}
      </p>
    );
  }
  if (run.status === "failed") {
    return (
      <p className={cn("text-[12px]", run.passed > 0 ? "text-warning" : "text-destructive")}>
        Прошло {run.passed} из {run.total}
      </p>
    );
  }
  if (run.status === "timeout") {
    return <p className="text-[12px] text-warning">Не уложились в лимит: код слишком медленный или зациклился.</p>;
  }
  return (
    <p className="text-[12px] text-destructive">
      {run.detail || "Код не удалось запустить"}
    </p>
  );
}
