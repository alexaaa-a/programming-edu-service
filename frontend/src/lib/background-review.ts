import { toast } from "sonner";
import { getSubmission } from "./api";
import { appNavigate } from "./app-navigate";

const polling = new Set<number>();

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
    try {
      for (let i = 0; i < maxAttempts; i++) {
        const s = await getSubmission(submissionId);
        if (s.review) {
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
              detail: { submissionId, taskId },
            }),
          );
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
      }
      toast.info("Проверка всё ещё выполняется", {
        description:
          "Загляните на страницу задачи или откройте отчёт позже — результат появится, как только обработка закончится.",
        duration: 9000,
      });
    } catch {
      toast.error("Не удалось дождаться результата проверки");
    } finally {
      polling.delete(submissionId);
    }
  })();
}
