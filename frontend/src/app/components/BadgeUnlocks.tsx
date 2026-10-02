import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { onUnlocked, type UnlockedBadge } from "@/lib/unlocks";
import { burstConfetti } from "./ConfettiBurst";
import { BadgeGlyph } from "./BadgeGlyph";

const VISIBLE_MS = 7000;

type Card = UnlockedBadge & { key: string };

export function BadgeUnlocks() {
  const [cards, setCards] = useState<Card[]>([]);

  useEffect(() => {
    return onUnlocked((badges) => {
      const stamp = Date.now();
      setCards((prev) => [
        ...prev,
        ...badges.map((badge, index) => ({ ...badge, key: `${badge.id}-${stamp}-${index}` })),
      ]);
      burstConfetti();
    });
  }, []);

  useEffect(() => {
    if (cards.length === 0) return;
    const timer = window.setTimeout(() => {
      setCards((prev) => prev.slice(1));
    }, VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [cards]);

  if (cards.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 top-5 z-[90] flex flex-col items-center gap-2 px-5"
      role="status"
      aria-live="polite"
    >
      {cards.slice(0, 3).map((card) => (
        <div
          key={card.key}
          className="pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-[10px] border border-primary/40 bg-card p-4 shadow-[0_18px_40px_-24px_rgba(0,0,0,0.8)] motion-safe:animate-[badge-in_380ms_var(--ease-out)]"
        >
          <BadgeGlyph id={card.id} className="mt-0.5 size-5 text-primary" />
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[11px] text-primary">Новый бейдж</p>
            <p className="mt-1 text-sm font-medium leading-snug">{card.title}</p>
            {card.hint ? (
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{card.hint}</p>
            ) : null}
          </div>
          <button
            type="button"
            aria-label="Скрыть"
            onClick={() => setCards((prev) => prev.filter((item) => item.key !== card.key))}
            className="rounded-md p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
