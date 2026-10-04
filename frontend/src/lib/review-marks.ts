import type { SubmissionReview } from "./types";

export interface ReviewMark {
  line: number;
  severity: "error" | "warning" | "info";
  kind: "criterion" | "challenge";
  title: string;
  message: string;
}

const SEVERITY: Record<string, ReviewMark["severity"]> = {
  high: "error",
  medium: "warning",
  low: "info",
};

export function reviewMarks(review: SubmissionReview | null | undefined): ReviewMark[] {
  if (!review) return [];
  const marks: ReviewMark[] = [];

  for (const item of review.criteria ?? []) {
    if (item.passed || !isLine(item.line)) continue;
    marks.push({
      line: item.line,
      severity: "warning",
      kind: "criterion",
      title: "Критерий приёмки",
      message: item.note ? `${item.text} — ${item.note}` : item.text,
    });
  }

  for (const item of review.challenges ?? []) {
    if (!isLine(item.line)) continue;
    marks.push({
      line: item.line,
      severity: SEVERITY[String(item.severity ?? "medium")] ?? "warning",
      kind: "challenge",
      title: "Замечание проверяющего",
      message: item.text,
    });
  }

  const seen = new Set<string>();
  return marks
    .filter((mark) => {
      const key = `${mark.line}:${mark.message}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => a.line - b.line);
}

export function unanchoredCount(review: SubmissionReview | null | undefined): number {
  if (!review) return 0;
  const criteria = (review.criteria ?? []).filter((item) => !item.passed && !isLine(item.line));
  const challenges = (review.challenges ?? []).filter((item) => !isLine(item.line));
  return criteria.length + challenges.length;
}

function isLine(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 1;
}
