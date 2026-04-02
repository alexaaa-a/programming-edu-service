const teamMembers = [
  { name: "Сара", role: "Продакт" },
  { name: "Майк", role: "Аналитик" },
  { name: "Эмма", role: "Тестировщик" },
  { name: "Джон", role: "Тимлид" },
];

export function pickResponder(
  question: string,
  fallbackIndex: number,
): { name: string; role: string } {
  const q = question.toLowerCase();
  if (q.includes("баг") || q.includes("ошиб") || q.includes("тест")) {
    return teamMembers[2];
  }
  if (q.includes("требован") || q.includes("срок") || q.includes("приоритет")) {
    return teamMembers[0];
  }
  if (q.includes("данн") || q.includes("метрик") || q.includes("анализ")) {
    return teamMembers[1];
  }
  if (q.includes("архитект") || q.includes("api") || q.includes("рефактор")) {
    return teamMembers[3];
  }
  return teamMembers[fallbackIndex % teamMembers.length];
}
