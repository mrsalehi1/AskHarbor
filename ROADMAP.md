# Roadmap

AskHarbor's next stage is a dependable guided FAQ tool that a site owner can configure and embed. The plan uses predefined answers and public reference content. It replaces the earlier AI and RAG direction.

## Starting point

The prototype at the start of this roadmap had a TypeScript widget, a FastAPI service, one fictional demo bot written in Python, basic API and widget tests, and a local example page. Since then, stages 1 to 3 have moved bot content into validated JSON files with a reload signal, added a second fictional bot, and added a local browser editor with a live preview and guarded import and export. The setup and CI added alongside this roadmap are preparation work and are excluded from the estimates below.

## 1. Make answer flows reliable

Estimated effort: 4 to 6 hours.

1. Fix the stale error messages described in [issue 1](https://github.com/mrsalehi1/AskHarbor/issues/1). A successful retry should clear the earlier failure without duplicating the question. **Done.** Fixed on `dev` with regression tests; the issue is closed.
2. Handle empty and incorrectly formatted origin settings with clear validation. See [issue 2](https://github.com/mrsalehi1/AskHarbor/issues/2) and [issue 3](https://github.com/mrsalehi1/AskHarbor/issues/3). **Done** on `dev` with regression tests. A blank value now stops startup with a clear error while an unset variable keeps the default (issue 2), and configured origins are normalized so spaces and trailing slashes no longer break CORS matching (issue 3).
3. Detect missing answer references instead of silently removing follow up options. See [issue 4](https://github.com/mrsalehi1/AskHarbor/issues/4). **Done** on `dev` with regression tests. Bot content is validated when it is built, and the error names the bot, the answer holding the bad reference and the missing option ID. If invalid content ever reaches the messages endpoint, it returns a 500 with the same details instead of dropping the option.
4. Read the API version from package metadata. See [issue 5](https://github.com/mrsalehi1/AskHarbor/issues/5). **Done** on `dev` with regression tests. The version shown in the API docs comes from the installed package metadata, with `pyproject.toml` as the fallback for a source checkout, so there is no second copy to keep in sync.
5. Add regression tests for the corrected behavior, including repeated failures and recovery. **Done.** Issues 1 to 6 have regression coverage, including a CORS test for the trailing slash case, the version fallback for a source checkout, and request limit recovery after the window resets.

Done when valid conversations still work, invalid content produces useful errors, and the existing issues have passing regression coverage.

## 2. Load bot content from files

Estimated effort: 6 to 8 hours.

1. Define a versioned JSON format for branding, opening questions, answer nodes and follow up choices. **Done** on `dev`: `format_version` 1, one bot per file, identity from `config.id`, opening labels taken from the answers, API responses unchanged.
2. Load a configured content file instead of editing Python to change answers. **Done.** `ASKHARBOR_CONTENT_DIR` selects the directory, defaulting to `server/content/`.
3. Validate duplicate IDs, missing references, empty labels, invalid colors and malformed files. **Done.** Also checks the format version, required fields, unknown keys, ID and color patterns and length caps, and reports every problem with its path. Invalid content stops startup with the full list.
4. Make import and reload atomic so rejected content leaves the last valid definition available. **Done** for reload: `SIGHUP` reloads every file and swaps the whole set only when all of them validate; otherwise the loaded content stays. Import belongs to the editor in stage 3.
5. Keep the fictional demo as an example and document how to create a second bot. **Done.** The demo moved to `server/content/demo.json`, a fictional Harbor Library bot was added, and shared validation fixtures in `fixtures/content/` are ready for the editor.

Done when two independent bots can be configured from files, valid content survives reload, and rejected changes leave existing content intact. Remaining limitations: reload is per process and not available on Windows, and there is no file watcher. See "Bot content" in the README.

## 3. Add a local content editor

Estimated effort: 8 to 12 hours.

1. Let a site owner edit branding, questions, answers and follow up choices in the browser. **Done** on `dev`: plain TypeScript forms over one draft document at `editor.html` in the widget build.
2. Show a draft conversation preview before exporting a bot definition. **Done.** The preview is the real widget reading from the draft through a local transport; embeds keep using HTTP unchanged.
3. Support JSON import and export using the same validation rules as the API. **Done.** The browser validation mirrors the server's paths and messages and both are tested against the shared fixtures in `fixtures/content/`.
4. Preserve the current draft when an import fails and explain the error. **Done.** Files are validated before they replace anything; a rejected import lists its problems and leaves the draft alone. Export is disabled while the draft is invalid.
5. Keep the editor local, using public or fictional FAQ content and browser file operations. **Done.** The editor makes no network requests; import and export use the browser's file dialogs.

Done when a user can create, preview, export and reload a complete bot without editing Python. Invalid imports must preserve the draft. The exported file must load successfully in the API. All three hold: a starter draft export is committed as a shared fixture the API tests load, and the flow was exercised end to end in a real browser. Out of scope for this stage, by design: autosave (closing the tab discards the draft) and a flow diagram.

## 4. Improve accessibility and browser behavior

Estimated effort: 4 to 6 hours.

1. Check opening, closing, Escape, keyboard focus and screen reader announcements.
2. Test narrow screens, long answers and long question labels.
3. Cover loading errors, delayed responses, retries and removal of the widget while a request is pending.
4. Add browser tests with a local API or controlled responses.

Done when the documented flows work with a keyboard and on mobile layouts, with browser tests for the important failure cases.

## 5. Make demonstration deployments repeatable

Estimated effort: 4 to 6 hours.

1. Package the API and static widget for a documented AWS demonstration deployment.
2. Keep infrastructure configuration in the repository and use placeholders for account specific settings.
3. Check the health endpoint during deployment and document rollback and cleanup.
4. Add configurable request limits, or enforce them at the deployment proxy, as described in [issue 6](https://github.com/mrsalehi1/AskHarbor/issues/6). **Partly done** on `dev`: the API enforces a configurable per client limit on the messages endpoint (default 30 per 60 seconds, `429` with `Retry-After`, in memory and bounded, no visitor identifiers) with tests for the limit and recovery. The README documents where the limit is enforced, how to configure it, what the `429` looks like, how retry works, and why it does not hold up with several workers or behind a reverse proxy. **Still pending:** proxy level enforcement for multi worker deployments and the deployment configuration that goes with it.
5. Use the fictional bot for deployment checks and document the host's request logging settings.

Done when a fresh deployment serves the widget and demo API, health checks succeed, and rollback and cleanup have been rehearsed. Cloud checks require a separately configured account; local development remains available without one.

## 6. Accounts, access control and database storage

Estimated effort: 30 to 44 hours, in four rounds.

AskHarbor grows from a single-owner tool into one service managing bots for several websites: an admin creates users and websites and assigns users to websites; after login a user sees only their websites and can edit only those bots. This stores the project's first credentials (password hashes and login sessions), which the data boundaries section below now reflects.

1. **Database foundation** (8 to 12 hours). PostgreSQL with SQLAlchemy 2 and Alembic migrations. Tables for users, sessions, websites, memberships and one validated JSONB bot document per website with a revision that detects conflicting saves. A batch import command moves the JSON content files into the database; file mode keeps working and the public API and bot IDs are unchanged. **Done** on `feat/database-foundation`: schema, migrations, revision-guarded saves, all-or-nothing import with skip-or-replace, database content mode with identical API responses, tests against real PostgreSQL in CI, and documentation. Login, the bootstrap admin and the admin pages are explicitly later rounds.
2. **Accounts and login** (10 to 14 hours). Argon2id password hashes, database-backed cookie sessions, a bootstrap admin created once from environment settings with a forced password change, login rate limiting, and CORS scoped to the public bot routes only. **Done** on `feat/login-sessions`: login, logout, `me` and password change endpoints; 12 hour sessions stored by token hash; Secure, HttpOnly, SameSite=Lax cookies; Origin and Referer checks plus JSON-only bodies against cross-site requests; failed-attempt limits per address and per username; a bootstrap admin created inside a PostgreSQL advisory lock so concurrent workers create exactly one, never touched again by restarts; production refusing the documented local credentials; and a websites listing as the first route behind the forced password change.
3. **Admin and connected editor** (8 to 12 hours). Admin API and pages for users, websites and memberships. The editor gains login, a website picker limited to accessible websites, and load and save against the server using the revision to detect conflicting saves. Import and export stay as browser file operations.
4. **Per website settings** (4 to 6 hours). Allowed origins per website enforced on the public routes, replacing the global list for database-backed bots.

Done when an admin can create users and websites and assign access, a user sees and edits only their own websites' bots, a restart never resets existing credentials, and the public widgets keep working throughout.

## Planning estimate

The remaining open work — stage 4, the rest of stage 5, and rounds 3 and 4 of stage 6 — is estimated at 20 to 30 hours, including implementation, tests and documentation. Rounds 1 and 2 of stage 6 are implemented and under review. These are planning estimates based on the current prototype. Update them as work is completed or a task changes.

Stage 1 is complete and merged to `dev`: issues 1 to 5 are fixed with regression tests. The API side of issue 6 (stage 5, item 4) is also on `dev`; proxy enforcement and deployment documentation are still pending. Stages 2 and 3 are complete and merged to `dev`: bot content is loaded from JSON files with validation and an atomic reload, and the local editor creates, previews, imports and exports those files with the same validation. Stage 4 has not started and the rest of stage 5 is still pending; their estimates are unchanged. Existing issue fixes are part of stage 1 and stage 5, rather than additional work counted twice.

## Data and product boundaries

Development examples use fictional content. Stage 6 adds site owner accounts: usernames, password hashes and login sessions for the people who edit bots. Visitors remain untracked — the plan still adds no visitor profiles, contact collection, stored conversations, customer datasets or regulated records. Request metadata at the hosting layer needs separate attention when testing a deployment.

Model training, model evaluation, AI inference infrastructure, document embeddings and RAG are outside this roadmap. Any later change in direction should be recorded explicitly before that work begins.
