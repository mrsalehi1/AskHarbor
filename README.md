# AskHarbor

AskHarbor adds a small guided FAQ widget to a website. Visitors choose a question and receive a predefined answer, with follow up choices when needed. It is for site owners who want to publish common answers without building a support interface from scratch.

The browser widget uses TypeScript and Shadow DOM. A Python FastAPI service supplies the branding, questions and answers.

## Current status

AskHarbor is a small multi-website service. With PostgreSQL configured, an admin creates users and websites and assigns users to websites; each user signs in to the panel at `/admin/`, sees only their websites, and edits each one's questions and answers, branding, domain name and allowed origins, copies the embed snippet, and exports or imports backups. Two fictional sample bots are loaded at first start. Start with the [quick start](#quick-start-from-a-fresh-checkout); details are under [The panel](#the-panel) and [Accounts and login](#accounts-and-login).

Without a database the server still works as a single-owner tool: bots come from JSON files in `server/content/` (see [Bot content](#bot-content)) and the standalone editor at `editor.html` edits those files (see [Content editor](#content-editor)). The widget, its retry and back to menu behavior, origin validation and the per client request limit work the same in both setups. Automated tests cover the API, the configuration rules, the content format, the accounts and the browser code. Deployment automation is planned work; the [roadmap](ROADMAP.md) separates it from the features available today.

The active product plan is guided FAQ support using public reference content. Earlier AI and RAG ideas are outside this plan. The current code does not call a model or retrieve documents.

## Quick start from a fresh checkout

Everything below runs on a fresh Ubuntu machine with a clone of this repository. The full setup uses PostgreSQL and gives you the panel at `/admin/`; the shorter file mode at the end needs no database.

### 1. System packages

```bash
sudo apt update
sudo apt install git python3 python3-venv python3-pip nodejs npm postgresql
```

Ubuntu's `python3-venv` is required or the virtual environment fails with an `ensurepip` error. Check `node --version` reports 22 or newer; if not, install Node.js 22 from [nodejs.org](https://nodejs.org/) or with `nvm`. Python 3.11 or newer is required.

### 2. PostgreSQL role and databases

Ubuntu starts PostgreSQL automatically on `127.0.0.1:5432` (check with `pg_isready`). Create a role and the application database:

```bash
sudo -u postgres createuser --pwprompt askharbor     # enter the password askharbor for local use
sudo -u postgres createdb --owner askharbor askharbor
```

For the test suite, also create a disposable test database and give the role the `CREATEDB` right while you run the tests (one test creates and drops an extra empty database to check the startup refusal):

```bash
sudo -u postgres createdb --owner askharbor askharbor_test
sudo -u postgres psql -c 'ALTER ROLE askharbor CREATEDB'
# after testing, if you prefer the role without it:
sudo -u postgres psql -c 'ALTER ROLE askharbor NOCREATEDB'
```

These are local development names and passwords. A deployment chooses its own and passes them through the environment.

### 3. API: environment, dependencies, migrations

From the repository root:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cp .env.example .env
```

Open `server/.env` and set the database URL and, for plain `http://` on your own machine, the cookie flag:

```bash
ASKHARBOR_DATABASE_URL=postgresql+psycopg://askharbor:askharbor@127.0.0.1:5432/askharbor
ASKHARBOR_COOKIE_SECURE=false
```

Then create the schema:

```bash
python -m alembic upgrade head
```

Every schema change ships as a migration; run the same command after pulling a new version. The server refuses to start if the database is behind.

### 4. Frontend build

In a second terminal, from the repository root:

```bash
cd widget
npm ci
npm run build
```

This produces `widget/dist/` with the widget bundle `askharbor.js`, the panel `admin.html` + `admin.js`, the standalone editor and the example page. The API serves this directory at `/admin/`, so rebuild after changing the frontend.

### 5. Start and sign in

Back in the first terminal (environment active, inside `server/`):

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The log shows the first start doing three things once: `Bootstrap admin 'admin' created`, `Sample bots loaded into the empty database`, and `Application startup complete`. Open [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) and sign in with the local development account:

| Username | Password |
| :--- | :--- |
| `admin` | `ChangeMeLocal123!` |

You are asked for a new password (12 characters or more) before anything else appears. After that the sidebar lists the two fictional sample websites, `demo` (AskHarbor) and `library` (Harbor Library). The example page at [http://127.0.0.1:8000/admin/index.html](http://127.0.0.1:8000/admin/index.html) embeds the `demo` bot from this same server, so you can see edits appear in a real widget.

### 6. What to try

1. **Edit and save.** Open `demo`, change the greeting, press **Save**. The status reads `Saved revision 2`; reload the example page and the widget shows the new greeting.
2. **Conflicting saves.** Open the same website in a second tab, save a change there, then save in the first tab. The first tab reports that someone else saved a newer revision, nothing is overwritten, and one click loads their version so you can apply your edit again.
3. **Users and access.** Under *Users*, create `editor` with a temporary password. Under *Websites*, add `editor` to `library`. Sign out, sign in as `editor`: a forced password change, then a sidebar with only `library`. The API answers `404` for anything else, not just the panel hiding it.
4. **Domain and CORS.** On a website's *Settings* tab enter your site's domain name and the exact origins that may load the widget, such as `https://www.example.com`. Within two seconds the public bot routes answer CORS only for those origins.
5. **Embed.** The *Install* tab shows the script snippet with the API address and bot ID filled in. See [Embed the widget](#embed-the-widget).
6. **Backup and restore.** The *Backup* tab downloads one JSON file with settings and content and imports one back, checked completely before anything changes.
7. **Recovery and reset.** `python -m app.create_admin NAME` from `server/` creates an admin on purpose, for example after every admin was deactivated. Deleting the sample websites is permanent; they are only loaded into an empty database.

### Without PostgreSQL (file mode)

Skip steps 2 and 3's database lines. Without `ASKHARBOR_DATABASE_URL` the API serves the bots from the JSON files in `server/content/` and the panel answers that accounts are not configured. Run the API as in step 5 and serve the built widget separately:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory widget/dist
```

Open [http://127.0.0.1:4173/](http://127.0.0.1:4173/) for the example page (it talks to the API on port 8000; `server/.env.example` allows that origin) and [http://127.0.0.1:4173/editor.html](http://127.0.0.1:4173/editor.html) for the standalone editor, which edits content files in the browser and never contacts the server. Content changes are picked up with `kill -HUP $(pgrep -f "uvicorn app.main:app")`; see [Bot content](#bot-content).

To check the widget's failure handling in either mode: stop the API, choose a question (one error line with the question offered again as a retry, never stacking), restart the API, choose it again and the error disappears. The **Menu** button in the panel header returns to the opening questions and discards a pending reply.

## Embed the widget

The *Install* tab of each website in the panel shows the exact snippet for that website. It has this shape:

```html
<script
  src="https://faq.example.com/admin/askharbor.js"
  data-api-url="https://faq.example.com"
  data-bot-id="demo"
  defer
></script>
```

Paste it before the closing `</body>` tag (the footer) or in `<head>`; the script waits for the page to load. `data-bot-id` is the website's bot ID. The API serves the widget bundle at `/admin/askharbor.js`, so no separate file hosting is needed, and `ASKHARBOR_PUBLIC_URL` sets the address shown when visitors reach the API through a different host than you do.

**Which pages may load the bot** is decided by the website's allowed origins (panel, *Settings*) when it has any, otherwise by the server wide `ASKHARBOR_ALLOWED_ORIGINS`. Both are lists of exact origins, scheme and host only, for example `https://www.example.com`; spaces and trailing slashes are trimmed, ports are kept, paths are not supported. `ASKHARBOR_ALLOWED_ORIGINS` accepts `*` to allow any origin, which is meant for local development only. Leaving it unset means `*`; setting it to an empty value stops the server with an error, because an empty list would block every visitor.

The widget sends a selected option ID to the API and nothing else: no free text field, no visitor account, no transcript. Hosting services can still record request metadata.

The `create({ apiUrl, botId, container? })` function is also exported for applications that import the TypeScript source.

## API

| Endpoint | Behavior |
| :--- | :--- |
| `GET /health` | Returns `{"status":"ok"}`. |
| `GET /api/v1/bots/{bot_id}` | Returns the branding, greeting and opening questions. |
| `POST /api/v1/bots/{bot_id}/messages` | Accepts `{"option_id":"getting-started"}` and returns an answer with follow up choices. |

The messages endpoint is rate limited per client address. Over the limit it returns `429` with a `Retry-After` header giving the whole seconds until the client's window resets, and a detail of the form `Too many requests. Try again in N seconds.` Health checks and the bot configuration endpoint are never limited. See [Request limits](#request-limits).

Unknown bots return `404`. Unknown option IDs return `400`. Invalid request fields return `422`.

The version shown at `/docs` and in `/openapi.json` is read from the installed package metadata, falling back to `server/pyproject.toml` for a source checkout. To release a new API version, change the `version` field in `server/pyproject.toml` only. Bot content is validated when the server starts and on every reload, see [Bot content](#bot-content). If content with a missing follow up reference ever reaches the messages endpoint anyway, it returns a 500 naming the bot, the answer and the missing ID instead of dropping the button.

## Bot content

Each bot is one JSON file in the content directory. The default directory is `server/content/`, which ships with the fictional `demo` and `library` bots. Set `ASKHARBOR_CONTENT_DIR` in the environment or in `server/.env` to use another directory. The variable must not be blank; remove it to get the default back.

**Identity.** The bot ID is `config.id` inside the file, not the file name. It appears in the widget's `data-bot-id` attribute and in the API path. Two files with the same `config.id` are rejected together.

**Format.** This is the shape of a file, trimmed from `server/content/demo.json`:

```json
{
  "format_version": 1,
  "config": {
    "id": "demo",
    "name": "AskHarbor",
    "greeting": "Hi! What can I help you with?",
    "launcher_label": "Open support chat",
    "primary_color": "#155eef",
    "opening_option_ids": ["getting-started", "contact"]
  },
  "answers": [
    {
      "id": "getting-started",
      "label": "How do I get started?",
      "answer": "Add the AskHarbor script before your closing body tag.",
      "next_option_ids": ["contact"]
    },
    {
      "id": "contact",
      "label": "How can I contact support?",
      "answer": "Email your support team at support@example.com."
    }
  ]
}
```

| Field | Meaning |
| :--- | :--- |
| `format_version` | Always `1`. Other values are rejected so an older server never misreads a newer file. |
| `config.id` | Bot ID. Letters, digits, `-` and `_`, starting with a letter or digit, at most 100 characters. |
| `config.name`, `config.greeting`, `config.launcher_label` | Panel title, first message, and the launcher button's accessible label. Plain text, not blank. |
| `config.primary_color` | Hex color, `#rgb` or `#rrggbb`. |
| `config.opening_option_ids` | The questions shown with the greeting, in order. At least one. Each must be an answer `id`. |
| `answers[].id` | Option ID, same rules as the bot ID. Unique within the file. |
| `answers[].label` | The button text for this question, also used when it is an opening question. At most 200 characters. |
| `answers[].answer` | The reply, plain text up to 4000 characters. Line breaks are kept; links and markup are not interpreted. |
| `answers[].next_option_ids` | Follow up questions offered after this answer, in order. Optional. Each must be an answer `id`. |

Opening labels are taken from the matching answer, so a question's text lives in one place. Unknown keys are rejected rather than ignored, so a misspelled key such as `next_options_ids` is reported instead of silently dropping the follow ups. The API responses are unchanged: `GET /api/v1/bots/{bot_id}` still returns `options` with `id` and `label`, built from `opening_option_ids`.

**Validation.** Every file is checked for malformed JSON and UTF-8, the format version, required fields, blank text, the ID and color patterns, length caps, duplicate answer IDs, duplicate entries in an option list, and opening or follow up options with no matching answer. Each problem is reported with the file, a path such as `answers[1].next_option_ids[0]` and a short reason. All problems in all files are listed at once, not just the first.

**Startup.** If any file is invalid, the server refuses to start and prints the full list:

```text
AskHarbor cannot start because the bot content in /path/to/content is invalid. Fix the files below or point ASKHARBOR_CONTENT_DIR at a valid directory.
Bot content was rejected (1 file with problems):
  /path/to/content/shop.json
    config.primary_color: must be a hex color like #155eef or #fff
    answers[0].next_option_ids[0]: follow up option 'pricng' has no matching answer
```

An empty directory or a directory that does not exist is also an error.

**Reload without a restart.** Send `SIGHUP` to the uvicorn process. The server reads every file again and swaps the complete set in one step only if all of them validate. Otherwise it logs the problems in the same format and keeps serving the content that was already loaded, so a half finished edit never takes a bot offline.

```bash
kill -HUP $(pgrep -f "uvicorn app.main:app")
```

A successful reload logs `Content reloaded from <directory>: demo, library`. A rejected one logs `Content reload rejected, keeping the N bot(s) already loaded (...)` followed by the problems. There is no HTTP endpoint for reloading, by design: the API has no authentication, and a reload endpoint would let anyone on the network trigger file reads.

**Adding a bot.** Create one in the [content editor](#content-editor) and export it, or copy `server/content/library.json` and change `config.id` and the content. Keep it fictional or public, then restart or send the reload signal. The widget embed for the new bot uses its `config.id` in `data-bot-id`. The shared fixtures in `fixtures/content/` show valid and invalid examples with the problems each one should produce; the editor and the API are both tested against the same files so they agree on what is valid.

**Limitations.**

- The reload signal is meant for the single process command shown in the quick start. With `uvicorn --reload`, the supervisor process does not handle `SIGHUP` and exits, so send the signal only to the child worker, or restart. With `uvicorn --workers N`, each worker holds its own copy and uvicorn treats `SIGHUP` to the supervisor as a request to restart every worker; the new workers validate the content at startup and fail if it is invalid. In both cases `pgrep -f "uvicorn app.main:app"` returns more than one process, so pick the PID deliberately.
- `SIGHUP` does not exist on Windows. The server logs a warning at startup and runs without the reload signal; restart it to pick up changes.
- Answers are plain text. Links, markdown and HTML are shown literally.
- Answers that no opening or follow up option can reach are allowed and not reported.
- The content directory is read once per startup or reload. There is no file watcher.

## PostgreSQL storage

With `ASKHARBOR_DATABASE_URL` set, bots are served from PostgreSQL and edited in the panel; without it they come from the content files. `ASKHARBOR_CONTENT_SOURCE` can force `files` or `database`. The public endpoints and the bot IDs are identical in both modes. Installing PostgreSQL and creating the role and databases is step 2 of the [quick start](#quick-start-from-a-fresh-checkout).

**What is stored.** One `websites` row per bot, where the `slug` is the public bot ID, with the website's name, domain name and allowed origins. Each website has one bot document, the same validated JSON as a content file, in a JSONB column with a `revision` number. Accounts live in `users`, logins in `sessions`, access in `website_members`, failed login counters in `login_attempts`, every change in `audit_log`, and durable markers such as bootstrap completion in `system_state`.

**Conflicting saves.** Every save names the revision it started from and increases it by one. If two people edit the same website, the second save finds a newer revision, writes nothing and answers `409` with the current revision. The panel shows who-saved-first wording and a button that loads the newer version, so the second person reapplies their change on top of it instead of silently undoing the first.

**Migrations.** `python -m alembic upgrade head` from `server/` creates or updates the schema. At startup the server checks that the database is at the current migration and refuses to start otherwise, naming the command to run. The URL comes from `ASKHARBOR_DATABASE_URL` in the environment or `server/.env`.

**Sample data.** On the first start with no websites at all, the two fictional bots in `server/content/` are loaded as the websites `demo` and `library`, together with the bootstrap admin and inside the same database lock, so several workers starting together load them once. They are never loaded again while any website exists; deleting them in the panel is permanent. `ASKHARBOR_SEED_SAMPLE_CONTENT=false` turns the seeding off.

**Importing content files.** `python -m app.import_content [directory] [--replace]` loads a directory of content files as websites: the whole directory is validated first, everything commits in one transaction, existing bot IDs are skipped unless `--replace` is given. This is how the sample data is loaded and how a set of files from the standalone editor gets into the database.

**Testing against PostgreSQL.** The database tests run only when `ASKHARBOR_TEST_DATABASE_URL` points at a disposable database. They drop and recreate its `public` schema, migrate from scratch with Alembic and truncate tables between tests, so never point this at a database you want to keep. One test creates and drops an extra empty database, which needs the `CREATEDB` right on the role for the duration of the test run (quick start, step 2):

```bash
cd server
ASKHARBOR_TEST_DATABASE_URL=postgresql+psycopg://askharbor:askharbor@127.0.0.1:5432/askharbor_test python -m pytest
```

Without the variable those tests are skipped and the rest of the suite runs as before. CI runs them against a PostgreSQL 16 service container. A schema drift test fails when the SQLAlchemy models and the migrations stop describing the same tables.

**Limitations.**

- The standalone `editor.html` edits files, not the database; use the panel for database-backed websites, or export from one and import into the other.
- Database mode queries PostgreSQL on each request (with a small per revision cache for the built definition). Fine at demo scale, unmeasured beyond it.

## Accounts and login

Accounts are available whenever `ASKHARBOR_DATABASE_URL` is set and the migrations have run, in either content mode. Without a database the account routes answer `503` with an explanation and the widget is unaffected. Users sign in with a username and password; admins create users and websites and decide who may edit what, in [the panel](#the-panel) or through the API below.

**Local development account.** On the first start, when bootstrap has never run and the `users` table is empty, the server creates one admin:

| Setting | Default | Variable |
| :--- | :--- | :--- |
| Username | `admin` | `ASKHARBOR_BOOTSTRAP_ADMIN_USERNAME` |
| Password | `ChangeMeLocal123!` (development only) | `ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD` |

The account starts with a forced password change: until it is changed, every route except login, logout, `GET /api/v1/auth/me` and the password change itself answers `403` with the code `password_change_required`, and the panel shows nothing but the change form. The bootstrap runs in every worker at startup inside a PostgreSQL advisory lock, so several workers starting together still create exactly one admin.

**Bootstrap runs once, and that is recorded on its own.** Completion is written to the `system_state` table in the same transaction as the admin. From then on the bootstrap never runs again: a restart does not recreate the account or reset a changed password, and deleting every user later does not bring the documented account back either. Databases created before this marker existed are recognized by their users and marked as completed at the next start. If every admin is ever lost, recover deliberately with `python -m app.create_admin NAME` from `server/` (`--reset` to repurpose an existing user); it asks for a temporary password, or reads `ASKHARBOR_NEW_ADMIN_PASSWORD`, and the account must change it at first sign in.

**Production.** Set `ASKHARBOR_ENV=production`. For the first start, supply `ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD` (12 characters or more; the username is optional). The server refuses to start while that variable holds the documented local password or a shorter one, or while `ASKHARBOR_COOKIE_SECURE` is false, and names the variable to fix without echoing its value. After the first admin exists, remove the variable: the server starts normally without it because completion is recorded in the database. A production database that has no accounts and no bootstrap password refuses to start and says so, rather than creating an account with a known password.

**Endpoints.** All under `/api/v1`. Every route except the first four requires a session whose password change is done; the admin routes also require `is_admin`; the website routes require admin or membership and answer `404` otherwise.

| Endpoint | Behavior |
| :--- | :--- |
| `POST /auth/login` | JSON `{"username","password"}`. Sets the session cookie and returns `{"username","is_admin","must_change_password"}`. Wrong name and wrong password get the same `401`. |
| `POST /auth/logout` | Revokes the session in the database and clears the cookie. `204`. |
| `GET /auth/me` | The signed in user, including whether a password change is still required. |
| `POST /auth/password` | JSON `{"current_password","new_password"}`. Checks the current password, applies the policy, clears the forced change and signs out the user's other sessions. |
| `GET /websites`, `GET /websites/{slug}` | The user's websites; details include the allowed origins, the current revision and the embed snippet. |
| `PATCH /websites/{slug}` | Name, domain and allowed origins. Origins must be `scheme://host[:port]`. |
| `GET`/`PUT /websites/{slug}/content` | The bot document with its revision. `PUT` sends `{"document","revision"}` and answers `409` with the current revision when stale, `422` with the shared problem list when invalid. |
| `GET /websites/{slug}/export`, `POST /websites/{slug}/import` | Backup download and restore. |
| `GET /websites/{slug}/audit` | This website's audit log. |
| `GET`/`POST /admin/users`, `PATCH /admin/users/{id}`, `POST /admin/users/{id}/password` | Manage users; the last one sets a temporary password. |
| `GET`/`POST /admin/websites`, `DELETE /admin/websites/{slug}` | Manage websites. |
| `POST /admin/websites/{slug}/members`, `DELETE /admin/websites/{slug}/members/{user_id}` | Manage access. |
| `GET /admin/audit` | The full audit log. |

**Passwords.** Hashed with Argon2id (the `argon2-cffi` defaults: 64 MiB, 3 passes) and never stored or logged in clear. New passwords must be 12 to 200 characters and differ from the current one; there are no composition rules. A login for an unknown username still runs a hash check against a dummy hash, so the response time does not reveal which accounts exist.

**Sessions.** A login creates a database row and a cookie named `askharbor_session` holding a random 256-bit token; the row stores only the token's SHA-256. Sessions last 12 hours (`ASKHARBOR_SESSION_HOURS`), end on logout, and all other sessions of a user end when that user changes their password. Expired or revoked rows are cleaned up at startup. Because sessions live in the database, every worker sees the same logins and a logout is immediate everywhere.

**Cookies and cross-site protection.** The cookie is `HttpOnly`, `SameSite=Lax`, `Path=/` and `Secure`. For plain `http://127.0.0.1` development set `ASKHARBOR_COOKIE_SECURE=false`; production refuses that. Three layers stop cross-site requests: the browser does not attach a `Lax` cookie to cross-site POSTs; the login, logout and password routes compare the `Origin` (or `Referer`) host with the `Host` header and answer `403` on a mismatch; and the login and password bodies must be JSON, which an HTML form cannot send. CORS applies only to `/health` and `/api/v1/bots/`, never to account routes, so an origin allowed for the widget cannot call them with the owner's cookie.

**Login rate limit.** Failed attempts are counted per client address and per username, 5 per 5 minutes by default (`ASKHARBOR_LOGIN_RATE_LIMIT`, `ASKHARBOR_LOGIN_RATE_WINDOW_SECONDS`). While over the limit even a correct password gets `429` with `Retry-After`. Successful logins do not consume the budget. The counters live in the `login_attempts` table, so they are shared by every worker and instance. Behind a reverse proxy the client address is still the proxy's, so all visitors share one address budget there; the per username budget still applies.

**Audit log.** Sign ins, failed sign ins, sign outs, password changes and every admin, settings, content and backup action are recorded in the `audit_log` table with the user, time, client address, target and what changed. Users see their websites' entries in the panel; admins see everything.

**Try it locally.** With PostgreSQL migrated as described above and the API started with `ASKHARBOR_DATABASE_URL` set and `ASKHARBOR_COOKIE_SECURE=false`:

```bash
curl -c cookies.txt -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"ChangeMeLocal123!"}' http://127.0.0.1:8000/api/v1/auth/login
curl -b cookies.txt http://127.0.0.1:8000/api/v1/websites        # 403 password_change_required
curl -b cookies.txt -H 'Content-Type: application/json' \
  -d '{"current_password":"ChangeMeLocal123!","new_password":"pick-a-long-local-passphrase"}' \
  http://127.0.0.1:8000/api/v1/auth/password
curl -b cookies.txt http://127.0.0.1:8000/api/v1/websites        # 200, lists imported websites
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/v1/auth/logout
```

## The panel

The panel is served by the API itself at `/admin/` from the built widget output (`npm run build` in `widget/`, location `ASKHARBOR_ADMIN_DIST`, default `widget/dist`). Serving it from the API's own origin keeps the session cookie first party. It needs accounts, so `ASKHARBOR_DATABASE_URL` must be set; see [Accounts and login](#accounts-and-login) for the local admin account.

**For every user:**

- **Sign in, forced password change, sign out.** A temporary password (the bootstrap admin's, a newly created user's, or one set by an admin reset) must be changed before anything else appears.
- **Your websites.** The sidebar lists the websites you may edit: all of them for an admin, your memberships otherwise. The API enforces the same rule on every route, and a website you cannot access answers `404`.
- **Questions and answers.** The editor from `editor.html`, with the bot ID locked to the website and a **Save** button. Saves carry the revision you loaded; if someone saved first you are told, nothing is overwritten, and one click loads their version so you can apply your change again. The public widget serves the saved version immediately. File import and export still work inside the editor.
- **Settings.** The name shown in the panel, your website's domain name (informational), and the **connection and CORS** list: the exact origins (`https://www.example.com`) allowed to load this bot. Empty means the server default `ASKHARBOR_ALLOWED_ORIGINS` applies. Changes take effect within a couple of seconds on every worker.
- **Install.** The script snippet to paste before `</body>` (or in `<head>`), with the API address and bot ID filled in, plus a copy button. The widget bundle itself is served at `/admin/askharbor.js`. If visitors reach the API through another address than you do, set `ASKHARBOR_PUBLIC_URL`.
- **Backup.** Download one JSON file with settings and content, or import a backup (or a plain bot content file). An import is validated completely first and changes nothing when it fails; the bot ID inside becomes this website's ID, so a backup can move content between websites.
- **Activity.** The audit log for this website.

**For admins:**

- **Users.** Create users with a temporary password, deactivate and reactivate, grant or remove admin, reset a password. Deactivation and a reset end the user's sessions at once; a reset user signs in with the temporary password and must change it. You cannot deactivate yourself or drop your own admin access.
- **Websites.** Create a website (it gets a starter bot so its widget works at once), delete one, and manage who can access it.
- **Activity log.** Every sign in, failed sign in, password change, user and website change, membership change, settings change, content save and backup action, with who, when, from which address, and what changed.

**Sample data.** On the first start with an empty database the two fictional bots from `server/content/` are loaded as websites `demo` and `library`, so you can try the panel immediately. They are only ever loaded when there are no websites at all, so deleting them sticks across restarts. Set `ASKHARBOR_SEED_SAMPLE_CONTENT=false` to never load them.

**Local walkthrough.** With PostgreSQL migrated and the widget built:

```bash
cd server
ASKHARBOR_DATABASE_URL=postgresql+psycopg://askharbor:askharbor@127.0.0.1:5432/askharbor \
ASKHARBOR_COOKIE_SECURE=false \
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/), sign in as `admin` / `ChangeMeLocal123!`, choose a new password, and the `demo` and `library` websites are ready to edit. The example page at [http://127.0.0.1:8000/admin/index.html](http://127.0.0.1:8000/admin/index.html) embeds the `demo` bot from the same server.

## Production checklist

- `ASKHARBOR_ENV=production`. Refuses the development defaults described above.
- `ASKHARBOR_DATABASE_URL` pointing at your PostgreSQL, migrated with `python -m alembic upgrade head` before each start of a new version.
- `ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD` set only for the first start, then removed.
- HTTPS in front of the API. The session cookie is `Secure`, `HttpOnly`, `SameSite=Lax` and `ASKHARBOR_COOKIE_SECURE` must stay true; if TLS ends at a proxy, the Origin check only compares the host, so it keeps working.
- `ASKHARBOR_PUBLIC_URL` set to the address visitors use, so embed snippets are right.
- `ASKHARBOR_ALLOWED_ORIGINS` set to your sites, or rely on per website origins in the panel. Never `*` in production.
- `ASKHARBOR_ADMIN_DIST` pointing at a built `widget/dist` from the same version.
- `ASKHARBOR_SEED_SAMPLE_CONTENT=false` unless you want the fictional sample websites.
- A reverse proxy limit on `POST /api/v1/auth/login` and the messages route in addition to the built in ones; behind a proxy all visitors share the proxy's client address.

## Content editor

`editor.html` in the built widget output is a local, single page editor for one bot at a time. Build the widget and serve `widget/dist` as in the quick start, then open [http://127.0.0.1:4173/editor.html](http://127.0.0.1:4173/editor.html). Everything happens inside the browser tab: the editor makes no network requests, so it works without the API and nothing you type leaves the machine.

**Forms.** Plain input fields for the branding, the greeting, the launcher label and the color, plus one section per answer with its ID, question label, answer text and follow up choices. Opening questions and follow ups are chosen from the existing answer IDs and can be reordered or removed. Buttons add and remove whole answers.

**Validation.** The draft is checked on every keystroke with the same rules, paths and messages as the API, so a problem reads the same in the browser as in a server log, for example `answers[1].next_option_ids[0]: follow up option 'pricng' has no matching answer`. Problems are listed next to the form and the offending fields are outlined. The TypeScript and Python validators are tested against the same shared cases in `fixtures/content/`, so they cannot quietly drift apart.

**Preview.** The preview in the corner is the real widget, not an imitation: the same code that runs on a host page, reading from your draft through a local transport instead of HTTP. Open it with the launcher button and click through the conversation, including follow ups, errors for removed answers, and the back to menu button. The preview updates when you leave a field or change the structure. While the draft has problems, the last valid draft stays in the preview and a note says so.

**Import.** Choose a JSON file with the import control. The file is validated completely before anything changes: a file that is malformed or breaks a rule is reported with the same problem list and the draft you were working on is untouched. A valid file replaces the draft and the forms and preview follow.

**Export.** The export button downloads the draft as `<bot id>.json`, in exactly the format the server reads, and is disabled while the draft has problems, so an invalid file cannot be produced. An imported file that is exported unchanged is byte for byte identical. Put the exported file in the content directory and restart or send the reload signal; the automated tests load an editor export through the API to keep this true.

**Limitations.**

- One bot per editor tab. Several bots mean several files, imported one at a time.
- No autosave. The draft lives in the page; reloading or closing the tab discards it. Export early and often.
- The editor edits content, not server settings. Origins, limits and the content directory stay in `server/.env`.
- Answer text is plain text, exactly as the widget shows it.
- There is no flow diagram; the conversation structure is visible through the follow up lists and the preview.

## Request limits

**Where the limit is enforced.** Inside the API process itself, on `POST /api/v1/bots/{bot_id}/messages` only. It is applied before the bot or option is looked up, so even unknown options count toward the budget. `GET /health` and `GET /api/v1/bots/{bot_id}` are never limited. There is no proxy or gateway configuration in this repository yet; see the caveats below for when you need one.

**Default.** 30 requests per client address per 60 second window. Answers are predefined and a visitor following a guided conversation sends one request per click, so an ordinary session stays far below this.

**How to configure it.** Set these in the environment or in `server/.env`:

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `ASKHARBOR_MESSAGE_RATE_LIMIT` | `30` | Requests allowed per client address within one window. `0` disables the limit. Negative or non numeric values stop the server at startup. |
| `ASKHARBOR_MESSAGE_RATE_WINDOW_SECONDS` | `60` | Length of the window in seconds. Must be at least 1. |

For example, to allow 10 requests every 30 seconds:

```bash
ASKHARBOR_MESSAGE_RATE_LIMIT=10
ASKHARBOR_MESSAGE_RATE_WINDOW_SECONDS=30
```

**What a rejected request looks like.** The first request over the limit, and every further one until the window resets, receives:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
Content-Type: application/json

{"detail":"Too many requests. Try again in 42 seconds."}
```

`Retry-After` is the whole number of seconds, at least 1, until the client's current window ends, so it shrinks on each rejected attempt. Rejected requests do not extend the window.

**How retry works.** The window is fixed, not sliding. The first request from an address opens a window, later requests in that window are counted, and once the window length has passed the next request opens a fresh window with a full budget. The widget treats a `429` like any other failed request: it shows "Sorry, the answer could not be loaded. Please try again." with the same question offered as a single retry button, and the visitor can also use the menu button to start over. The widget does not read `Retry-After` and does not wait automatically, so a visitor who retries straight away sees the same message until the window resets. Repeated retries never stack errors or duplicate the question.

**What the limiter stores.** One fixed window counter per client address, in process memory, capped at 10000 entries. Expired windows are evicted first, then the oldest live one. Nothing is written to disk, no visitor IDs, cookies or profiles are created, and the counters disappear when the process stops.

**What does not hold up with more than one worker.** Each uvicorn worker process keeps its own counters. With `--workers 4` a client can send roughly four times the configured limit, a request rejected by one worker may be accepted by the next, and `Retry-After` values from different workers disagree. The same applies to several instances behind a load balancer.

**What does not hold up behind a reverse proxy.** The client address is taken from the TCP connection. `X-Forwarded-For` and `Forwarded` are not read, so behind a reverse proxy, CDN or load balancer every visitor appears as the proxy's address and all of them share one budget. That is far too strict for real traffic and would block legitimate visitors.

**Recommendation beyond a single process demo.** Enforce the limit at the reverse proxy or load balancer, keyed on the real client address, and set `ASKHARBOR_MESSAGE_RATE_LIMIT=0` so the API does not add a second, misleading limit. Writing down that proxy configuration belongs to the deployment stage of the [roadmap](ROADMAP.md) and is still pending.

## Checks

From `server/`, with its environment active:

```bash
python -m pytest                                   # file mode; database tests are skipped
ASKHARBOR_TEST_DATABASE_URL=postgresql+psycopg://askharbor:askharbor@127.0.0.1:5432/askharbor_test python -m pytest
python -m ruff check .
```

The second command runs the database tests too and needs the disposable test database and the temporary `CREATEDB` right from the quick start. From `widget/`:

```bash
npm test
npm run typecheck
npm run build
```

GitHub Actions runs all of these on pushes and pull requests, with a PostgreSQL 16 service for the database tests. Browser checks for keyboard navigation, mobile layout and request failures are described in [CONTRIBUTING.md](CONTRIBUTING.md).

## Project files

| Location | Purpose |
| :--- | :--- |
| `widget/src/` | Browser widget, styles, shared content validation and the editor. |
| `server/app/` | API, settings, content loading and validation, database models, storage, accounts and login. |
| `server/alembic/` | Database migrations, applied with `python -m alembic upgrade head`. |
| `examples/admin.html` | The panel page, copied into the build output and served at `/admin/`. |
| `server/content/` | Bot content files, one JSON file per bot. |
| `fixtures/content/` | Shared valid and invalid content cases used by the API tests and, later, the editor. |
| `server/tests/` and `widget/tests/` | Automated tests. |
| `examples/demo.html` | Local example host page. |
| `examples/editor.html` | The local content editor page, copied into the build output. |
| [ROADMAP.md](ROADMAP.md) | Planned work and completion criteria. |

## License

[MIT](LICENSE).
