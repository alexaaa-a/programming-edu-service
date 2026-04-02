import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Calendar, Users, LogOut, LayoutGrid, Shield, UserRound, BarChart3 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { useRequireAuth } from "../hooks/useRequireAuth";
import {
  apiFetch,
  completeSprint,
  getBoard,
  getMyAdminRole,
  getMe,
  getTemplateForStart,
  logoutRemote,
  startProject,
} from "@/lib/api";
import type { AdminRole, BoardResponse, Sprint, TaskResponse, UserShow } from "@/lib/types";

function pickCurrentTask(board: BoardResponse): TaskResponse | null {
  const first = (arr: TaskResponse[]) => arr[0] ?? null;
  return (
    first(board.in_progress) ??
    first(board.review) ??
    first(board.todo) ??
    null
  );
}

function allDone(board: BoardResponse): boolean {
  return (
    board.todo.length === 0 &&
    board.in_progress.length === 0 &&
    board.review.length === 0 &&
    board.done.length > 0
  );
}

const teamMembers = [
  { id: 1, name: "Сара", role: "Продакт", color: "#FF9BB5" },
  { id: 2, name: "Майк", role: "Аналитик", color: "#FFC2D4" },
  { id: 3, name: "Эмма", role: "Тестировщик", color: "#FFE5EC" },
  { id: 4, name: "Джон", role: "Тимлид", color: "#FF9BB5" },
];

const columnMeta = [
  { key: "todo" as const, label: "К выполнению" },
  { key: "in_progress" as const, label: "В работе" },
  { key: "review" as const, label: "Ревью" },
  { key: "done" as const, label: "Готово" },
];

export default function Dashboard() {
  useRequireAuth();
  const navigate = useNavigate();
  const [me, setMe] = useState<UserShow | null>(null);
  const [sprint, setSprint] = useState<Sprint | null>(null);
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const profile = await getMe();
      if (!profile.direction || !profile.level) {
        navigate("/direction", { replace: true });
        return;
      }
      setMe(profile);
      const role = await getMyAdminRole();
      setAdminRole(role.role);

      let sp: Sprint;
      const sprintRes = await apiFetch("/api/task/v1/sprint/current");
      if (sprintRes.ok) {
        sp = (await sprintRes.json()) as Sprint;
      } else if (sprintRes.status === 404) {
        const tpl = await getTemplateForStart();
        await startProject(tpl.template_id);
        const again = await apiFetch("/api/task/v1/sprint/current");
        if (!again.ok) {
          throw new Error(await again.text());
        }
        sp = (await again.json()) as Sprint;
      } else {
        throw new Error(await sprintRes.text());
      }
      setSprint(sp);

      const b = await getBoard();
      setBoard(b);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Не удалось загрузить дашборд";
      toast.error(msg);
      setSprint(null);
      setBoard(null);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleLogout = async () => {
    await logoutRemote();
    navigate("/login", { replace: true });
  };

  const handleCompleteSprint = async () => {
    if (!board || !allDone(board)) return;
    setCompleting(true);
    try {
      await completeSprint();
      toast.success("Спринт завершен");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось завершить спринт");
    } finally {
      setCompleting(false);
    }
  };

  const current = board ? pickCurrentTask(board) : null;
  const firstName = me?.name ?? "друг";

  const sprintLabel = sprint
    ? `Спринт ${sprint.order} · ${sprint.status}`
    : "";

  const started = sprint?.started_at
    ? new Date(sprint.started_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "";

  return (
    <div className="min-h-screen p-6 md:p-12">
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-10">
          <h1 className="text-3xl">Привет, {firstName} 👋</h1>
          <div className="flex items-center gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate("/profile")}
              className="h-11 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
            >
              <UserRound className="w-4 h-4 mr-2" />
              Профиль
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate("/statistics")}
              className="h-11 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
            >
              <BarChart3 className="w-4 h-4 mr-2" />
              Статистика
            </Button>
            {adminRole !== "user" && (
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate("/admin")}
                className="h-11 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
              >
                <Shield className="w-4 h-4 mr-2" />
                Админ-панель
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              onClick={() => void handleLogout()}
              className="h-11 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
            >
              <LogOut className="w-4 h-4 mr-2" />
              Выйти
            </Button>
          </div>
        </div>

        {loading && (
          <p className="text-[#9E9E9E] text-center py-16">Загружаем ваш спринт…</p>
        )}

        {!loading && board && (
          <>
            <div className="bg-white rounded-[20px] p-8 md:p-10 shadow-lg mb-8">
              <div className="flex items-start justify-between mb-6 flex-wrap gap-4">
                <div>
                  <h2 className="text-2xl mb-3">Текущая задача</h2>
                  {current ? (
                    <>
                      <h3 className="text-xl text-[#FF9BB5] mb-2">
                        {current.title}
                      </h3>
                      <p className="text-sm text-[#9E9E9E]">{sprintLabel}</p>
                    </>
                  ) : (
                    <p className="text-[#9E9E9E]">
                      {allDone(board)
                        ? "Все задачи в этом спринте завершены. Завершите спринт, чтобы продолжить."
                        : "На доске нет активной задачи."}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 text-sm text-[#9E9E9E] bg-[#FFE5EC] px-4 py-2 rounded-full">
                  <Calendar className="w-4 h-4" />
                  <span>{started ? `Старт: ${started}` : "Спринт"}</span>
                </div>
              </div>

              {current && (
                <p className="text-[#9E9E9E] mb-8 leading-relaxed line-clamp-4">
                  {current.description}
                </p>
              )}

              <div className="flex flex-col sm:flex-row gap-3">
                {current && (
                  <Button
                    onClick={() => navigate(`/task/${current.task_id}`)}
                    className="h-14 px-10 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white text-lg shadow-md"
                  >
                    Открыть задачу
                  </Button>
                )}
                {board && allDone(board) && (
                  <Button
                    disabled={completing}
                    onClick={() => void handleCompleteSprint()}
                    className="h-14 px-10 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white text-lg shadow-md"
                  >
                    {completing ? "Завершаем…" : "Завершить спринт"}
                  </Button>
                )}
              </div>
            </div>

            <div className="bg-white rounded-[20px] p-8 shadow-lg mb-8">
              <div className="flex items-center gap-2 mb-6">
                <LayoutGrid className="w-5 h-5 text-[#FF9BB5]" />
                <h3 className="text-xl">Доска спринта</h3>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {columnMeta.map((col) => (
                  <div key={col.key} className="rounded-[16px] bg-[#FFF5F8] p-4 min-h-[140px]">
                    <p className="text-xs font-medium text-[#9E9E9E] uppercase tracking-wide mb-3">
                      {col.label}
                    </p>
                    <ul className="space-y-2">
                      {board[col.key].map((t) => (
                        <li key={t.task_id}>
                          <button
                            type="button"
                            onClick={() => navigate(`/task/${t.task_id}`)}
                            className="w-full text-left rounded-[14px] bg-white px-3 py-2 text-sm shadow-sm hover:ring-2 hover:ring-[#FF9BB5]/40 transition-all"
                          >
                            {t.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        <div className="bg-white rounded-[20px] p-8 shadow-lg">
          <div className="flex items-center gap-2 mb-6">
            <Users className="w-5 h-5 text-[#FF9BB5]" />
            <h3 className="text-xl">Команда</h3>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {teamMembers.map((member) => (
              <div key={member.id} className="text-center">
                <div
                  className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-3"
                  style={{
                    background: `linear-gradient(135deg, ${member.color}, #FFC2D4)`,
                  }}
                >
                  <span className="text-white text-xl">
                    {member.name.charAt(0)}
                  </span>
                </div>
                <p className="mb-1">{member.name}</p>
                <p className="text-xs text-[#9E9E9E]">{member.role}</p>
              </div>
            ))}
          </div>

          <Button
            onClick={() => navigate("/chat")}
            variant="outline"
            className="w-full mt-6 h-12 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC] hover:border-[#FF9BB5]"
          >
            Открыть командный чат
          </Button>
        </div>
      </div>
    </div>
  );
}
