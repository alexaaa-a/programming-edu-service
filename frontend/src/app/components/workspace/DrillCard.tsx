import { useEffect, useState } from "react";
import { Check, Loader2, Play, Timer, X } from "lucide-react";
import { getMyDrill, runDrill } from "@/lib/api";
import type { DrillOffer, DrillRunResult } from "@/lib/types";
import { cn } from "../ui/utils";

export function DrillCard({ className }: { className?: string }) {
  const [offer, setOffer] = useState<DrillOffer | null>(null);
  const [code, setCode] = useState("");
  const [run, setRun] = useState<DrillRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const data = await getMyDrill();
        if (!alive) return;
        setOffer(data);
        setCode(data?.starter ?? "");
      } catch {
        // разминка необязательна: молча прячем карточку
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (!offer || hidden) return null;

  const handleRun = async () => {
    setRunning(true);
    setError("");
    try {
      setRun(await runDrill(offer.drill_id, code));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Прогон не удался");
    } finally {
      setRunning(false);
    }
  };

  const done = run?.status === "passed";

  return (
    <section
      className={cn("rounded-[10px] border border-border bg-card p-6 sm:p-7", className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] text-primary">
            {offer.kind === "review" ? "Разминка" : "Добор"}
          </p>
          <h2 className="mt-2 text-lg font-medium tracking-tight">{offer.title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{offer.reason}</p>
        </div>
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-border px-3 py-1 font-mono text-[11px] text-muted-foreground">
          <Timer className="size-3" />
          {offer.minutes} мин
        </span>
      </div>

      <pre className="mt-5 whitespace-pre-wrap font-sans text-sm leading-relaxed text-foreground/90">
        {offer.prompt.trim()}
      </pre>

      <textarea
        value={code}
        onChange={(e) => setCode(e.target.value)}
        spellCheck={false}
        className="mt-4 block h-auto min-h-[180px] w-full rounded-[10px] border border-foreground/15 bg-[#1c1916] px-4 py-3 font-mono text-[13px] leading-relaxed text-foreground outline-none focus:border-primary/80 focus:ring-2 focus:ring-primary/25"
      />

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void handleRun()}
          disabled={running || !code.trim()}
          className="inline-flex items-center gap-2 rounded-[10px] border border-border px-3.5 py-2 text-sm hover:border-primary/50 disabled:opacity-60"
        >
          {running ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
          {running ? "Проверяем…" : "Проверить"}
        </button>
        <Summary run={run} running={running} error={error} skill={offer.skill_title} />
        {done && (
          <button
            type="button"
            onClick={() => setHidden(true)}
            className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            Скрыть
          </button>
        )}
      </div>

      {run && run.failures.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {run.failures.slice(0, 5).map((item) => (
            <li key={item.name} className="flex gap-2 text-[12px] leading-snug">
              <X className="mt-0.5 size-3 shrink-0 text-warning" />
              <span className="min-w-0">
                <span className="font-mono text-foreground">{item.name}</span>
                {item.message ? <span className="text-muted-foreground"> · {item.message}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Summary({
  run,
  running,
  error,
  skill,
}: {
  run: DrillRunResult | null;
  running: boolean;
  error: string;
  skill: string;
}) {
  if (running) return <span className="text-sm text-muted-foreground">Гоняем тесты…</span>;
  if (error) return <span className="text-sm text-destructive">{error}</span>;
  if (!run) {
    return (
      <span className="text-sm text-muted-foreground">
        Решение проверяется тестами — оценку за это не ставят.
      </span>
    );
  }
  if (run.status === "passed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-primary">
        <Check className="size-4" />
        Готово{run.recorded ? ` — «${skill}» освежён` : ""}
      </span>
    );
  }
  if (run.status === "timeout") {
    return (
      <span className="text-sm text-warning">
        Не уложилось в лимит времени — похоже, решение слишком медленное.
      </span>
    );
  }
  if (run.status === "error") {
    return <span className="text-sm text-warning">{run.detail || "Код не запустился"}</span>;
  }
  return (
    <span className="text-sm text-muted-foreground">
      Прошло {run.passed} из {run.total}
    </span>
  );
}
