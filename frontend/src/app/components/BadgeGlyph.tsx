import {
  Award,
  Bug,
  CalendarCheck,
  Flame,
  Medal,
  Mic,
  Siren,
  Target,
  TrendingUp,
  Wallet,
  Zap,
  type LucideIcon,
} from "lucide-react";

const GLYPHS: Record<string, LucideIcon> = {
  first_close: Award,
  first_try: Zap,
  nine: Target,
  streak_three: Flame,
  streak_five: Flame,
  bug_hunter: Bug,
  firefighter: Siren,
  pitch: Mic,
  promoted: TrendingUp,
  investor: Wallet,
  veteran: CalendarCheck,
};

export function BadgeGlyph({ id, className }: { id: string; className?: string }) {
  const Icon = GLYPHS[id] ?? Medal;
  return <Icon className={className} aria-hidden="true" />;
}
