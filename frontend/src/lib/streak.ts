const KEY = "desk_streak_v1";

export type Streak = {
  count: number;
  longest: number;
  lastDay: string;
};

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function dayKey(d = new Date()): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function shiftDay(day: string, delta: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + delta);
  return dayKey(dt);
}

function empty(): Streak {
  return { count: 0, longest: 0, lastDay: "" };
}

export function readStreak(): Streak {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return empty();
    const parsed = JSON.parse(raw) as Streak;
    if (typeof parsed.count !== "number") return empty();
    return parsed;
  } catch {
    return empty();
  }
}

export function touchStreak(): Streak {
  const today = dayKey();
  const prev = readStreak();
  if (prev.lastDay === today) return prev;

  const next: Streak =
    prev.lastDay === shiftDay(today, -1)
      ? {
          count: prev.count + 1,
          longest: Math.max(prev.longest, prev.count + 1),
          lastDay: today,
        }
      : { count: 1, longest: Math.max(prev.longest, 1), lastDay: today };

  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}

export function streakDaysLabel(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "дня";
  return "дней";
}

const claimed = new Set<string>();

export function shouldCelebrate(key: string): boolean {
  const storageKey = `desk_celeb:${key}`;
  try {
    if (claimed.has(key) || localStorage.getItem(storageKey)) return false;
    claimed.add(key);
    localStorage.setItem(storageKey, "1");
    return true;
  } catch {
    return false;
  }
}
