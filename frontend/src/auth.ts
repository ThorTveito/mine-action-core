import type { Permission, Role } from "./types";

const KEY = "mac.token";

// localStorage can throw (private mode, blocked storage); the app must work without it.
export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

// UI hints only. The API enforces permissions; this just avoids offering actions that will fail.
// Keep in sync with ROLE_PERMISSIONS in backend/app/auth.py.
const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  viewer: [],
  surveyor: ["report"],
  editor: ["write", "import", "report", "view_reports"],
  qa_officer: ["qa", "release", "view_reports"],
  admin: ["write", "import", "qa", "release", "delete", "manage_users", "report", "view_reports"],
};

export const roleCan = (role: Role | undefined, permission: Permission): boolean =>
  role !== undefined && ROLE_PERMISSIONS[role].includes(permission);

export const ROLE_LABEL: Record<Role, string> = {
  viewer: "Viewer",
  surveyor: "Field surveyor",
  editor: "Editor (IM officer)",
  qa_officer: "QA officer",
  admin: "Admin",
};
