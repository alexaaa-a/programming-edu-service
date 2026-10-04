export type TaskStatus = "todo" | "in_progress" | "review" | "done";
export type CloseQuality = "ok" | "weak";

export type CareerGrade = "intern" | "junior" | "junior_plus" | "strong" | "offer";

export interface CareerLetter {
  at: string;
  old_salary: number;
  new_salary: number;
  bonus_paid: number;
  facts: string[];
  text: string;
  kind: "promote" | "no_raise" | "frozen" | string;
  old_grade: CareerGrade;
  new_grade: CareerGrade;
}

export interface FridayDemo {
  sara_line: string;
  question: string;
  criterion: string | null;
}

export interface CareerBadge {
  id: string;
  title: string;
  hint: string;
  at: string;
}

export interface CareerQuest {
  id: string;
  title: string;
  hint: string;
  current: number;
  target: number;
  left: number;
}

export interface CareerProgress {
  closes_ok: number;
  closes_weak: number;
  streak_ok: number;
  best_streak: number;
  first_try: number;
  nines: number;
  peer_found: number;
  incidents_done: number;
  demos_held: number;
  sprints: number;
  promotions: number;
  purchases: number;
}

export interface Career {
  grade: CareerGrade;
  salary: number;
  bonus: number;
  equity: number;
  raise_blocked: boolean;
  incident_used: boolean;
  appeal_used: boolean;
  pending_letter?: CareerLetter | null;
  pending_forced?: boolean;
  pending_demo?: FridayDemo | null;
  letters: CareerLetter[];
  purchases: {
    item: string;
    price: number;
    at: string;
    task_id: number | null;
    used?: boolean;
  }[];
  progress?: CareerProgress;
  badges?: CareerBadge[];
  quests?: CareerQuest[];
  badge_total?: number;
}

export interface UserShow {
  username: string;
  name: string;
  surname: string;
  email: string;
  direction: string | null;
  level: string | null;
}

export interface AuthResult {
  access_token: string;
  refresh_token: string;
}

export interface Sprint {
  sprint_id: number;
  user_project_id: number;
  user_id: number;
  order: number;
  status: string;
  started_at: string;
  completed_at: string | null;
  close_mode?: "ok" | "forced" | null;
}

export interface TaskResponse {
  task_id: number;
  user_id: number;
  user_project_id: number;
  sprint_id: number;
  title: string;
  description: string;
  status: TaskStatus;
  created_at: string;
  completed_at: string | null;
  close_quality?: CloseQuality | null;
  close_note?: string | null;
}

export interface BoardResponse {
  todo: TaskResponse[];
  in_progress: TaskResponse[];
  review: TaskResponse[];
  done: TaskResponse[];
}

export interface CriterionResult {
  id: string;
  text: string;
  passed: boolean;
  note?: string;
  line?: number | null;
}

export interface ChallengeResult {
  text: string;
  severity?: "low" | "medium" | "high" | string;
  line?: number | null;
}

export interface PathStepResult {
  kind: string;
  name: string;
  status: string;
  detail?: string;
}

export interface TaskTestsResult {
  status: "passed" | "failed" | "error" | "timeout" | "unavailable" | string;
  total: number;
  passed: number;
  failed_names: string[];
  detail: string;
}

export interface SubmissionReview {
  score: number;
  feedback: string;
  suggestions: string[];
  criteria?: CriterionResult[];
  challenges?: ChallengeResult[];
  agent_path?: PathStepResult[];
  tests?: TaskTestsResult | null;
}

export interface Submission {
  submission_id: number;
  user_id: number;
  task_id: number;
  code: string;
  status: string;
  review: SubmissionReview | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface ChatHistoryItem {
  id: string;
  role: "user" | "assistant" | string;
  text: string;
  sender?: string | null;
  created_at: string;
}

export interface ChatResponse {
  session_id: string;
  answer: string;
  speaker?: string;
  role?: string;
  mode?: "solo" | "huddle" | string;
  advisors?: string[];
  agent_path?: PathStepResult[];
}

export interface TemplateForStart {
  template_id: number;
}

export type AdminRole = "user" | "admin" | "superadmin";

export interface MyAdminRole {
  role: AdminRole;
}

export interface AdminUser {
  user_id: number;
  role: "admin" | "superadmin";
}

export interface ProjectTemplateTask {
  title: string;
  description: string;
  tests?: string;
}

export interface TemplateIssue {
  code: string;
  message: string;
  task: string;
}

export interface TemplateTaskReport {
  title: string;
  ok: boolean;
  attempts: number;
  tests_total: number;
  reference_passed: number;
  broken_failed: number;
  tests_kept: boolean;
  dropped: boolean;
  issues: TemplateIssue[];
}

export interface GeneratedSprint {
  order: number;
  sprint_title: string;
  project_title: string;
  project_description: string;
  tasks: ProjectTemplateTask[];
  ok: boolean;
  rounds: number;
  tests_ran: boolean;
  issues: TemplateIssue[];
  reports: TemplateTaskReport[];
  summary: string;
}

export interface GenerateSprintPayload {
  topic: string;
  direction: string;
  level: string;
  sprints: number;
  tasks_per_sprint: number;
  notes?: string;
  with_tests: boolean;
  order: number;
  used_titles: string[];
}

export interface ProjectTemplateSprint {
  order: number;
  title: string;
  tasks: ProjectTemplateTask[];
}

export interface CreateProjectTemplatePayload {
  project_template_id: null;
  title: string;
  description: string;
  direction: string;
  level: string;
  sprints: ProjectTemplateSprint[];
}

export interface UserSubmissionStats {
  total_submissions: number;
  reviewed_submissions: number;
  pending_submissions: number;
  failed_submissions: number;
  average_score: number | null;
  best_score: number | null;
  tasks_attempted: number;
}

export type TrajectoryAction =
  | "start"
  | "wait_review"
  | "revise"
  | "chat"
  | "close_ok"
  | "close_weak"
  | "next_task"
  | "hold_sprint"
  | "next_sprint"
  | string;

export type SkillStatus = "new" | "gap" | "learning" | "mastered" | "fading" | string;

export type FocusKind = "fix" | "learn" | "review" | "grow" | "stretch" | "prepare" | string;

export type RecommendationKind =
  | "fix"
  | "learn"
  | "review"
  | "practice"
  | "next_task"
  | "stretch"
  | string;

export interface TrajectorySkill {
  id: string;
  title: string;
  status: SkillStatus;
  mastery: number;
  predicted_success: number;
  retention: number;
  evidence: number;
  opportunities: number;
  last_practiced_at: string | null;
}

export interface TrajectoryFocus {
  skill_id: string;
  title: string;
  summary: string;
  kind: FocusKind;
  status: SkillStatus;
  mastery: number;
  predicted_success: number;
  why: string;
  steps: string[];
  mentor: string;
  mentor_name: string;
  ask: string;
  evidence: string[];
}

export interface TrajectoryRecommendation {
  kind: RecommendationKind;
  title: string;
  detail: string;
  skill_id: string | null;
  task_id: number | null;
  mentor: string | null;
  ask: string | null;
}

export interface UserTrajectory {
  mastery: number;
  difficulty: number;
  pace: number;
  readiness: number;
  action: TrajectoryAction;
  reason: string;
  block_close: boolean;
  block_next_sprint: boolean;
  window_tasks: number;
  reviewed_in_window: number;
  current_task_id: number | null;
  current_attempts: number;
  current_score: number | null;
  failed_criteria: string[];
  velocity?: number;
  readiness_threshold?: number;
  skills?: TrajectorySkill[];
  focus?: TrajectoryFocus | null;
  recommendations?: TrajectoryRecommendation[];
  next_task_id?: number | null;
  model?: string;
}

/** Короткое упражнение на навык, который начал забываться. */
export interface DrillOffer {
  drill_id: string;
  title: string;
  prompt: string;
  starter: string;
  minutes: number;
  skill_id: string;
  skill_title: string;
  kind: "review" | "gap" | string;
  reason: string;
  days_since: number;
  retention: number;
}

export interface DrillRunResult {
  status: "passed" | "failed" | "error" | "timeout" | string;
  total: number;
  passed: number;
  failed: number;
  failures: { name: string; message: string }[];
  detail: string;
  skill_id: string;
  recorded: boolean;
}

/** Сообщение, которое команда написала сама, без вопроса студента. */
export interface TeamNudge {
  sent: boolean;
  message: string;
  speaker_id: string;
  speaker_name: string;
  speaker_role: string;
  kind: "repeat" | "silence" | string;
  task_id: number | null;
}
