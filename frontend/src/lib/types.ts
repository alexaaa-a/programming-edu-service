export type TaskStatus = "todo" | "in_progress" | "review" | "done";

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
}

export interface BoardResponse {
  todo: TaskResponse[];
  in_progress: TaskResponse[];
  review: TaskResponse[];
  done: TaskResponse[];
}

export interface SubmissionReview {
  score: number;
  feedback: string;
  suggestions: string[];
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

export interface ChatResponse {
  session_id: string;
  answer: string;
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
