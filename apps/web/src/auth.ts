/**
 * Session handling for local accounts.
 *
 * The token this module stores is an opaque server-side session id. It carries
 * no claims, so nothing here decides what the account may do — `permissions`
 * comes from `GET /auth/me` and exists only so the UI can render a navigation
 * that matches what the server will allow. Editing it in devtools changes the
 * menu and nothing else: every endpoint re-checks on each request and answers
 * 403.
 */

import type { CurrentUser } from "./types";

const TOKEN_KEY = "cabqp.session";

type StoredSession = { access_token: string; expires_at?: string };

function apiUrl(path: string): string {
  return `/api/v1${path}`;
}

function readSession(): StoredSession | null {
  try {
    return JSON.parse(sessionStorage.getItem(TOKEN_KEY) || "null") as StoredSession | null;
  } catch {
    return null;
  }
}

function writeSession(session: StoredSession): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, JSON.stringify(session));
  } catch {
    /* Private-mode storage failures must not break sign-in. */
  }
}

function clearSession(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function getAccessToken(): string | null {
  return readSession()?.access_token || null;
}

function toCurrentUser(payload: any): CurrentUser {
  return {
    subject: payload.username,
    username: payload.username,
    displayName: payload.display_name || payload.username,
    isAdmin: Boolean(payload.is_admin),
    permissions: new Set<string>(payload.permissions || []),
    coverageGroups: new Set<string>(payload.coverage_groups || []),
    mustChangePassword: Boolean(payload.must_change_password),
    roles: new Set<string>(payload.roles || []),
  };
}

export class AuthError extends Error {}

export async function login(username: string, password: string): Promise<CurrentUser> {
  const response = await fetch(apiUrl("/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    let message = "Không thể đăng nhập. Vui lòng thử lại.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new AuthError(message);
  }

  const body = await response.json();
  writeSession({ access_token: body.access_token, expires_at: body.expires_at });
  return toCurrentUser(body.user);
}

/**
 * Re-read the signed-in account from the server.
 *
 * Called on boot and after any change that could alter authority, so a
 * permission an administrator revokes disappears from the UI without needing a
 * fresh sign-in. Returns null when the session is gone or no longer valid.
 */
export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const token = getAccessToken();
  if (!token) return null;
  try {
    const response = await fetch(apiUrl("/auth/me"), {
      headers: { Authorization: `Bearer ${token}` },
      credentials: "same-origin",
    });
    if (!response.ok) {
      clearSession();
      return null;
    }
    return toCurrentUser(await response.json());
  } catch {
    return null;
  }
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(apiUrl("/auth/change-password"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "same-origin",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  if (!response.ok) {
    let message = "Không thể đổi mật khẩu.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new AuthError(message);
  }
}

export async function logout(): Promise<void> {
  const token = getAccessToken();
  try {
    await fetch(apiUrl("/auth/logout"), {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      credentials: "same-origin",
    });
  } catch {
    // The server-side session may already be gone; clearing locally either way
    // is correct, and a stale token resolves to nothing on the next request.
  }
  clearSession();
  window.location.reload();
}

/** Whether the UI should offer a feature. Never the thing that permits it. */
export function can(user: CurrentUser | null, ...permissions: string[]): boolean {
  if (!user) return false;
  if (user.isAdmin) return true;
  return permissions.some((permission) => user.permissions.has(permission));
}
