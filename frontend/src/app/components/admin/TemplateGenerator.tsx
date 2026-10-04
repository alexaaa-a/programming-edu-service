import { useState } from "react";
import { AlertTriangle, Check, Loader2, X } from "lucide-react";
import { generateTemplateSprint } from "@/lib/api";
import type {
  GeneratedSprint,
  ProjectTemplateSprint,
  TemplateTaskReport,
} from "@/lib/types";
import { Field, PrimaryButton, fieldClass, selectClass } from "../onboarding/Field";
import { cn } from "../ui/utils";

export interface TemplateDraft {
  title: string;
  description: string;
  sprints: ProjectTemplateSprint[];
}

interface Props {
  direction: string;
  level: string;
  onDraft: (draft: TemplateDraft) => void;
}

export function TemplateGenerator({ direction, level, onDraft }: Props) {
  const [topic, setTopic] = useState("");
  const [notes, setNotes] = useState("");
  const [sprints, setSprints] = useState(3);
  const [tasksPerSprint, setTasksPerSprint] = useState(4);
  const [withTests, setWithTests] = useState(true);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(0);
  const [results, setResults] = useState<GeneratedSprint[]>([]);
  const [error, setError] = useState("");

  const reports = results.flatMap((item) => item.reports);
  const kept = results.flatMap((item) => item.tasks);
  const withTestsCount = reports.filter((item) => item.tests_kept).length;

  const handleGenerate = async () => {
    if (topic.trim().length < 5) {
      setError("Опиши тему проекта хотя бы парой слов.");
      return;
    }
    setBusy(true);
    setError("");
    setResults([]);
    setDone(0);

    const collected: GeneratedSprint[] = [];
    const usedTitles: string[] = [];
    try {
      for (let order = 1; order <= sprints; order += 1) {
        const result = await generateTemplateSprint({
          topic: topic.trim(),
          direction,
          level,
          sprints,
          tasks_per_sprint: tasksPerSprint,
          notes: notes.trim(),
          with_tests: withTests,
          order,
          used_titles: usedTitles,
        });
        collected.push(result);
        result.tasks.forEach((task) => usedTitles.push(task.title));
        setResults([...collected]);
        setDone(order);
      }

      const sprintPayload: ProjectTemplateSprint[] = collected
        .filter((item) => item.tasks.length > 0)
        .map((item, index) => ({
          order: index + 1,
          title: item.sprint_title || `Спринт ${index + 1}`,
          tasks: item.tasks.map((task) => ({
            title: task.title,
            description: task.description,
            tests: task.tests ?? "",
          })),
        }));

      if (sprintPayload.length === 0) {
        setError("Ни одной задачи собрать не удалось. Попробуй другую тему.");
        return;
      }
      const first = collected[0];
      onDraft({
        title: first?.project_title || topic.trim(),
        description: first?.project_description || topic.trim(),
        sprints: sprintPayload,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Генерация не удалась");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mt-8 rounded-[10px] border border-border bg-card p-6 sm:p-8">
      <h2 className="text-lg font-medium tracking-tight">Черновик по теме</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Модель пишет задачи, сервер их проверяет: структура, число критериев и прогон
        тестов на эталонном решении. Непрошедшее не публикуется молча — оно в отчёте.
      </p>

      <div className="mt-6 space-y-4">
        <Field
          label="Тема проекта"
          value={topic}
          placeholder="Например: сервис бронирования столиков"
          onChange={(e) => setTopic(e.target.value)}
        />
        <label className="block space-y-2">
          <span className="text-xs font-medium tracking-wide text-muted-foreground">
            Заметки (необязательно)
          </span>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Что обязательно должно быть: SQLite, обработка ошибок, классы…"
            className={cn(fieldClass, "block w-full h-auto min-h-[72px] py-3")}
          />
        </label>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block space-y-2">
            <span className="text-xs font-medium tracking-wide text-muted-foreground">
              Спринтов
            </span>
            <select
              value={sprints}
              onChange={(e) => setSprints(Number(e.target.value))}
              className={selectClass}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-2">
            <span className="text-xs font-medium tracking-wide text-muted-foreground">
              Задач в спринте
            </span>
            <select
              value={tasksPerSprint}
              onChange={(e) => setTasksPerSprint(Number(e.target.value))}
              className={selectClass}
            >
              {[2, 3, 4, 5, 6].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="flex items-center gap-2.5 text-sm">
          <input
            type="checkbox"
            checked={withTests}
            onChange={(e) => setWithTests(e.target.checked)}
            className="size-4 accent-primary"
          />
          <span>
            Со скрытыми тестами
            <span className="text-muted-foreground">
              {" "}
              — дольше, зато задачу можно проверить запуском
            </span>
          </span>
        </label>

        <div className="flex flex-wrap items-center gap-3">
          <PrimaryButton
            type="button"
            className="w-auto min-w-[180px]"
            disabled={busy}
            onClick={() => void handleGenerate()}
          >
            {busy ? "Собираем…" : "Собрать черновик"}
          </PrimaryButton>
          {busy && (
            <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              спринт {Math.min(done + 1, sprints)} из {sprints}, это небыстро
            </span>
          )}
          {!busy && reports.length > 0 && (
            <span className="text-sm text-muted-foreground">
              задач {kept.length}, с тестами {withTestsCount}
            </span>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {reports.length > 0 && (
          <div className="space-y-1.5 border-t border-border pt-4">
            {reports.map((report) => (
              <TaskLine key={`${report.title}-${report.attempts}`} report={report} />
            ))}
            {results.some((item) => item.issues.length > 0) && (
              <p className="pt-2 text-sm text-destructive">
                {results.flatMap((item) => item.issues).map((issue) => issue.message).join("; ")}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function TaskLine({ report }: { report: TemplateTaskReport }) {
  const icon = report.dropped ? (
    <X className="mt-0.5 size-3.5 shrink-0 text-destructive" />
  ) : report.ok ? (
    <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
  ) : (
    <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
  );

  const note = report.dropped
    ? "снята"
    : report.tests_kept
      ? `тесты ${report.reference_passed}/${report.tests_total} на эталоне, ошибку ловят ${report.broken_failed}`
      : "без тестов";

  return (
    <div className="flex items-start gap-2 text-sm">
      {icon}
      <p className="min-w-0">
        <span className="font-medium">{report.title}</span>
        <span className="text-muted-foreground"> · {note}</span>
        {report.issues.length > 0 && (
          <span className="block text-xs text-muted-foreground">
            {report.issues.map((issue) => issue.message).join("; ")}
          </span>
        )}
      </p>
    </div>
  );
}
