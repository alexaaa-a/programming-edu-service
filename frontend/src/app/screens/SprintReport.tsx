import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Award, Loader2, Sparkles } from "lucide-react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getSubmission } from "@/lib/api";
import type { Submission } from "@/lib/types";
import { useRequireAuth } from "../hooks/useRequireAuth";

export default function SprintReport() {
  useRequireAuth();
  const { submissionId } = useParams<{ submissionId: string }>();
  const navigate = useNavigate();
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [loading, setLoading] = useState(true);

  const idNum = submissionId ? Number(submissionId) : NaN;

  useEffect(() => {
    if (Number.isNaN(idNum)) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const sub = await getSubmission(idNum);
        if (!cancelled) setSubmission(sub);
      } catch (e) {
        if (!cancelled) {
          toast.error(e instanceof Error ? e.message : "Не удалось загрузить отчет");
          setSubmission(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [idNum]);

  const review = submission?.review;
  const scoreOutOf100 = review ? Math.max(0, Math.min(100, review.score * 10)) : null;

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <div className="flex justify-center mb-8">
          <div className="bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white px-6 py-3 rounded-full shadow-lg flex items-center gap-2">
            <Award className="w-5 h-5" />
            <span>Проверка готова 🎉</span>
          </div>
        </div>

        <div className="bg-white rounded-[20px] p-8 md:p-10 shadow-lg">
          {loading && (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-[#9E9E9E]">
              <Loader2 className="w-8 h-8 animate-spin text-[#FF9BB5]" />
              Загружаем ваш отчет…
            </div>
          )}

          {!loading && !submission && (
            <p className="text-center text-[#9E9E9E]">Отчет не найден.</p>
          )}

          {!loading && submission && !review && (
            <div className="text-center py-8">
              <p className="text-[#9E9E9E] mb-6">
                Ваше решение еще проверяется. На этой странице появится оценка после
                завершения проверки.
              </p>
              <Button
                type="button"
                onClick={() => navigate("/dashboard")}
                className="h-12 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white px-8"
              >
                Вернуться на дашборд
              </Button>
            </div>
          )}

          {!loading && review && (
            <>
              <div className="text-center mb-8">
                <div className="inline-flex items-center justify-center w-32 h-32 rounded-full bg-gradient-to-br from-[#FFE5EC] to-[#FFC2D4] mb-4">
                  <div className="text-5xl text-[#FF9BB5]">{scoreOutOf100}</div>
                </div>
                <p className="text-[#9E9E9E]">из 100 баллов</p>
              </div>

              <div className="mb-8">
                <h3 className="text-xl mb-4 text-center flex items-center justify-center gap-2">
                  <Sparkles className="w-5 h-5 text-[#FF9BB5]" />
                  Обратная связь
                </h3>
                <div className="text-[#4A4A4A] leading-relaxed text-center max-w-lg mx-auto prose prose-sm max-w-none prose-p:my-2 prose-strong:text-inherit">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {review.feedback}
                  </ReactMarkdown>
                </div>
              </div>

              {review.suggestions.length > 0 && (
                <div className="mb-8">
                  <h4 className="text-lg mb-4 text-center">Рекомендации</h4>
                  <ul className="space-y-3">
                    {review.suggestions.map((s, i) => (
                      <li
                        key={i}
                        className="bg-[#FFF5F8] rounded-[20px] px-5 py-4 text-sm text-[#4A4A4A]"
                      >
                        <div className="prose prose-sm max-w-none prose-p:my-2 prose-strong:text-inherit">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {s}
                          </ReactMarkdown>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <Button
                type="button"
                onClick={() => navigate("/dashboard")}
                className="w-full h-14 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white text-lg shadow-md"
              >
                Вернуться на дашборд
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
