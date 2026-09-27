export const TEAM = [
  { name: "Сара", role: "Продакт", accent: "#e4b48a", presence: "в эфире" },
  { name: "Майк", role: "Аналитик", accent: "#cbb992", presence: "смотрит метрики" },
  { name: "Эмма", role: "Тестировщик", accent: "#9bb8aa", presence: "ждёт ревью" },
  { name: "Джон", role: "Тимлид", accent: "#c3b0cc", presence: "на стендапе" },
] as const;

export type TeamMember = (typeof TEAM)[number];

export function memberFromSender(sender?: string): TeamMember {
  if (!sender) return TEAM[3];
  const found = TEAM.find((m) => sender.startsWith(m.name));
  return found ?? TEAM[3];
}
