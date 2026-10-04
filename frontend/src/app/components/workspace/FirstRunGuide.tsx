import { ArrowRight, Check } from "lucide-react";
import { cn } from "../ui/utils";

const KEY = "desk_firstrun_v1";

const STEPS: { title: string; body: string }[] = [
  {
    title: "Берёшь задачу",
    body: "Доска ведёт по одной: пока задача в работе или на ревью, следующая закрыта. Порядок задач — это программа спринта.",
  },
  {
    title: "Пишешь код в браузере",
    body: "Редактор на странице задачи. Бриф и критерии приёмки — слева, по ним и будут проверять.",
  },
  {
    title: "Сдаёшь и получаешь ревью",
    body: "Команда разбирает код по критериям и ставит балл. Обычно это занимает минуту. На задачу есть две сдачи.",
  },
  {
    title: "Правишь по замечаниям",
    body: "В отчёте видно, какие критерии не прошли. Непонятно почему — спроси в чате, отвечает тот, чья это зона.",
  },
  {
    title: "Закрываешь задачу",
    body: "С баллом 8 и выше это зачёт, ниже — слабое закрытие. Слабое не блокирует спринт, но видно в письме.",
  },
  {
    title: "В пятницу — демо и письмо",
    body: "Когда задачи спринта закрыты: питч для Сары, потом письмо от Джона с грейдом и премией.",
  },
];

export function wasFirstRunSeen(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function markFirstRunSeen(): void {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    /* приватный режим: покажем ещё раз, это не страшно */
  }
}

export function FirstRunGuide({
  onDismiss,
  className,
}: {
  onDismiss: () => void;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-[10px] border border-primary/30 bg-card p-7 sm:p-9",
        className,
      )}
    >
      <p className="font-mono text-[11px] text-primary">Как это работает</p>
      <h2 className="mt-3 text-2xl font-medium tracking-tight sm:text-3xl">
        Ты вышел на работу джуном
      </h2>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        Сара, Майк, Эмма и Джон — твоя команда. Они дают задачи, проверяют код и в конце
        спринта решают, что с твоим грейдом. Весь круг выглядит так.
      </p>

      <ol className="mt-7 grid gap-x-8 gap-y-5 sm:grid-cols-2">
        {STEPS.map((step, index) => (
          <li key={step.title} className="flex gap-3">
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-border font-mono text-[11px] text-primary">
              {index + 1}
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium leading-snug">{step.title}</p>
              <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
                {step.body}
              </p>
            </div>
          </li>
        ))}
      </ol>

      <button
        type="button"
        onClick={onDismiss}
        className="mt-8 inline-flex items-center gap-2 rounded-[10px] border border-border px-4 py-2.5 text-sm hover:border-primary/50"
      >
        <Check className="size-4" />
        Понятно, начинаем
      </button>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Вернуться к этому можно кнопкой «Как это работает» наверху.
      </p>
    </section>
  );
}

export function HowItWorksButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground hover:text-foreground"
    >
      Как это работает
      <ArrowRight className="size-3" />
    </button>
  );
}
