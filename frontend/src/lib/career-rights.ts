import type { BoardResponse, CareerGrade, TaskResponse } from "./types";

export const GRADE_LABEL: Record<CareerGrade, string> = {
  intern: "Стажёр",
  junior: "Junior",
  junior_plus: "Junior+",
  strong: "Strong junior",
  offer: "Оффер",
};

const RANK: Record<CareerGrade, number> = {
  intern: 0,
  junior: 1,
  junior_plus: 2,
  strong: 3,
  offer: 4,
};

export function formatRub(value: number): string {
  return `${new Intl.NumberFormat("ru-RU").format(value)} ₽`;
}

export function careerRights(grade: CareerGrade | null | undefined, appealUsed = false) {
  const known = grade != null && grade in RANK;
  const rank = known ? RANK[grade as CareerGrade] : 1;
  return {
    oneSpeaker: grade === "intern",
    criteriaBeforeSubmit: known && rank >= RANK.junior_plus,
    pickFirstTask: known && rank >= RANK.junior_plus,
    shortBrief: known && rank >= RANK.strong,
    appeal: known && rank >= RANK.strong && !appealUsed,
    chooseDirection: known && rank >= RANK.offer,
    reopenLetter: known && rank >= RANK.offer,
  };
}

const CRITERIA_HEAD = /^(?:#+\s*)?(критерии(?:\s+при[её]мки)?|acceptance criteria)\s*:?\s*$/i;
const PLAN_HEAD = /^(?:#+\s*)?(план|как делать|шаги|план решения)\s*:?\s*$/i;

interface Sections {
  body: string;
  plan: string;
  criteria: string[];
}

function splitSections(description: string): Sections {
  const body: string[] = [];
  const plan: string[] = [];
  const criteria: string[] = [];
  let section: "body" | "plan" | "criteria" = "body";
  for (const line of description.split("\n")) {
    const trimmed = line.trim();
    if (CRITERIA_HEAD.test(trimmed)) {
      section = "criteria";
      continue;
    }
    if (PLAN_HEAD.test(trimmed)) {
      section = "plan";
      continue;
    }
    if (section === "criteria") {
      const item = trimmed.replace(/^[-*•]\s*/, "").replace(/^\d+[.)]\s*/, "");
      if (item) criteria.push(item);
    } else if (section === "plan") {
      plan.push(line);
    } else {
      body.push(line);
    }
  }
  return {
    body: body.join("\n").trim(),
    plan: plan.join("\n").trim(),
    criteria,
  };
}

function peelNumberedPlan(text: string): { body: string; plan: string } {
  const lines = text.split("\n");
  let start = -1;
  let run = 0;
  for (let i = 0; i < lines.length; i += 1) {
    if (/^\s*\d+[.)]\s+\S/.test(lines[i])) {
      if (run === 0) start = i;
      run += 1;
    } else if (lines[i].trim() === "" && run > 0) {
      continue;
    } else {
      run = 0;
      start = -1;
    }
  }
  if (run >= 3 && start > 0) {
    return {
      body: lines.slice(0, start).join("\n").trim(),
      plan: lines.slice(start).join("\n").trim(),
    };
  }
  return { body: text.trim(), plan: "" };
}

export interface TaskBrief {
  prose: string;
  criteria: string[];
}

export function presentTask(
  description: string,
  grade: CareerGrade | null | undefined,
  submitted: boolean,
  criteriaUnlocked = false,
): TaskBrief {
  const rights = careerRights(grade);
  if (grade !== "intern" && !rights.criteriaBeforeSubmit && !rights.shortBrief) {
    return { prose: description, criteria: [] };
  }
  const split = splitSections(description);
  let body = split.body;
  let plan = split.plan;
  if (rights.shortBrief && !plan) {
    const peeled = peelNumberedPlan(body);
    body = peeled.body;
    plan = peeled.plan;
  }
  const showCriteria =
    split.criteria.length > 0 &&
    (rights.criteriaBeforeSubmit || criteriaUnlocked || (grade === "intern" && submitted));
  const chunks = [body];
  if (!rights.shortBrief && plan) chunks.push(plan);
  if (grade === "intern" && submitted && !showCriteria && split.criteria.length) {
    chunks.push(split.criteria.map((item) => `- ${item}`).join("\n"));
  }
  return {
    prose: chunks.filter(Boolean).join("\n\n").trim(),
    criteria: showCriteria ? split.criteria : [],
  };
}

export function isNightIncident(title: string): boolean {
  return title === "Ночной инцидент";
}

export function taskIsOpen(task: TaskResponse, board: BoardResponse, pickFirst: boolean): boolean {
  if (isNightIncident(task.title)) return true;
  if (task.status !== "todo") return true;
  const locking = [...board.in_progress, ...board.review].filter(
    (item) => !isNightIncident(item.title),
  );
  if (locking.length > 0) return false;
  if (pickFirst) return true;
  const queue = board.todo.filter((item) => !isNightIncident(item.title));
  return queue[0]?.task_id === task.task_id;
}

const MENTION = /@(?:Сара|Майк|Эмма|Джон)/gi;

export const SPEND_PRICE = {
  extra_round: 15_000,
  emma_session: 10_000,
  early_criteria: 8_000,
} as const;

export function boughtForTask(
  purchases: { item: string; task_id: number | null }[] | undefined,
  item: string,
  taskId: number,
): boolean {
  return (purchases ?? []).some((purchase) => purchase.item === item && purchase.task_id === taskId);
}

export function hasUnusedEmma(
  purchases: { item: string; used?: boolean }[] | undefined,
): boolean {
  return (purchases ?? []).some((purchase) => purchase.item === "emma_session" && !purchase.used);
}

export function keepOneMention(text: string): { text: string; trimmed: boolean } {
  const found = text.match(MENTION);
  if (!found || found.length <= 1) return { text, trimmed: false };
  const rest = text.replace(MENTION, " ").replace(/\s+/g, " ").trim();
  return { text: `${found[0]} ${rest}`.trim(), trimmed: true };
}
