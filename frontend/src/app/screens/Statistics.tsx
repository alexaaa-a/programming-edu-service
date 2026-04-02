import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, BarChart3, CheckCircle2, Clock3, Target, Trophy, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { getMySubmissionStats } from "@/lib/api";
import type { UserSubmissionStats } from "@/lib/types";

function ratio(part: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((part / total) * 100)));
}

export default function Statistics() {
  useRequireAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState<UserSubmissionStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await getMySubmissionStats();
        setStats(data);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Не удалось загрузить статистику");
        setStats(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const reviewedPct = useMemo(
    () => ratio(stats?.reviewed_submissions ?? 0, stats?.total_submissions ?? 0),
    [stats],
  );
  const pendingPct = useMemo(
    () => ratio(stats?.pending_submissions ?? 0, stats?.total_submissions ?? 0),
    [stats],
  );
  const failedPct = useMemo(
    () => ratio(stats?.failed_submissions ?? 0, stats?.total_submissions ?? 0),
    [stats],
  );

  return (
    <div className="min-h-screen p-6 md:p-12">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/dashboard")}
            className="rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Назад
          </Button>
        </div>

        <div className="bg-white rounded-[20px] p-8 md:p-10 shadow-lg mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 rounded-full bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] flex items-center justify-center">
              <BarChart3 className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-3xl">Статистика прогресса</h1>
          </div>
          <p className="text-[#9E9E9E]">Ваши метрики по отправкам решений и ИИ-ревью.</p>
        </div>

        {loading && <p className="text-center text-[#9E9E9E] py-16">Загружаем статистику…</p>}

        {!loading && stats && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <div className="bg-white rounded-[20px] p-6 shadow-lg">
                <p className="text-sm text-[#9E9E9E] mb-2">Всего отправок</p>
                <p className="text-3xl">{stats.total_submissions}</p>
              </div>
              <div className="bg-white rounded-[20px] p-6 shadow-lg">
                <p className="text-sm text-[#9E9E9E] mb-2">Уникальных задач</p>
                <p className="text-3xl">{stats.tasks_attempted}</p>
              </div>
              <div className="bg-white rounded-[20px] p-6 shadow-lg">
                <p className="text-sm text-[#9E9E9E] mb-2">Средняя оценка</p>
                <p className="text-3xl">
                  {stats.average_score === null ? "—" : `${Math.round(stats.average_score * 10)}/100`}
                </p>
              </div>
              <div className="bg-white rounded-[20px] p-6 shadow-lg">
                <p className="text-sm text-[#9E9E9E] mb-2">Лучшая оценка</p>
                <p className="text-3xl">
                  {stats.best_score === null ? "—" : `${stats.best_score * 10}/100`}
                </p>
              </div>
            </div>

            <div className="bg-white rounded-[20px] p-8 shadow-lg">
              <h2 className="text-xl mb-6">Статусы проверок</h2>

              <div className="space-y-5">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-[#FF9BB5]" />
                      Проверено
                    </p>
                    <p className="text-sm text-[#9E9E9E]">
                      {stats.reviewed_submissions} ({reviewedPct}%)
                    </p>
                  </div>
                  <div className="w-full h-3 bg-[#FFF5F8] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4]"
                      style={{ width: `${reviewedPct}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm flex items-center gap-2">
                      <Clock3 className="w-4 h-4 text-[#FF9BB5]" />
                      В ожидании
                    </p>
                    <p className="text-sm text-[#9E9E9E]">
                      {stats.pending_submissions} ({pendingPct}%)
                    </p>
                  </div>
                  <div className="w-full h-3 bg-[#FFF5F8] rounded-full overflow-hidden">
                    <div className="h-full bg-[#FFC2D4]" style={{ width: `${pendingPct}%` }} />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm flex items-center gap-2">
                      <XCircle className="w-4 h-4 text-[#FF9BB5]" />
                      Ошибка проверки
                    </p>
                    <p className="text-sm text-[#9E9E9E]">
                      {stats.failed_submissions} ({failedPct}%)
                    </p>
                  </div>
                  <div className="w-full h-3 bg-[#FFF5F8] rounded-full overflow-hidden">
                    <div className="h-full bg-[#FFE5EC]" style={{ width: `${failedPct}%` }} />
                  </div>
                </div>
              </div>

              <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-[16px] bg-[#FFF5F8] p-4 flex items-center gap-3">
                  <Target className="w-5 h-5 text-[#FF9BB5]" />
                  <div>
                    <p className="text-sm text-[#9E9E9E]">Процент успешных проверок</p>
                    <p className="text-lg">{reviewedPct}%</p>
                  </div>
                </div>
                <div className="rounded-[16px] bg-[#FFF5F8] p-4 flex items-center gap-3">
                  <Trophy className="w-5 h-5 text-[#FF9BB5]" />
                  <div>
                    <p className="text-sm text-[#9E9E9E]">Текущий фокус</p>
                    <p className="text-lg">
                      {stats.pending_submissions > 0 ? "Закрыть pending-отправки" : "Держать качество на уровне"}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
