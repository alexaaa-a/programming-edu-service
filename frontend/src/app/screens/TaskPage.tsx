import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import {
  Calendar,
  MessageCircle,
  ArrowLeft,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { useRequireAuth } from "../hooks/useRequireAuth";
import {
  getBoard,
  getTaskSubmissions,
  submitCode,
  updateTaskStatus,
} from "@/lib/api";
import { startBackgroundReviewPoll } from "@/lib/background-review";
import type { Submission, TaskResponse, TaskStatus } from "@/lib/types";

function sortSubmissionsNewestFirst(subs: Submission[]): Submission[] {
  return [...subs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
}

function nextStatus(s: TaskStatus): TaskStatus | null {
  if (s === "todo") return "in_progress";
  if (s === "in_progress") return "review";
  if (s === "review") return "done";
  return null;
}

function flattenBoard(board: Awaited<ReturnType<typeof getBoard>>): TaskResponse[] {
  return [
    ...board.todo,
    ...board.in_progress,
    ...board.review,
    ...board.done,
  ];
}

const inputClass =
  "w-full min-h-[200px] rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 py-4 focus:border-[#FF9BB5] focus:outline-none transition-colors text-[#4A4A4A] leading-relaxed resize-y";

const inputClassLocked =
  "w-full min-h-[200px] rounded-[20px] border-2 border-[#FFE5EC] bg-[#FAFAFA] px-5 py-4 text-[#4A4A4A] leading-relaxed resize-y cursor-default";

export default function TaskPage() {
  useRequireAuth();
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<TaskResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [codeLocked, setCodeLocked] = useState(false);
  const [submissionReportId, setSubmissionReportId] = useState<number | null>(null);

  const idNum = taskId ? Number(taskId) : NaN;

  const loadTask = useCallback(async () => {
    if (Number.isNaN(idNum)) {
      setTask(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const board = await getBoard();
      const found = flattenBoard(board).find((t) => t.task_id === idNum);
      setTask(found ?? null);
      if (!found) {
        setCode("");
        setCodeLocked(false);
        setSubmissionReportId(null);
        return;
      }

      const subs = await getTaskSubmissions(found.task_id);
      if (subs.length > 0) {
        const reviewed = subs
          .filter((s) => s.review !== null)
          .sort((a, b) => {
            const ad = a.reviewed_at ?? a.created_at;
            const bd = b.reviewed_at ?? b.created_at;
            return new Date(bd).getTime() - new Date(ad).getTime();
          });
        const sorted = sortSubmissionsNewestFirst(subs);
        const latest = sorted[0];
        setCode(latest.code);
        setCodeLocked(true);
        setSubmissionReportId(
          found.status === "done" && reviewed[0]
            ? reviewed[0].submission_id
            : latest.submission_id,
        );
      } else {
        setCode("");
        setCodeLocked(false);
        setSubmissionReportId(null);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось загрузить задачу");
      setTask(null);
      setCode("");
      setCodeLocked(false);
      setSubmissionReportId(null);
    } finally {
      setLoading(false);
    }
  }, [idNum]);

  useEffect(() => {
    void loadTask();
  }, [loadTask]);

  useEffect(() => {
    const handler = (e: Event) => {
      const d = (e as CustomEvent<{ taskId: number }>).detail;
      if (d.taskId === idNum) void loadTask();
    };
    window.addEventListener("submission-review-ready", handler);
    return () => window.removeEventListener("submission-review-ready", handler);
  }, [idNum, loadTask]);

  const handleAdvance = async () => {
    if (!task) return;
    const next = nextStatus(task.status);
    if (!next) return;
    setAdvancing(true);
    try {
      await updateTaskStatus(task.task_id, next);
      toast.success("Статус обновлен");
      await loadTask();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось обновить статус");
    } finally {
      setAdvancing(false);
    }
  };

  const handleSubmit = async () => {
    if (codeLocked) {
      toast.error("Решение уже отправлено на проверку");
      return;
    }
    if (!task || !code.trim()) {
      toast.error("Сначала добавьте код решения");
      return;
    }
    if (task.status !== "in_progress" && task.status !== "review") {
      toast.error("Переведите задачу в статус «В работе» или «Ревью», чтобы отправить код");
      return;
    }
    setSubmitting(true);
    try {
      const submissionId = await submitCode(task.task_id, code);
      toast.info("Решение отправлено на ИИ-проверку", {
        description:
          "Проверка идёт в фоне: можно перейти в дашборд или в другой раздел. Когда отчёт будет готов, появится яркое уведомление с кнопкой «Открыть отчёт». Прогресс не теряется.",
        duration: 12_000,
      });
      startBackgroundReviewPoll(submissionId, task.task_id, task.title);
      await loadTask();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось отправить решение");
    } finally {
      setSubmitting(false);
    }
  };

  const dueHint = task?.created_at
    ? new Date(task.created_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "";

  const canSubmit =
    task &&
    !codeLocked &&
    (task.status === "in_progress" || task.status === "review") &&
    code.trim().length > 0;

  const advanceLabel =
    task?.status === "todo"
      ? "Начать задачу"
      : task?.status === "in_progress"
        ? "Отправить на ревью"
        : task?.status === "review"
          ? "Отметить выполненной"
          : null;

  return (
    <div className="min-h-screen p-6 md:p-12">
      <div className="max-w-3xl mx-auto">
        <button
          type="button"
          onClick={() => navigate("/dashboard")}
          className="flex items-center gap-2 text-[#9E9E9E] hover:text-[#FF9BB5] mb-8 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
          <span>Назад к дашборду</span>
        </button>

        {loading && (
          <div className="flex justify-center py-20 text-[#9E9E9E] gap-2 items-center">
            <Loader2 className="w-5 h-5 animate-spin" />
            Загрузка задачи…
          </div>
        )}

        {!loading && !task && (
          <div className="bg-white rounded-[20px] p-8 shadow-lg text-center text-[#9E9E9E]">
            Задача не найдена.
          </div>
        )}

        {!loading && task && (
          <div className="bg-white rounded-[20px] p-8 md:p-10 shadow-lg">
            <div className="flex items-start justify-between mb-8 flex-wrap gap-4">
              <h1 className="text-2xl md:text-3xl flex-1 pr-4">{task.title}</h1>
              <div className="flex items-center gap-2 text-sm text-[#9E9E9E] bg-[#FFE5EC] px-4 py-2 rounded-full whitespace-nowrap">
                <Calendar className="w-4 h-4" />
                <span>Создана {dueHint}</span>
              </div>
            </div>

            <div className="mb-2">
              <span className="inline-block text-xs font-medium uppercase tracking-wide text-[#9E9E9E] bg-[#FFF5F8] px-3 py-1 rounded-full">
                {task.status.replace("_", " ")}
              </span>
            </div>

            <div className="mb-8">
              <h3 className="text-lg mb-4 text-[#FF9BB5]">Описание</h3>
              <div className="text-[#4A4A4A] leading-relaxed whitespace-pre-wrap">
                {task.description}
              </div>
            </div>

            {advanceLabel && (
              <div className="mb-8">
                <Button
                  type="button"
                  disabled={advancing}
                  onClick={() => void handleAdvance()}
                  className="h-12 px-6 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white shadow-md"
                >
                  {advancing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      {advanceLabel}
                      <ChevronRight className="w-4 h-4 ml-1" />
                    </>
                  )}
                </Button>
              </div>
            )}

            <div className="mb-6">
              <h3 className="text-lg mb-3 text-[#FF9BB5]">Ваше решение</h3>
              <textarea
                className={codeLocked ? inputClassLocked : inputClass}
                placeholder="Вставьте ваш код сюда…"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                readOnly={codeLocked}
                spellCheck={false}
              />
              <p className="text-xs text-[#9E9E9E] mt-2">
                {codeLocked
                  ? "Решение уже отправлено на ИИ-проверку. Редактирование и повторная отправка недоступны."
                  : "Отправка доступна, пока задача в статусе «В работе» или «Ревью»."}
              </p>
            </div>

            <div className="flex flex-col md:flex-row gap-4">
              <Button
                type="button"
                disabled={codeLocked || !canSubmit || submitting}
                onClick={() => void handleSubmit()}
                className="flex-1 h-14 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white text-lg shadow-md"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Отправляем…
                  </>
                ) : codeLocked ? (
                  "Уже отправлено"
                ) : (
                  "Отправить на ИИ-проверку"
                )}
              </Button>
              <Button
                type="button"
                onClick={() =>
                  navigate("/chat", {
                    state: { taskTitle: task.title, taskId: task.task_id },
                  })
                }
                variant="outline"
                className="flex-1 h-14 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC] hover:border-[#FF9BB5]"
              >
                <MessageCircle className="w-5 h-5 mr-2" />
                Задать вопрос
              </Button>
            </div>
            {codeLocked && submissionReportId && (
              <div className="mt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigate(`/report/${submissionReportId}`)}
                  className="w-full h-12 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC] hover:border-[#FF9BB5]"
                >
                  {task.status === "done" ? "Открыть завершенное ревью" : "Открыть страницу проверки"}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
