import type { NavigateFunction } from "react-router";

let _navigate: NavigateFunction | null = null;

export function setAppNavigate(fn: NavigateFunction): void {
  _navigate = fn;
}

export function appNavigate(
  to: string,
  options?: { replace?: boolean; state?: unknown },
): void {
  if (_navigate) {
    _navigate(to, { replace: options?.replace, state: options?.state });
  } else {
    window.location.assign(to);
  }
}
