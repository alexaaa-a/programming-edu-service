export const TEAM_PERSONAS = [
  { name: "Сара", role: "Продакт" },
  { name: "Майк", role: "Аналитик" },
  { name: "Эмма", role: "Тестировщик" },
  { name: "Джон", role: "Тимлид" },
] as const;

export function formatSender(person: { name: string; role: string }): string {
  return `${person.name} (${person.role})`;
}

export function pickResponder(
  question: string,
  fallbackIndex: number,
): { name: string; role: string } {
  const q = question.toLowerCase();
  if (q.includes("баг") || q.includes("ошиб") || q.includes("тест")) {
    return TEAM_PERSONAS[2];
  }
  if (q.includes("требован") || q.includes("срок") || q.includes("приоритет")) {
    return TEAM_PERSONAS[0];
  }
  if (q.includes("данн") || q.includes("метрик") || q.includes("анализ")) {
    return TEAM_PERSONAS[1];
  }
  if (q.includes("архитект") || q.includes("api") || q.includes("рефактор")) {
    return TEAM_PERSONAS[3];
  }
  return TEAM_PERSONAS[fallbackIndex % TEAM_PERSONAS.length];
}
