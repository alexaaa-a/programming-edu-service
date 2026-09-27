const ACCESS = "access_token";
const REFRESH = "refresh_token";

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
  const doomed: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (!key) continue;
    if (key.startsWith("chat_session_id") || key.startsWith("chat_messages:")) {
      doomed.push(key);
    }
  }
  for (const key of doomed) {
    localStorage.removeItem(key);
  }
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken());
}
