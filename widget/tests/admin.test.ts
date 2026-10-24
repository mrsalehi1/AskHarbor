// @vitest-environment jsdom
// The panel against a small fake of the API: sign in, forced password change,
// website scoping, editing with revision conflicts, settings and admin pages.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mountAdmin } from "../src/admin-app";
import type { BotContentDocument } from "../src/content";
import { mountEditor, starterDraft } from "../src/editor-app";

type Json = Record<string, unknown>;

function fakeApi() {
  const state = {
    user: null as null | { username: string; is_admin: boolean; must_change_password: boolean },
    password: "ChangeMeLocal123!",
    revision: 1,
    document: { ...starterDraft(), config: { ...starterDraft().config, id: "demo" } },
    settings: { name: "AskHarbor", domain: null as string | null, allowed_origins: [] as string[] },
    users: [{ id: 1, username: "admin", is_admin: true, is_active: true, must_change_password: false, created_at: "2026-01-01T00:00:00Z", last_login_at: null, websites: [] }],
    calls: [] as { method: string; path: string; body: unknown }[],
  };
  const json = (status: number, body: unknown) =>
    new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(String(init.body)) as Json) : undefined;
    state.calls.push({ method, path, body });
    const needsUser = () => (state.user ? null : json(401, { detail: "Not signed in." }));
    if (path === "/api/v1/auth/me") return needsUser() ?? json(200, state.user);
    if (path === "/api/v1/auth/login") {
      if (body?.username === "admin" && body?.password === state.password) {
        state.user = { username: "admin", is_admin: true, must_change_password: state.password === "ChangeMeLocal123!" };
        return json(200, state.user);
      }
      return json(401, { detail: "Invalid username or password." });
    }
    if (path === "/api/v1/auth/logout") {
      state.user = null;
      return json(204, null);
    }
    if (path === "/api/v1/auth/password") {
      if (body?.current_password !== state.password) return json(400, { detail: "The current password is not correct." });
      state.password = String(body?.new_password);
      state.user = { ...state.user!, must_change_password: false };
      return json(200, state.user);
    }
    const denied = needsUser();
    if (denied) return denied;
    if (state.user?.must_change_password) return json(403, { detail: { code: "password_change_required", message: "Change your password." } });
    if (path === "/api/v1/websites") return json(200, [{ slug: "demo", name: state.settings.name, domain: state.settings.domain }]);
    if (path === "/api/v1/websites/demo" && method === "GET")
      return json(200, { slug: "demo", ...state.settings, revision: state.revision, api_url: "https://faq.example.com", widget_url: "https://faq.example.com/admin/askharbor.js", embed_snippet: '<script src="https://faq.example.com/admin/askharbor.js" data-api-url="https://faq.example.com" data-bot-id="demo" defer></script>', members: [], can_manage: true });
    if (path === "/api/v1/websites/demo" && method === "PATCH") {
      if ((body?.allowed_origins as string[]).some((o) => !o.startsWith("http"))) return json(422, { detail: "'bad' is not an origin." });
      Object.assign(state.settings, body);
      return json(200, { slug: "demo", ...state.settings, revision: state.revision, api_url: "", widget_url: "", embed_snippet: "", members: [], can_manage: true });
    }
    if (path === "/api/v1/websites/demo/content" && method === "GET") return json(200, { document: state.document, revision: state.revision });
    if (path === "/api/v1/websites/demo/content" && method === "PUT") {
      if (body?.revision !== state.revision) return json(409, { detail: { code: "revision_conflict", current_revision: state.revision, message: "stale" } });
      state.document = body?.document as typeof state.document;
      state.revision += 1;
      return json(200, { revision: state.revision });
    }
    if (path === "/api/v1/websites/demo/audit") return json(200, []);
    if (path === "/api/v1/admin/users" && method === "GET") return json(200, state.users);
    if (path === "/api/v1/admin/users" && method === "POST") {
      const created = { id: state.users.length + 1, username: String(body?.username), is_admin: Boolean(body?.is_admin), is_active: true, must_change_password: true, created_at: "2026-01-02T00:00:00Z", last_login_at: null, websites: [] };
      state.users.push(created);
      return json(201, created);
    }
    if (path === "/api/v1/admin/websites") return json(200, [{ id: 1, slug: "demo", name: state.settings.name, domain: state.settings.domain, allowed_origins: [], members: [] }]);
    if (path === "/api/v1/admin/audit") return json(200, [{ id: 1, at: "2026-01-01T00:00:00Z", username: "admin", action: "login", target_type: null, target_id: null, website_slug: null, details: null, client_address: "127.0.0.1" }]);
    return json(404, { detail: `unhandled ${method} ${path}` });
  });
  return { state, fetchMock };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 8; i += 1) await new Promise((r) => setTimeout(r, 5));
}

function type(selector: string, value: string): void {
  const input = document.querySelector<HTMLInputElement>(selector)!;
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function text(selector: string): string {
  return document.querySelector(selector)?.textContent ?? "";
}

describe("admin panel", () => {
  let state: ReturnType<typeof fakeApi>["state"];

  beforeEach(() => {
    const fake = fakeApi();
    state = fake.state;
    vi.stubGlobal("fetch", fake.fetchMock);
    document.body.replaceChildren(document.createElement("div"));
  });

  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  async function signIn(password = "ChangeMeLocal123!") {
    mountAdmin(document.body.firstElementChild as HTMLElement);
    await settle();
    expect(document.querySelector("#login-form")).not.toBeNull();
    const inputs = document.querySelectorAll<HTMLInputElement>("#login-form input");
    inputs[0]!.value = "admin";
    inputs[1]!.value = password;
    document.querySelector("#login-form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle();
  }

  async function finishPasswordChange(next = "a-much-longer-password-1") {
    const inputs = document.querySelectorAll<HTMLInputElement>("#password-form input");
    inputs[0]!.value = state.password;
    inputs[1]!.value = next;
    inputs[2]!.value = next;
    document.querySelector("#password-form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle();
  }

  it("shows the sign in form and reports a wrong password", async () => {
    await signIn("nope-nope-nope");
    expect(text("#login-form .notice")).toContain("Invalid username or password.");
    expect(state.user).toBeNull();
  });

  it("forces the password change before anything else and rejects mismatches", async () => {
    await signIn();
    expect(document.querySelector("#password-form")).not.toBeNull();
    expect(text("#password-form h1")).toBe("Choose a new password");
    expect(document.querySelector(".sidebar")).toBeNull();

    const inputs = document.querySelectorAll<HTMLInputElement>("#password-form input");
    inputs[0]!.value = state.password;
    inputs[1]!.value = "a-much-longer-password-1";
    inputs[2]!.value = "different-password-12";
    document.querySelector("#password-form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle();
    expect(text("#password-form .notice")).toContain("do not match");

    await finishPasswordChange();
    expect(document.querySelector(".sidebar")).not.toBeNull();
    expect(text(".sidebar .who")).toContain("admin (admin)");
    expect(state.password).toBe("a-much-longer-password-1");
  });

  it("opens the first website in the editor with the ID locked and saves with the revision", async () => {
    await signIn();
    await finishPasswordChange();
    expect(document.querySelector('.nav-item[data-slug="demo"]')?.classList.contains("active")).toBe(true);
    expect(document.querySelector("#editor-root #bot-form")).not.toBeNull();
    const idField = document.querySelector<HTMLInputElement>('[data-path="config.id"]')!;
    expect(idField.readOnly).toBe(true);
    expect(idField.value).toBe("demo");

    type('[data-path="config.greeting"]', "Changed in the panel.");
    document.querySelector<HTMLButtonElement>("#save-button")!.click();
    await settle();

    expect(text("#save-status")).toContain("Saved revision 2");
    const save = state.calls.find((c) => c.method === "PUT");
    expect((save?.body as { revision: number }).revision).toBe(1);
    expect(state.document.config.greeting).toBe("Changed in the panel.");
  });

  it("explains a revision conflict and reloads the other person's version", async () => {
    await signIn();
    await finishPasswordChange();
    // Someone else saves meanwhile.
    state.revision = 5;
    state.document = { ...state.document, config: { ...state.document.config, greeting: "Theirs." } };

    type('[data-path="config.greeting"]', "Mine.");
    document.querySelector<HTMLButtonElement>("#save-button")!.click();
    await settle();

    expect(text("#conflict-area")).toContain("Someone else saved revision 5");
    expect(text("#save-status")).toContain("Not saved");
    expect(state.document.config.greeting).toBe("Theirs.");

    document.querySelector<HTMLButtonElement>("#reload-content")!.click();
    await settle();
    expect(document.querySelector<HTMLInputElement>('[data-path="config.greeting"]')!.value).toBe("Theirs.");
    expect(text("#conflict-area")).toContain("Loaded revision 5");
  });

  it("edits settings and shows the embed snippet", async () => {
    await signIn();
    await finishPasswordChange();
    document.querySelector<HTMLButtonElement>('.tab[data-section="settings"]')!.click();
    await settle();
    const form = document.querySelector("#settings-form")!;
    const inputs = form.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>("input, textarea");
    inputs[1]!.value = "www.example.com";
    inputs[2]!.value = "https://www.example.com\nbad";
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle();
    expect(text("#settings-form .notice")).toContain("is not an origin");

    inputs[2]!.value = "https://www.example.com\n";
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle();
    expect(text("#settings-form .notice")).toContain("Settings saved.");
    expect(state.settings.domain).toBe("www.example.com");
    expect(state.settings.allowed_origins).toEqual(["https://www.example.com"]);
    expect(text('.nav-item[data-slug="demo"]')).toContain("www.example.com");

    document.querySelector<HTMLButtonElement>('.tab[data-section="install"]')!.click();
    await settle();
    expect(text("#embed-snippet")).toContain('data-bot-id="demo"');
    expect(text("#section-body")).toContain("https://www.example.com");
  });

  it("lets an admin create a user from the users page and signs out", async () => {
    await signIn();
    await finishPasswordChange();
    document.querySelector<HTMLButtonElement>('.nav-item[data-page="users"]')!.click();
    await settle();
    expect(document.querySelectorAll("#users-table tbody tr")).toHaveLength(1);

    const form = document.querySelector("#create-user-form")!;
    const inputs = form.querySelectorAll<HTMLInputElement>("input");
    inputs[0]!.value = "editor";
    inputs[1]!.value = "temporary-password-123";
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle();
    expect(text("#users-status")).toContain("User 'editor' created.");
    expect(document.querySelectorAll("#users-table tbody tr")).toHaveLength(2);
    expect(text('tr[data-user="editor"]')).toContain("must change password");

    document.querySelector<HTMLButtonElement>("#logout-button")!.click();
    await settle();
    expect(document.querySelector("#login-form")).not.toBeNull();
    expect(state.user).toBeNull();
  });
});

describe("editor server options", () => {
  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
  });

  it("starts from the given document, locks the ID, saves through onSave and accepts setDocument", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network")));
    const initial = { ...starterDraft(), config: { ...starterDraft().config, id: "shop" } };
    const onSave = vi.fn(async (_document: BotContentDocument) => "Saved!");
    const root = document.createElement("div");
    document.body.append(root);
    const editor = mountEditor(root, { initialDocument: initial, lockId: true, onSave });

    expect(root.querySelector<HTMLInputElement>('[data-path="config.id"]')!.readOnly).toBe(true);
    root.querySelector<HTMLButtonElement>("#save-button")!.click();
    await settle();
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0]![0].config.id).toBe("shop");
    expect(root.querySelector("#save-status")?.textContent).toBe("Saved!");

    editor.setDocument({ ...initial, config: { ...initial.config, name: "Replaced" } });
    expect(root.querySelector<HTMLInputElement>('[data-path="config.name"]')!.value).toBe("Replaced");
    expect(editor.getDraft().config.name).toBe("Replaced");
  });

  it("has no save button without onSave", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network")));
    const root = document.createElement("div");
    document.body.append(root);
    mountEditor(root);
    expect(root.querySelector("#save-button")).toBeNull();
  });
});
