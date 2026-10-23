/** Thin client for the AskHarbor account, website and admin routes. */

import type { BotContentDocument, ContentProblem } from "./content";

export interface CurrentUser {
  username: string;
  is_admin: boolean;
  must_change_password: boolean;
}

export interface WebsiteSummary {
  slug: string;
  name: string;
  domain: string | null;
}

export interface WebsiteDetails extends WebsiteSummary {
  allowed_origins: string[];
  revision: number;
  api_url: string;
  widget_url: string;
  embed_snippet: string;
  members: string[];
  can_manage: boolean;
}

export interface UserSummary {
  id: number;
  username: string;
  is_admin: boolean;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at: string | null;
  websites: string[];
}

export interface WebsiteAdminSummary {
  id: number;
  slug: string;
  name: string;
  domain: string | null;
  allowed_origins: string[];
  members: string[];
}

export interface AuditEntry {
  id: number;
  at: string;
  username: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  website_slug: string | null;
  details: Record<string, unknown> | null;
  client_address: string | null;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(ApiError.describe(status, detail));
  }

  static describe(status: number, detail: unknown): string {
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const record = detail as Record<string, unknown>;
      if (typeof record.message === "string") return record.message;
      if (Array.isArray(record.problems)) {
        return (record.problems as ContentProblem[])
          .map((problem) => `${problem.path || "(document)"}: ${problem.message}`)
          .join("; ");
      }
    }
    return `Request failed (${status})`;
  }

  get code(): string | undefined {
    const record = this.detail as Record<string, unknown> | null;
    return record && typeof record.code === "string" ? record.code : undefined;
  }

  get problems(): ContentProblem[] {
    const record = this.detail as Record<string, unknown> | null;
    return record && Array.isArray(record.problems) ? (record.problems as ContentProblem[]) : [];
  }
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let payload: unknown = undefined;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }
  if (!response.ok) {
    const detail = (payload as { detail?: unknown } | undefined)?.detail ?? payload;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export const api = {
  me: () => request<CurrentUser>("GET", "/api/v1/auth/me"),
  login: (username: string, password: string) =>
    request<CurrentUser>("POST", "/api/v1/auth/login", { username, password }),
  logout: () => request<void>("POST", "/api/v1/auth/logout"),
  changePassword: (current_password: string, new_password: string) =>
    request<CurrentUser>("POST", "/api/v1/auth/password", { current_password, new_password }),

  websites: () => request<WebsiteSummary[]>("GET", "/api/v1/websites"),
  website: (slug: string) => request<WebsiteDetails>("GET", `/api/v1/websites/${slug}`),
  updateSettings: (slug: string, body: Partial<Pick<WebsiteDetails, "name" | "domain" | "allowed_origins">>) =>
    request<WebsiteDetails>("PATCH", `/api/v1/websites/${slug}`, body),
  content: (slug: string) =>
    request<{ document: BotContentDocument; revision: number }>("GET", `/api/v1/websites/${slug}/content`),
  saveContent: (slug: string, document: BotContentDocument, revision: number) =>
    request<{ revision: number }>("PUT", `/api/v1/websites/${slug}/content`, { document, revision }),
  importBackup: (slug: string, payload: unknown) =>
    request<{ revision: number; applied: string[] }>("POST", `/api/v1/websites/${slug}/import`, payload),
  websiteAudit: (slug: string) => request<AuditEntry[]>("GET", `/api/v1/websites/${slug}/audit`),
  exportUrl: (slug: string) => `/api/v1/websites/${slug}/export`,

  users: () => request<UserSummary[]>("GET", "/api/v1/admin/users"),
  createUser: (username: string, password: string, is_admin: boolean) =>
    request<UserSummary>("POST", "/api/v1/admin/users", { username, password, is_admin }),
  updateUser: (id: number, body: { is_active?: boolean; is_admin?: boolean }) =>
    request<UserSummary>("PATCH", `/api/v1/admin/users/${id}`, body),
  resetPassword: (id: number, new_password: string) =>
    request<UserSummary>("POST", `/api/v1/admin/users/${id}/password`, { new_password }),
  adminWebsites: () => request<WebsiteAdminSummary[]>("GET", "/api/v1/admin/websites"),
  createWebsite: (slug: string, name: string, domain: string) =>
    request<WebsiteAdminSummary>("POST", "/api/v1/admin/websites", { slug, name, domain }),
  deleteWebsite: (slug: string) => request<void>("DELETE", `/api/v1/admin/websites/${slug}`),
  addMember: (slug: string, user_id: number) =>
    request<WebsiteAdminSummary>("POST", `/api/v1/admin/websites/${slug}/members`, { user_id }),
  removeMember: (slug: string, user_id: number) =>
    request<WebsiteAdminSummary>("DELETE", `/api/v1/admin/websites/${slug}/members/${user_id}`),
  fullAudit: () => request<AuditEntry[]>("GET", "/api/v1/admin/audit"),
};
