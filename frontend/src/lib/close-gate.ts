import type { Submission } from "./types";
import { scoreOutOfTen } from "./score";

export const PASS_SCORE = 8;
export const MAX_ROUNDS = 2;

export type CloseQuality = "ok" | "weak";

export type CloseDecision =
  | { allowed: false; code: "need_review" | "pending" | "revise"; reason: string }
  | { allowed: true; code: CloseQuality; quality: CloseQuality; reason: string };

function sortOldestFirst(subs: Submission[]): Submission[] {
  return [...subs].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );
}

export function countsTowardRounds(item: Submission): boolean {
  if (item.status === "pending") return false;
  if (item.review != null) return true;
  if (item.status === "failed" && item.reviewed_at != null) return true;
  return false;
}

export function countedRounds(subs: Submission[]): number {
  return subs.filter(countsTowardRounds).length;
}

export function evaluateCloseGate(subs: Submission[], maxRounds = MAX_ROUNDS): CloseDecision {
  const items = sortOldestFirst(subs);
  if (items.some((item) => item.status === "pending")) {
    return {
      allowed: false,
      code: "pending",
      reason: "Предыдущая сдача ещё на проверке — дождись отчёта.",
    };
  }
  const reviewed = items.filter((item) => item.review != null);
  const spent = countedRounds(items);
  const agentFailed = items.filter(
    (item) =>
      item.status === "failed" && item.review == null && item.reviewed_at != null,
  );
  const infraFailed = items.filter(
    (item) =>
      item.status === "failed" && item.review == null && item.reviewed_at == null,
  );

  if (reviewed.length === 0) {
    if (spent >= maxRounds) {
      return {
        allowed: true,
        code: "weak",
        quality: "weak",
        reason:
          "Лимит попыток исчерпан (в т.ч. сбои проверки). Можно закрыть задачу как слабую.",
      };
    }
    if (agentFailed.length > 0 || infraFailed.length > 0) {
      return {
        allowed: false,
        code: "revise",
        reason: "Проверка не удалась. Отправь решение ещё раз — закрыть задачу пока нельзя.",
      };
    }
    return {
      allowed: false,
      code: "need_review",
      reason: "Сначала отправь решение на ревью команды.",
    };
  }
  const score = scoreOutOfTen(reviewed[reviewed.length - 1].review!.score);
  if (score >= PASS_SCORE) {
    return {
      allowed: true,
      code: "ok",
      quality: "ok",
      reason: "Команда довольна. Можно закрыть задачу.",
    };
  }
  if (spent < maxRounds) {
    return {
      allowed: false,
      code: "revise",
      reason: "Балл ниже 8. Исправь замечания и сдайте снова — закрыть задачу пока нельзя.",
    };
  }
  return {
    allowed: true,
    code: "weak",
    quality: "weak",
    reason: "Лимит попыток исчерпан. Можно закрыть задачу как слабую.",
  };
}
