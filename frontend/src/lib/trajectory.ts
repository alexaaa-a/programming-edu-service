import type { TrajectoryAction, UserTrajectory } from "./types";

export type { TrajectoryAction, UserTrajectory } from "./types";

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
    return {
      title: "Разбери замечания",
      body: failed
        ? `Команда уже видит бриф: ${trajectory.reason} Не закрыто: ${failed}.`
        : `Команда уже видит бриф: ${trajectory.reason}`,
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
