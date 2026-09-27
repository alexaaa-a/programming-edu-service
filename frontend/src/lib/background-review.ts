import { toast } from "sonner";
import { getSubmission } from "./api";
import { appNavigate } from "./app-navigate";

const polling = new Set<number>();
const announced = new Set<number>();

export function isReviewPollActive(submissionId: number): boolean {
  return polling.has(submissionId);
}

export function startBackgroundReviewPoll(
  submissionId: number,
  taskId: number,
  taskTitle?: string | null,
  maxAttempts = 90,
): void {
  if (polling.has(submissionId)) return;
  polling.add(submissionId);

  const taskHint = taskTitle?.trim()
    ? `Задача «${taskTitle.trim()}». `
    : "";

  void (async () => {
    let slowNotified = false;
    let errorNotified = false;
    try {
      for (;;) {
        try {
          for (let i = 0; i < maxAttempts; i++) {
            const s = await getSubmission(submissionId);
            if (s.review) {
              if (announced.has(submissionId)) return;
              announced.add(submissionId);
              toast.success("ИИ-проверка решения готова", {
                description: `${taskHint}Откройте отчёт с оценкой и рекомендациями.`,
                duration: 14_000,
                action: {
                  label: "Открыть отчёт",
                  onClick: () => appNavigate(`/report/${submissionId}`),
                },
              });
              window.dispatchEvent(
                new CustomEvent("submission-review-ready", {
                  detail: { submissionId, taskId, status: s.status },
                }),
              );
              return;
            }
            if (s.status === "failed") {
              toast.error("Проверка не удалась", {
                description:
                  `${taskHint}Можно отправить решение ещё раз или спросить команду.`,
                duration: 12_000,
              });
              window.dispatchEvent(
                new CustomEvent("submission-review-ready", {
                  detail: { submissionId, taskId, status: "failed" },
                }),
              );
              return;
            }
            await new Promise((r) => setTimeout(r, 2000));
          }
          if (!slowNotified) {
            toast.info("Проверка всё ещё выполняется", {
              description:
                "Загляните на страницу задачи или откройте отчёт позже — результат появится, как только обработка закончится.",
              duration: 9000,
            });
            slowNotified = true;
          }
          await new Promise((r) => setTimeout(r, 10_000));
        } catch {
          if (!errorNotified) {
            toast.error("Не удалось дождаться результата проверки — повторяем…");
            errorNotified = true;
          }
          await new Promise((r) => setTimeout(r, 5_000));
        }
      }
    } finally {
      polling.delete(submissionId);
    }
  })();
}
