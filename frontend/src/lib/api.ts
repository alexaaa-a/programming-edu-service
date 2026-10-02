import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "./auth-storage";
import { pushUnlocked } from "./unlocks";
import type {
  AdminUser,
  AuthResult,
  BoardResponse,
  Career,
  CareerLetter,
  ChatHistoryItem,
  ChatResponse,
  CreateProjectTemplatePayload,
  MyAdminRole,
  Sprint,
  Submission,
  TemplateForStart,
  UserSubmissionStats,
  UserShow,
  UserTrajectory,
} from "./types";

const base = () => import.meta.env.VITE_API_BASE_URL ?? "";

async function parseApiError(res: Response): Promise<string> {
  try {
    const j: unknown = await res.json();
    if (j && typeof j === "object" && "detail" in j) {
      const d = (j as { detail: unknown }).detail;
      if (typeof d === "string") return d;
      if (d && typeof d === "object" && !Array.isArray(d) && "message" in d) {
        const msg = (d as { message: unknown }).message;
        if (typeof msg === "string" && msg) return msg;
      }
      if (Array.isArray(d)) {
        return d
          .map((x) =>
            x && typeof x === "object" && "msg" in x
              ? String((x as { msg: string }).msg)
              : String(x),
          )
          .join(", ");
      }
    }
  } catch {
    /* ignore */
  }
  return res.statusText || "Ошибка запроса";
}

async function tryRefresh(): Promise<boolean> {
  const rt = getRefreshToken();
  if (!rt) return false;
  const res = await fetch(`${base()}/api/user/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
  });
  if (!res.ok) {
    clearTokens();
    return false;
  }
  const data = (await res.json()) as AuthResult;
  setTokens(data.access_token, data.refresh_token);
  return true;
}

export async function apiFetch(
  path: string,
  init: RequestInit & { json?: unknown } = {},
  allowRetry = true,
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const body =
    init.json !== undefined ? JSON.stringify(init.json) : init.body;

  let res = await fetch(`${base()}${path}`, {
    ...init,
    headers,
    body,
  });

  if (res.status === 401 && allowRetry && !path.includes("/auth/refresh")) {
    const ok = await tryRefresh();
    if (ok) {
      const h2 = new Headers(init.headers);
      const t2 = getAccessToken();
      if (t2) h2.set("Authorization", `Bearer ${t2}`);
      if (init.json !== undefined) h2.set("Content-Type", "application/json");
      res = await fetch(`${base()}${path}`, {
        ...init,
        headers: h2,
        body,
      });
    }
  }
  return res;
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<T>;
}

export async function postJson<T>(
  path: string,
  json?: unknown,
): Promise<T | void> {
  const res = await apiFetch(
    path,
    json === undefined ? { method: "POST" } : { method: "POST", json },
  );
  if (!res.ok) throw new Error(await parseApiError(res));
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return;
  }
  const text = await res.text();
  if (!text) return;
  return JSON.parse(text) as T;
}

export async function patchJson(path: string, json: unknown): Promise<void> {
  const res = await apiFetch(path, { method: "PATCH", json });
  if (!res.ok) throw new Error(await parseApiError(res));
}

export async function registerUser(body: {
  username: string;
  password: string;
  name: string;
  surname: string;
  email: string;
}): Promise<AuthResult> {
  const res = await apiFetch(
    "/api/user/v1/auth/register",
    { method: "POST", json: body },
    false,
  );
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<AuthResult>;
}

export async function loginUser(body: {
  email: string;
  password: string;
}): Promise<AuthResult> {
  const res = await apiFetch(
    "/api/user/v1/auth/login",
    { method: "POST", json: body },
    false,
  );
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<AuthResult>;
}

export async function getMe(): Promise<UserShow> {
  return getJson<UserShow>("/api/user/v1/users/me");
}

export async function updateProfile(partial: {
  name?: string;
  surname?: string;
  username?: string;
  email?: string;
  direction?: string;
  level?: string;
}): Promise<void> {
  await patchJson("/api/user/v1/users/me", partial);
}

export async function changePassword(body: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  await patchJson("/api/user/v1/users/me/password", body);
}

export async function getCurrentSprint(): Promise<Sprint> {
  return getJson<Sprint>("/api/task/v1/sprint/current");
}

export async function getTemplateForStart(): Promise<TemplateForStart> {
  return getJson<TemplateForStart>("/api/task/v1/project/template-for-start");
}

export async function startProject(templateId: number): Promise<void> {
  await postJson("/api/task/v1/project/start", { template_id: templateId });
}

export async function getCareer(): Promise<Career | null> {
  const res = await apiFetch("/api/task/v1/career");
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<Career>;
}

export async function getBoard(): Promise<BoardResponse> {
  return getJson<BoardResponse>("/api/task/v1/tasks/board");
}

export async function updateTaskStatus(
  taskId: number,
  status: string,
): Promise<{ close_quality?: string | null }> {
  const res = await apiFetch(`/api/task/v1/tasks/${taskId}/status`, {
    method: "PATCH",
    json: { status },
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = (await res.json().catch(() => ({}))) as {
    close_quality?: string | null;
    unlocked?: unknown;
  };
  pushUnlocked(data.unlocked);
  return { close_quality: data.close_quality ?? null };
}

export async function submitPeerReview(
  taskId: number,
  note: string,
): Promise<{ close_quality: string; emma: string }> {
  const res = await apiFetch(`/api/task/v1/tasks/${taskId}/peer-review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = (await res.json()) as {
    close_quality: string;
    emma: string;
    unlocked?: unknown;
  };
  pushUnlocked(data.unlocked);
  return { close_quality: data.close_quality, emma: data.emma };
}

export async function submitCode(taskId: number, code: string): Promise<number> {
  const res = await apiFetch("/api/submission/v1/submissions", {
    method: "POST",
    json: { task_id: taskId, code },
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<number>;
}

export async function getSubmission(submissionId: number): Promise<Submission> {
  return getJson<Submission>(
    `/api/submission/v1/submissions/${submissionId}`,
  );
}

export async function getTaskSubmissions(taskId: number): Promise<Submission[]> {
  const res = await apiFetch(`/api/submission/v1/tasks/${taskId}/submissions`);
  if (res.status === 404) return [];
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<Submission[]>;
}

export async function getMySubmissionStats(): Promise<UserSubmissionStats> {
  return getJson<UserSubmissionStats>("/api/submission/v1/submissions/me/stats");
}

export async function getMyTrajectory(taskId?: number | null): Promise<UserTrajectory> {
  const query =
    taskId != null && Number.isFinite(taskId)
      ? `?task_id=${encodeURIComponent(String(taskId))}`
      : "";
  return getJson<UserTrajectory>(`/api/submission/v1/submissions/me/trajectory${query}`);
}

export async function completeSprint(force = false): Promise<"letter" | "demo" | "closed"> {
  const headers: Record<string, string> = {};
  if (force) {
    headers["X-Confirm-Force-Sprint"] = "true";
  }
  const res = await apiFetch(`/api/task/v1/sprint/complete${force ? "?force=true" : ""}`, {
    method: "POST",
    headers,
  });
  if (res.status === 409) {
    try {
      const body: unknown = await res.json();
      const detail =
        body && typeof body === "object" && "detail" in body
          ? (body as { detail: unknown }).detail
          : null;
      if (detail && typeof detail === "object" && !Array.isArray(detail)) {
        const d = detail as {
          code?: unknown;
          message?: unknown;
          force_allowed?: unknown;
        };
        if (d.code === "hold") {
          throw new SprintHoldError(
            typeof d.message === "string" && d.message
              ? d.message
              : "Траектория ещё тяжёлая — рано открывать следующий спринт.",
            d.force_allowed === true,
          );
        }
      }
    } catch (e) {
      if (e instanceof SprintHoldError) throw e;
    }
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = (await res.json()) as { status?: string; unlocked?: unknown };
  pushUnlocked(data.unlocked);
  if (data.status === "letter" || data.status === "demo") return data.status;
  return "closed";
}

export async function submitFridayDemo(pitch: string, answer: string): Promise<CareerLetter> {
  const res = await apiFetch("/api/task/v1/career/demo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pitch, answer }),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = (await res.json()) as { letter?: CareerLetter; unlocked?: unknown };
  pushUnlocked(data.unlocked);
  if (!data.letter) throw new Error("Письмо не пришло");
  return data.letter;
}

export async function spendBonus(item: string, taskId?: number): Promise<Career> {
  const res = await apiFetch("/api/task/v1/career/spend", {
    method: "POST",
    json: { item, task_id: taskId ?? null },
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  // Покупка не присылает отдельный список новых бейджей: «Вложился в себя»
  // появится на панели целей при следующей загрузке карьеры.
  return res.json() as Promise<Career>;
}

export async function consumeEmmaSession(): Promise<Career> {
  const res = await apiFetch("/api/task/v1/career/consume", { method: "POST" });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<Career>;
}

export async function acceptCareerLetter(): Promise<void> {
  const res = await apiFetch("/api/task/v1/career/accept", { method: "POST" });
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = (await res.json().catch(() => ({}))) as { unlocked?: unknown };
  pushUnlocked(data.unlocked);
}

export class SprintHoldError extends Error {
  readonly forceAllowed: boolean;

  constructor(message: string, forceAllowed: boolean) {
    super(message);
    this.name = "SprintHoldError";
    this.forceAllowed = forceAllowed;
  }
}

export async function getChatHistory(taskId?: number): Promise<ChatHistoryItem[]> {
  const query = taskId != null ? `?task_id=${taskId}` : "";
  const res = await apiFetch(`/api/agents/v1/chat/history${query}`);
  if (!res.ok) throw new Error(await parseApiError(res));
  const data = (await res.json()) as { messages?: ChatHistoryItem[] };
  return Array.isArray(data.messages) ? data.messages : [];
}

export async function chatMessage(
  sessionId: string,
  message: string,
  context?: {
    task_title?: string;
    task_description?: string;
    task_id?: number;
    turn_id?: string;
    solo_only?: boolean;
    emma_briefing?: string;
  },
): Promise<ChatResponse> {
  const res = await apiFetch("/api/agents/v1/chat", {
    method: "POST",
    json: { session_id: sessionId, message, ...(context ?? {}) },
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json() as Promise<ChatResponse>;
}

export async function logoutRemote(): Promise<void> {
  const rt = getRefreshToken();
  try {
    if (rt) {
      await apiFetch(
        "/api/user/v1/auth/logout",
        { method: "POST", json: { refresh_token: rt } },
        false,
      );
    }
  } finally {
    clearTokens();
  }
}

export async function getMyAdminRole(): Promise<MyAdminRole> {
  return getJson<MyAdminRole>("/api/user/v1/users/admins/me/role");
}

export async function getAdmins(): Promise<AdminUser[]> {
  return getJson<AdminUser[]>("/api/user/v1/users/admins");
}

export async function addAdmin(userId: number): Promise<void> {
  await postJson("/api/user/v1/users/admins", { user_id: userId });
}

export async function removeAdmin(userId: number): Promise<void> {
  const res = await apiFetch(`/api/user/v1/users/admins/${userId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseApiError(res));
}

export async function createProjectTemplate(
  payload: CreateProjectTemplatePayload,
): Promise<void> {
  await postJson("/api/task/v1/project/template", payload);
}
