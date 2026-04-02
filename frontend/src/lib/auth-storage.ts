const ACCESS = "access_token";
const REFRESH = "refresh_token";
const CHAT_SESSION_PREFIX = "chat_session_id";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH);
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS, access);
  localStorage.setItem(REFRESH, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken());
}

export function getChatSessionId(scope: string = "general"): string {
  const key = `${CHAT_SESSION_PREFIX}:${scope}`;
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

export function setChatSessionId(scope: string, sessionId: string): void {
  localStorage.setItem(`${CHAT_SESSION_PREFIX}:${scope}`, sessionId);
}
