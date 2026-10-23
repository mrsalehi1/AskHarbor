/**
 * The AskHarbor panel at /admin: sign in, change the password when required,
 * pick a website you may edit, then edit its bot, settings, embed snippet and
 * backups. Admins also manage users, websites and who can access what.
 *
 * Plain TypeScript, no framework. Every view is a function that fills the
 * root element; state lives in a few module-level variables.
 */

import {
  ApiError,
  api,
  type AuditEntry,
  type CurrentUser,
  type UserSummary,
  type WebsiteAdminSummary,
  type WebsiteDetails,
  type WebsiteSummary,
} from "./admin-api";
import type { BotContentDocument } from "./content";
import { mountEditor, type EditorHandle } from "./editor-app";

type Children = (Node | string)[];

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> & { dataset?: Record<string, string> } = {},
  children: Children = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  const { dataset, ...rest } = props;
  Object.assign(node, rest);
  if (dataset) Object.assign(node.dataset, dataset);
  node.append(...children);
  return node;
}

function field(
  labelText: string,
  input: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
): HTMLElement {
  const id = `f-${Math.random().toString(36).slice(2, 9)}`;
  input.id = id;
  return el("p", { className: "field" }, [el("label", { htmlFor: id, textContent: labelText }), input]);
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export type Section = "content" | "settings" | "install" | "backup" | "activity";
type Page = { kind: "website"; slug: string; section: Section } | { kind: "users" } | { kind: "websites" } | { kind: "audit" } | { kind: "password" };

export interface AdminApp {
  /** For tests: the current page. */
  currentPage(): Page | null;
}

export function mountAdmin(root: HTMLElement): AdminApp {
  let me: CurrentUser | null = null;
  let websites: WebsiteSummary[] = [];
  let page: Page | null = null;
  let editor: EditorHandle | undefined;

  // --- shared helpers -------------------------------------------------------------

  async function guard<T>(work: () => Promise<T>): Promise<T | undefined> {
    try {
      return await work();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        me = null;
        renderLogin("Your session has ended. Please sign in again.");
        return undefined;
      }
      if (error instanceof ApiError && error.code === "password_change_required") {
        renderChangePassword(true);
        return undefined;
      }
      throw error;
    }
  }

  function notice(text: string, kind: "ok" | "error" = "ok"): HTMLElement {
    const node = el("p", { className: `notice ${kind}`, textContent: text });
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    return node;
  }

  // --- sign in ------------------------------------------------------------------------

  function renderLogin(message = ""): void {
    editor = undefined;
    const username = el("input", { type: "text", autocomplete: "username", required: true });
    const password = el("input", { type: "password", autocomplete: "current-password", required: true });
    const status = el("div", { className: "status-area" });
    if (message) status.append(notice(message, "error"));
    const form = el("form", { className: "card login", id: "login-form" }, [
      el("h1", { textContent: "Sign in to AskHarbor" }),
      field("Username", username),
      field("Password", password),
      el("button", { type: "submit", textContent: "Sign in", className: "primary" }),
      status,
    ]);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      status.replaceChildren();
      api
        .login(username.value.trim(), password.value)
        .then((user) => {
          me = user;
          if (user.must_change_password) renderChangePassword(true);
          else void renderShell();
        })
        .catch((error: unknown) => status.replaceChildren(notice(describe(error), "error")));
    });
    root.replaceChildren(el("main", { className: "centered" }, [form]));
    username.focus();
  }

  function renderChangePassword(forced: boolean): void {
    editor = undefined;
    const current = el("input", { type: "password", autocomplete: "current-password", required: true });
    const next = el("input", { type: "password", autocomplete: "new-password", required: true });
    const confirm = el("input", { type: "password", autocomplete: "new-password", required: true });
    const status = el("div", { className: "status-area" });
    const form = el("form", { className: "card login", id: "password-form" }, [
      el("h1", { textContent: forced ? "Choose a new password" : "Change your password" }),
      el("p", {
        className: "hint",
        textContent: forced
          ? "This account has a temporary password. Choose your own (at least 12 characters) before continuing."
          : "At least 12 characters. Your other sessions will be signed out.",
      }),
      field("Current password", current),
      field("New password", next),
      field("Repeat new password", confirm),
      el("button", { type: "submit", textContent: "Change password", className: "primary" }),
      ...(forced
        ? [el("button", { type: "button", textContent: "Sign out", className: "link", onclick: () => void signOut() })]
        : [el("button", { type: "button", textContent: "Cancel", className: "link", onclick: () => void renderShell() })]),
      status,
    ]);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      status.replaceChildren();
      if (next.value !== confirm.value) {
        status.append(notice("The new passwords do not match.", "error"));
        return;
      }
      void guard(() => api.changePassword(current.value, next.value))
        .then((user) => {
          if (!user) return;
          me = user;
          void renderShell();
        })
        .catch((error: unknown) => status.replaceChildren(notice(describe(error), "error")));
    });
    root.replaceChildren(el("main", { className: "centered" }, [form]));
    current.focus();
  }

  async function signOut(): Promise<void> {
    try {
      await api.logout();
    } finally {
      me = null;
      renderLogin("You have been signed out.");
    }
  }

  // --- the shell: navigation plus a main area ------------------------------------------

  const main = el("section", { className: "main", id: "main" });
  const nav = el("nav", { className: "sidebar" });

  async function renderShell(): Promise<void> {
    const list = await guard(() => api.websites());
    if (!list) return;
    websites = list;
    const current = page;
    if (!current || (current.kind === "website" && !websites.some((w) => w.slug === current.slug))) {
      page = websites[0] ? { kind: "website", slug: websites[0].slug, section: "content" } : me?.is_admin ? { kind: "websites" } : null;
    }
    renderNav();
    root.replaceChildren(el("div", { className: "shell" }, [nav, main]));
    await renderPage();
  }

  function renderNav(): void {
    const items: Node[] = [
      el("p", { className: "brand", textContent: "AskHarbor" }),
      el("p", { className: "who", textContent: `Signed in as ${me?.username ?? ""}${me?.is_admin ? " (admin)" : ""}` }),
      el("h2", { textContent: "Your websites" }),
    ];
    if (websites.length === 0) {
      items.push(el("p", { className: "hint", textContent: me?.is_admin ? "No websites yet. Create one under Websites." : "No websites assigned to you yet. Ask an admin." }));
    }
    for (const site of websites) {
      const active = page?.kind === "website" && page.slug === site.slug;
      items.push(
        el("button", {
          type: "button",
          className: `nav-item${active ? " active" : ""}`,
          textContent: site.domain ? `${site.name} · ${site.domain}` : site.name,
          dataset: { slug: site.slug },
          onclick: () => void go({ kind: "website", slug: site.slug, section: "content" }),
        }),
      );
    }
    if (me?.is_admin) {
      items.push(el("h2", { textContent: "Administration" }));
      for (const [label, kind] of [["Users", "users"], ["Websites", "websites"], ["Activity log", "audit"]] as const) {
        items.push(
          el("button", {
            type: "button",
            className: `nav-item${page?.kind === kind ? " active" : ""}`,
            textContent: label,
            dataset: { page: kind },
            onclick: () => void go({ kind }),
          }),
        );
      }
    }
    items.push(
      el("div", { className: "nav-footer" }, [
        el("button", { type: "button", className: "link", textContent: "Change password", onclick: () => renderChangePassword(false) }),
        el("button", { type: "button", className: "link", id: "logout-button", textContent: "Sign out", onclick: () => void signOut() }),
      ]),
    );
    nav.replaceChildren(...items);
  }

  async function go(next: Page): Promise<void> {
    page = next;
    renderNav();
    await renderPage();
  }

  async function renderPage(): Promise<void> {
    editor = undefined;
    if (!page) {
      main.replaceChildren(el("p", { className: "hint", textContent: "Nothing to show yet." }));
      return;
    }
    switch (page.kind) {
      case "website":
        await renderWebsite(page.slug, page.section);
        break;
      case "users":
        await renderUsers();
        break;
      case "websites":
        await renderWebsitesAdmin();
        break;
      case "audit":
        await renderAudit(undefined);
        break;
      case "password":
        renderChangePassword(false);
        break;
    }
  }

  // --- one website -----------------------------------------------------------------------

  async function renderWebsite(slug: string, section: Section): Promise<void> {
    const details = await guard(() => api.website(slug));
    if (!details) return;
    const tabs = el("div", { className: "tabs" });
    tabs.setAttribute("role", "tablist");
    for (const [label, key] of [["Questions and answers", "content"], ["Settings", "settings"], ["Install", "install"], ["Backup", "backup"], ["Activity", "activity"]] as const) {
      const tab = el("button", {
        type: "button",
        className: `tab${section === key ? " active" : ""}`,
        textContent: label,
        dataset: { section: key },
        onclick: () => void go({ kind: "website", slug, section: key }),
      });
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(section === key));
      tabs.append(tab);
    }
    const body = el("div", { className: "section-body", id: "section-body" });
    main.replaceChildren(
      el("header", { className: "page-header" }, [
        el("h1", { textContent: details.name }),
        el("p", { className: "hint", textContent: details.domain ? `${details.domain} · bot ID ${details.slug}` : `bot ID ${details.slug}` }),
      ]),
      tabs,
      body,
    );
    switch (section) {
      case "content":
        await renderContent(details, body);
        break;
      case "settings":
        renderSettings(details, body);
        break;
      case "install":
        renderInstall(details, body);
        break;
      case "backup":
        renderBackup(details, body);
        break;
      case "activity":
        await renderAudit(details.slug, body);
        break;
    }
  }

  async function renderContent(details: WebsiteDetails, body: HTMLElement): Promise<void> {
    const loaded = await guard(() => api.content(details.slug));
    if (!loaded) return;
    let revision = loaded.revision;
    const conflict = el("div", { className: "status-area", id: "conflict-area" });
    const editorRoot = el("div", { className: "editor-root", id: "editor-root" });
    body.replaceChildren(conflict, editorRoot);
    editor = mountEditor(editorRoot, {
      initialDocument: loaded.document,
      lockId: true,
      onSave: async (document: BotContentDocument) => {
        try {
          const result = await api.saveContent(details.slug, document, revision);
          revision = result.revision;
          conflict.replaceChildren();
          return `Saved revision ${revision}. The widget shows it now.`;
        } catch (error) {
          if (error instanceof ApiError && error.code === "revision_conflict") {
            const current = (error.detail as { current_revision: number }).current_revision;
            conflict.replaceChildren(
              notice(`Someone else saved revision ${current} while you were editing. Reload their version, then apply your change again. Nothing was saved.`, "error"),
              el("button", {
                type: "button",
                id: "reload-content",
                textContent: "Reload the latest version",
                onclick: () => {
                  void guard(() => api.content(details.slug)).then((fresh) => {
                    if (!fresh || !editor) return;
                    revision = fresh.revision;
                    editor.setDocument(fresh.document);
                    conflict.replaceChildren(notice(`Loaded revision ${revision}.`));
                  });
                },
              }),
            );
            throw new Error("Not saved: someone else saved first.");
          }
          if (error instanceof ApiError && error.status === 401) {
            me = null;
            renderLogin("Your session has ended. Please sign in again.");
          }
          throw error;
        }
      },
    });
  }

  function renderSettings(details: WebsiteDetails, body: HTMLElement): void {
    const name = el("input", { type: "text", value: details.name, maxLength: 80, required: true });
    const domain = el("input", { type: "text", value: details.domain ?? "", placeholder: "www.example.com" });
    const origins = el("textarea", { value: details.allowed_origins.join("\n"), rows: 4, placeholder: "https://www.example.com\nhttps://app.example.com" });
    const status = el("div", { className: "status-area" });
    const form = el("form", { className: "card", id: "settings-form" }, [
      el("h2", { textContent: "Website settings" }),
      field("Name shown in this panel", name),
      field("Domain name of your website", domain),
      el("p", { className: "hint", textContent: "The domain is shown in the panel to tell your websites apart. It does not change what the widget does." }),
      el("h2", { textContent: "Connection and CORS" }),
      field("Allowed origins, one per line", origins),
      el("p", {
        className: "hint",
        textContent:
          "Browsers only let the widget talk to this API from the origins listed here (scheme and host, no path). Leave the list empty to use the server's default. Changes apply within a couple of seconds.",
      }),
      el("button", { type: "submit", className: "primary", textContent: "Save settings" }),
      status,
    ]);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      status.replaceChildren();
      void guard(() =>
        api.updateSettings(details.slug, {
          name: name.value.trim(),
          domain: domain.value.trim(),
          allowed_origins: origins.value.split("\n").map((line) => line.trim()).filter(Boolean),
        }),
      )
        .then((updated) => {
          if (!updated) return;
          status.append(notice("Settings saved."));
          websites = websites.map((w) => (w.slug === updated.slug ? { slug: w.slug, name: updated.name, domain: updated.domain } : w));
          renderNav();
          main.querySelector("h1")!.textContent = updated.name;
        })
        .catch((error: unknown) => status.replaceChildren(notice(describe(error), "error")));
    });
    body.replaceChildren(form);
  }

  function renderInstall(details: WebsiteDetails, body: HTMLElement): void {
    const snippet = el("pre", { id: "embed-snippet", textContent: details.embed_snippet });
    const status = el("div", { className: "status-area" });
    const copy = el("button", {
      type: "button",
      className: "primary",
      textContent: "Copy snippet",
      onclick: () => {
        navigator.clipboard
          ?.writeText(details.embed_snippet)
          .then(() => status.replaceChildren(notice("Copied to the clipboard.")))
          .catch(() => status.replaceChildren(notice("Select the snippet and copy it by hand.", "error")));
      },
    });
    body.replaceChildren(
      el("section", { className: "card" }, [
        el("h2", { textContent: "Add AskHarbor to your website" }),
        el("p", { textContent: "Paste this snippet into your pages, just before the closing </body> tag (the footer). It also works in the <head> because the script waits for the page to load." }),
        snippet,
        copy,
        status,
        el("h2", { textContent: "Before it will work" }),
        el("ul", {}, [
          el("li", { textContent: `Add your website's origin (for example https://${details.domain || "www.example.com"}) under Settings → Allowed origins, or make sure the server default allows it.` }),
          el("li", { textContent: `The API address in the snippet is ${details.api_url}. If visitors reach the API through a different address, set ASKHARBOR_PUBLIC_URL on the server.` }),
          el("li", { textContent: "Save your questions and answers first; the widget shows the saved version." }),
        ]),
      ]),
    );
  }

  function renderBackup(details: WebsiteDetails, body: HTMLElement): void {
    const fileInput = el("input", { type: "file", accept: ".json,application/json", id: "backup-input" });
    const status = el("div", { className: "status-area", id: "backup-status" });
    fileInput.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        let payload: unknown;
        try {
          payload = JSON.parse(String(reader.result));
        } catch (error) {
          status.replaceChildren(notice(`'${file.name}' is not valid JSON: ${describe(error)}. Nothing was changed.`, "error"));
          return;
        }
        void guard(() => api.importBackup(details.slug, payload))
          .then((result) => {
            if (!result) return;
            status.replaceChildren(notice(`Imported '${file.name}' (${result.applied.join(" and ")}), now revision ${result.revision}.`));
          })
          .catch((error: unknown) => status.replaceChildren(notice(`'${file.name}' was not imported. Nothing was changed. ${describe(error)}`, "error")));
        fileInput.value = "";
      };
      reader.readAsText(file);
    });
    body.replaceChildren(
      el("section", { className: "card" }, [
        el("h2", { textContent: "Export a backup" }),
        el("p", { textContent: "Downloads every question, answer, the branding and this website's settings as one JSON file." }),
        el("a", { className: "button", id: "export-link", href: api.exportUrl(details.slug), textContent: "Download backup" }),
        el("h2", { textContent: "Import a backup" }),
        el("p", { textContent: "Choose a backup file, or a plain bot content file from the editor. It is checked completely first; if anything is wrong, nothing changes. The bot ID inside becomes this website's ID." }),
        fileInput,
        status,
      ]),
    );
  }

  async function renderAudit(slug: string | undefined, body: HTMLElement = main): Promise<void> {
    const entries = await guard(() => (slug ? api.websiteAudit(slug) : api.fullAudit()));
    if (!entries) return;
    body.replaceChildren(
      ...(slug ? [] : [el("header", { className: "page-header" }, [el("h1", { textContent: "Activity log" })])]),
      auditTable(entries),
    );
  }

  function auditTable(entries: AuditEntry[]): HTMLElement {
    const rows = entries.map((entry) =>
      el("tr", {}, [
        el("td", { textContent: formatTime(entry.at) }),
        el("td", { textContent: entry.username ?? "—" }),
        el("td", { textContent: entry.action }),
        el("td", { textContent: [entry.website_slug, entry.target_type && entry.target_id ? `${entry.target_type} ${entry.target_id}` : null].filter(Boolean).join(" · ") }),
        el("td", { textContent: entry.details ? JSON.stringify(entry.details) : "" }),
      ]),
    );
    return el("table", { className: "table", id: "audit-table" }, [
      el("thead", {}, [el("tr", {}, ["When", "Who", "Action", "Where", "Details"].map((h) => el("th", { textContent: h })))]),
      el("tbody", {}, rows.length ? rows : [el("tr", {}, [el("td", { colSpan: 5, textContent: "No activity yet." })])]),
    ]);
  }

  // --- administration ---------------------------------------------------------------------

  async function renderUsers(message?: string): Promise<void> {
    const users = await guard(() => api.users());
    if (!users) return;
    const status = el("div", { className: "status-area", id: "users-status" });
    if (message) status.append(notice(message));

    const username = el("input", { type: "text", required: true, placeholder: "username" });
    const password = el("input", { type: "text", required: true, placeholder: "temporary password (12+ characters)", autocomplete: "off" });
    const isAdmin = el("input", { type: "checkbox" });
    const createForm = el("form", { className: "card inline-form", id: "create-user-form" }, [
      el("h2", { textContent: "Create a user" }),
      field("Username", username),
      field("Temporary password", password),
      el("p", { className: "field checkbox" }, [el("label", {}, [isAdmin, " Administrator"])]),
      el("p", { className: "hint", textContent: "Tell the person the temporary password out of band. They must change it at first sign in." }),
      el("button", { type: "submit", className: "primary", textContent: "Create user" }),
    ]);
    createForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void guard(() => api.createUser(username.value.trim(), password.value, isAdmin.checked))
        .then((created) => {
          if (!created) return;
          void renderUsers(`User '${created.username}' created.`);
        })
        .catch((error: unknown) => status.replaceChildren(notice(describe(error), "error")));
    });

    const rows = users.map((user) => userRow(user, status));
    main.replaceChildren(
      el("header", { className: "page-header" }, [el("h1", { textContent: "Users" })]),
      status,
      el("table", { className: "table", id: "users-table" }, [
        el("thead", {}, [el("tr", {}, ["Username", "Role", "Status", "Websites", "Last sign in", "Actions"].map((h) => el("th", { textContent: h })))]),
        el("tbody", {}, rows),
      ]),
      createForm,
    );
  }

  function userRow(user: UserSummary, status: HTMLElement): HTMLElement {
    const self = user.username === me?.username;
    const act = (work: () => Promise<unknown>, done: string) => () =>
      void guard(work)
        .then((result) => {
          if (result === undefined) return;
          void renderUsers(done);
        })
        .catch((error: unknown) => status.replaceChildren(notice(describe(error), "error")));
    const actions = el("td", { className: "actions" });
    if (!self) {
      actions.append(
        el("button", {
          type: "button",
          textContent: user.is_active ? "Deactivate" : "Activate",
          dataset: { action: user.is_active ? "deactivate" : "activate", user: user.username },
          onclick: act(() => api.updateUser(user.id, { is_active: !user.is_active }), `'${user.username}' ${user.is_active ? "deactivated" : "activated"}.`),
        }),
        el("button", {
          type: "button",
          textContent: user.is_admin ? "Remove admin" : "Make admin",
          onclick: act(() => api.updateUser(user.id, { is_admin: !user.is_admin }), `'${user.username}' updated.`),
        }),
        el("button", {
          type: "button",
          textContent: "Reset password",
          dataset: { action: "reset", user: user.username },
          onclick: () => {
            const temporary = window.prompt(`Temporary password for '${user.username}' (12+ characters). Their sessions end and they must change it at sign in.`);
            if (!temporary) return;
            act(() => api.resetPassword(user.id, temporary), `Password for '${user.username}' reset.`)();
          },
        }),
      );
    } else {
      actions.textContent = "(you)";
    }
    return el("tr", { dataset: { user: user.username } }, [
      el("td", { textContent: user.username }),
      el("td", { textContent: user.is_admin ? "admin" : "editor" }),
      el("td", { textContent: `${user.is_active ? "active" : "deactivated"}${user.must_change_password ? ", must change password" : ""}` }),
      el("td", { textContent: user.websites.join(", ") || "—" }),
      el("td", { textContent: user.last_login_at ? formatTime(user.last_login_at) : "never" }),
      actions,
    ]);
  }

  async function renderWebsitesAdmin(message?: string): Promise<void> {
    const [sites, users] = (await guard(() => Promise.all([api.adminWebsites(), api.users()]))) ?? [];
    if (!sites || !users) return;
    const status = el("div", { className: "status-area", id: "websites-status" });
    if (message) status.append(notice(message));

    const slug = el("input", { type: "text", required: true, placeholder: "bot ID, e.g. shop" });
    const name = el("input", { type: "text", required: true, placeholder: "Harbor Shop" });
    const domain = el("input", { type: "text", placeholder: "www.example.com (optional)" });
    const createForm = el("form", { className: "card inline-form", id: "create-website-form" }, [
      el("h2", { textContent: "Create a website" }),
      field("Bot ID (used in the embed snippet, letters, digits, - and _)", slug),
      field("Name", name),
      field("Domain name", domain),
      el("button", { type: "submit", className: "primary", textContent: "Create website" }),
    ]);
    createForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void guard(() => api.createWebsite(slug.value.trim(), name.value.trim(), domain.value.trim()))
        .then(async (created) => {
          if (!created) return;
          websites = await api.websites();
          renderNav();
          void renderWebsitesAdmin(`Website '${created.slug}' created with a starter bot.`);
        })
        .catch((error: unknown) => status.replaceChildren(notice(describe(error), "error")));
    });

    const rows = sites.map((site) => websiteRow(site, users, status));
    main.replaceChildren(
      el("header", { className: "page-header" }, [el("h1", { textContent: "Websites" })]),
      status,
      el("table", { className: "table", id: "websites-table" }, [
        el("thead", {}, [el("tr", {}, ["Bot ID", "Name", "Domain", "Members", "Actions"].map((h) => el("th", { textContent: h })))]),
        el("tbody", {}, rows),
      ]),
      createForm,
    );
  }

  function websiteRow(site: WebsiteAdminSummary, users: UserSummary[], status: HTMLElement): HTMLElement {
    const refresh = async (message?: string) => {
      websites = await api.websites();
      renderNav();
      void renderWebsitesAdmin(message);
    };
    const members = el("td", { className: "members" });
    for (const username of site.members) {
      const user = users.find((u) => u.username === username);
      members.append(
        el("span", { className: "chip" }, [
          username,
          el("button", {
            type: "button",
            textContent: "×",
            title: `Remove ${username}`,
            dataset: { remove: username },
            onclick: () => {
              if (!user) return;
              void guard(() => api.removeMember(site.slug, user.id)).then((r) => r && refresh()).catch((e: unknown) => status.replaceChildren(notice(describe(e), "error")));
            },
          }),
        ]),
      );
    }
    const candidates = users.filter((u) => !site.members.includes(u.username) && !u.is_admin);
    if (candidates.length) {
      const select = el("select", { dataset: { addTo: site.slug } }, [
        el("option", { value: "", textContent: "Add user…" }),
        ...candidates.map((u) => el("option", { value: String(u.id), textContent: u.username })),
      ]);
      select.addEventListener("change", () => {
        const id = Number(select.value);
        if (!id) return;
        void guard(() => api.addMember(site.slug, id)).then((r) => r && refresh()).catch((e: unknown) => status.replaceChildren(notice(describe(e), "error")));
      });
      members.append(select);
    }
    members.append(el("span", { className: "hint", textContent: " Admins can always edit every website." }));
    return el("tr", { dataset: { site: site.slug } }, [
      el("td", { textContent: site.slug }),
      el("td", { textContent: site.name }),
      el("td", { textContent: site.domain ?? "—" }),
      members,
      el("td", { className: "actions" }, [
        el("button", { type: "button", textContent: "Open", onclick: () => void go({ kind: "website", slug: site.slug, section: "content" }) }),
        el("button", {
          type: "button",
          className: "danger",
          textContent: "Delete",
          dataset: { delete: site.slug },
          onclick: () => {
            if (!window.confirm(`Delete website '${site.slug}' and all of its questions and answers? Its widget will stop working. This cannot be undone.`)) return;
            void guard(() => api.deleteWebsite(site.slug))
              .then(() => refresh(`Website '${site.slug}' deleted.`))
              .catch((e: unknown) => status.replaceChildren(notice(describe(e), "error")));
          },
        }),
      ]),
    ]);
  }

  // --- start ------------------------------------------------------------------------------

  api
    .me()
    .then((user) => {
      me = user;
      if (user.must_change_password) renderChangePassword(true);
      else void renderShell();
    })
    .catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 503) {
        root.replaceChildren(el("main", { className: "centered" }, [el("div", { className: "card" }, [el("h1", { textContent: "Accounts are not configured" }), el("p", { textContent: describe(error) })])]));
        return;
      }
      renderLogin();
    });

  return { currentPage: () => page };
}
