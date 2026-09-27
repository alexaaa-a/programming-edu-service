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
}

export interface ChallengeResult {
  text: string;
  severity?: "low" | "medium" | "high" | string;
}

export interface PathStepResult {
  kind: string;
  name: string;
  status: string;
  detail?: string;
}

export interface SubmissionReview {
  score: number;
  feedback: string;
  suggestions: string[];
  criteria?: CriterionResult[];
  challenges?: ChallengeResult[];
  agent_path?: PathStepResult[];
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
}
