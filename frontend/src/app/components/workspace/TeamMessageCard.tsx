import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { MessageCircle } from "lucide-react";
import { pingTeamNudge } from "@/lib/api";
import type { TeamNudge } from "@/lib/types";
import { cn } from "../ui/utils";

export function TeamMessageCard({
  className,
  taskTitle,
}: {
  className?: string;
  taskTitle?: string | null;
}) {
  const navigate = useNavigate();
  const [nudge, setNudge] = useState<TeamNudge | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const data = await pingTeamNudge(taskTitle);
        if (alive) setNudge(data);
      } catch {
        // сообщение необязательное: молчим
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (!nudge || hidden) return null;

  return (
    <section
      className={cn(
        "rounded-[10px] border border-primary/30 bg-primary/5 p-5 sm:p-6",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
          <MessageCircle className="size-4" />
        </span>
        <div className="min-w-0">
          <p className="font-mono text-[11px] text-primary">
            {nudge.speaker_name} написала первой
          </p>
          <p className="mt-2 text-sm leading-relaxed">{nudge.message}</p>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={() => navigate("/chat")}
              className="inline-flex h-10 items-center rounded-[10px] bg-primary px-4 text-sm font-medium text-primary-foreground"
            >
              Ответить в чате
            </button>
            <button
              type="button"
              onClick={() => setHidden(true)}
              className="text-sm text-muted-foreground underline-offset-4 hover:underline"
            >
              Позже
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
