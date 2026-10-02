export interface UnlockedBadge {
  id: string;
  title: string;
  hint: string;
}

type Listener = (badges: UnlockedBadge[]) => void;

const listeners = new Set<Listener>();
const shown = new Set<string>();

function seenKey(id: string): string {
  return `desk_badge_shown:${id}`;
}

function alreadyShown(id: string): boolean {
  if (shown.has(id)) return true;
  try {
    return localStorage.getItem(seenKey(id)) === "1";
  } catch {
    return false;
  }
}

function markShown(id: string): void {
  shown.add(id);
  try {
    localStorage.setItem(seenKey(id), "1");
  } catch {
    /* приватный режим — переживём без памяти между сессиями */
  }
}

export function parseUnlocked(raw: unknown): UnlockedBadge[] {
  if (!Array.isArray(raw)) return [];
  const badges: UnlockedBadge[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Partial<UnlockedBadge>;
    if (typeof row.id !== "string" || !row.id) continue;
    badges.push({
      id: row.id,
      title: typeof row.title === "string" && row.title ? row.title : row.id,
      hint: typeof row.hint === "string" ? row.hint : "",
    });
  }
  return badges;
}

export function pushUnlocked(raw: unknown): void {
  const fresh = parseUnlocked(raw).filter((badge) => !alreadyShown(badge.id));
  if (fresh.length === 0) return;
  for (const badge of fresh) markShown(badge.id);
  for (const listener of listeners) listener(fresh);
}

export function onUnlocked(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
