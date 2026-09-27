import type {
  FocusKind,
  RecommendationKind,
  SkillStatus,
  TrajectoryAction,
  UserTrajectory,
} from "./types";

export type {
  TrajectoryAction,
  TrajectoryFocus,
  TrajectoryRecommendation,
  TrajectorySkill,
  UserTrajectory,
} from "./types";

export function pct01(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value * 100)));
}

export function actionTitle(action: TrajectoryAction): string {
  switch (action) {
    case "start":
      return "Возьми первую задачу";
    case "wait_review":
      return "Ждём ревью";
    case "revise":
      return "Доработай решение";
    case "chat":
      return "Разбери замечания с командой";
    case "close_ok":
      return "Можно закрывать задачу";
    case "close_weak":
      return "Закрой как слабую";
    case "next_task":
      return "Бери следующий узел";
    case "hold_sprint":
      return "Пока не открывай следующий спринт";
    case "next_sprint":
      return "Можно брать следующий спринт";
    default:
      return "Следующий шаг";
  }
}

export function actionCta(action: TrajectoryAction): string {
  switch (action) {
    case "chat":
      return "Спросить команду";
    case "revise":
      return "Исправить решение";
    case "wait_review":
      return "Открыть задачу";
    case "close_ok":
      return "Закрыть задачу";
    case "close_weak":
      return "Закрыть как слабую";
    case "next_sprint":
      return "Завершить спринт";
    case "hold_sprint":
      return "Остаться в спринте";
    default:
      return "Открыть задачу";
  }
}

export function chatEmptyCopy(trajectory: UserTrajectory | null): { title: string; body: string } {
  if (!trajectory) {
    return {
      title: "Спроси команду",
      body: "Напиши, что не сходится: «почему падает на нуле», «какой случай проверить», «как закрыть спринт после слабого зачёта». @Эмма — баг, @Сара — бриф, @Джон — как устроить код.",
    };
  }
  if (trajectory.action === "chat") {
    const failed = trajectory.failed_criteria.filter(Boolean).slice(0, 2).join("; ");
    const focus = trajectory.focus;
    const ask = focus ? ` Готовый вопрос: «${focus.ask}»` : "";
    return {
      title: "Разбери замечания",
      body: failed
        ? `Команда уже видит бриф: ${trajectory.reason} Не закрыто: ${failed}.${ask}`
        : `Команда уже видит бриф: ${trajectory.reason}${ask}`,
    };
  }
  if (trajectory.action === "revise") {
    return {
      title: "Спроси, что править",
      body: trajectory.reason,
    };
  }
  return {
    title: "Спроси команду",
    body: trajectory.reason || "Сара за бриф, Эмма за баги, Джон за архитектуру, Майк за данные.",
  };
}

export function focusKindLabel(kind: FocusKind): string {
  switch (kind) {
    case "fix":
      return "Перепроверить";
    case "learn":
      return "Пробел в знаниях";
    case "review":
      return "Пора повторить";
    case "grow":
      return "Граница умений";
    case "stretch":
      return "Следующий уровень";
    case "prepare":
      return "Перед первой сдачей";
    default:
      return "Фокус";
  }
}

export function skillStatusLabel(status: SkillStatus): string {
  switch (status) {
    case "mastered":
      return "освоен";
    case "learning":
      return "в процессе";
    case "gap":
      return "пробел";
    case "fading":
      return "забывается";
    case "new":
      return "ещё не было";
    default:
      return status;
  }
}

export function recommendationLabel(kind: RecommendationKind): string {
  switch (kind) {
    case "fix":
      return "Не закрыто";
    case "learn":
      return "Разобрать";
    case "review":
      return "Повторить";
    case "practice":
      return "Практика";
    case "next_task":
      return "Дальше";
    case "stretch":
      return "Усложнить";
    default:
      return "Шаг";
  }
}

export function velocityLabel(velocity: number | undefined): string | null {
  if (velocity == null || Math.abs(velocity) < 0.005) return null;
  const points = Math.round(velocity * 100);
  return `${points > 0 ? "+" : ""}${points} п.п. за неделю`;
}
