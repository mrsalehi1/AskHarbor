# AskHarbor

AskHarbor adds a small guided FAQ widget to a website. Visitors choose a question and receive a predefined answer, with follow up choices when needed. It is for site owners who want to publish common answers without building a support interface from scratch.

The browser widget uses TypeScript and Shadow DOM. A Python FastAPI service supplies the branding, questions and answers.

## Current status

This is an early prototype with two fictional bots. It supports embedding, configurable branding, guided answer flows, a single retry when a request fails, a back to menu button, validated origin and content settings, and a per client request limit on the messages endpoint. Automated tests cover the API, the configuration rules, the content format and the widget flows.

Bot content lives in JSON files, one per bot, in `server/content/`. The server validates every file at startup and can reload them without a restart. See [Bot content](#bot-content). A local browser editor creates and changes these files without touching Python or the server: see [Content editor](#content-editor). Deployment automation is planned work. The [roadmap](ROADMAP.md) separates that work from the features available today.

The active product plan is guided FAQ support using public reference content. Earlier AI and RAG ideas are outside this plan. The current code does not call a model or retrieve documents.

## Quick start

Open three terminals from the repository root. The first runs the API, the second builds the widget, and the third serves the example page.

On Ubuntu or Debian, install the system packages once before anything else:

```bash
sudo apt install python3 python3-venv python3-pip nodejs npm
```

Ubuntu's `python3-venv` package is required or the virtual environment will fail with an `ensurepip` error. Check that `node --version` reports 22 or newer. If the distribution package is older, install Node.js 22 from [nodejs.org](https://nodejs.org/) or with `nvm`.

Terminal 1, the API:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\Activate.ps1
cp .env.example .env
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Inside the activated environment, `python` points at the virtual environment's interpreter, so the remaining commands use `python`.

Terminal 2, the widget:

```bash
cd widget
npm ci
npm run build
```

Terminal 3, the example page:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory widget/dist
```

Open [http://127.0.0.1:4173/](http://127.0.0.1:4173/). The page is `examples/demo.html` served next to the built widget. It talks to the demo bot at `http://127.0.0.1:8000`, whose fictional questions and answers live in `server/content/demo.json`. Click the chat button, pick a question, and follow the answer to its follow up choices.

If the chat button does not appear, confirm the API is running and that `server/.env` allows `http://127.0.0.1:4173`.

### Try the retry flow

This checks the behavior fixed for [issue 1](https://github.com/mrsalehi1/AskHarbor/issues/1).

1. Open the chat and stop the API in terminal 1 with `Ctrl+C`.
2. Choose a question. One error line appears with the same question offered again as a retry.
3. Choose it again while the API is still down. The error line and retry option stay single. Nothing stacks.
4. Restart the API and choose the question once more.
5. The error disappears. The question, answer and follow up choices each appear once.

### Try the back to menu button

1. Open the chat and choose a question, then follow it to an answer with no further choices.
2. Use the "Menu" button in the panel header, by mouse or by tabbing to it and pressing Enter.
3. The greeting and the original opening questions return without a page reload.
4. Stop the API, choose a question, and use the menu button while the error is showing. The error and retry option are cleared.
5. Restart the API, choose a question, and use the menu button before the answer arrives. The late answer is ignored and the menu stays in place.

### Try the second bot and a content reload

1. With the API running, open [http://127.0.0.1:8000/api/v1/bots/library](http://127.0.0.1:8000/api/v1/bots/library). This is the fictional Harbor Library bot from `server/content/library.json`.
2. Edit the greeting in that file and save it.
3. In a fourth terminal, send the reload signal: `kill -HUP $(pgrep -f "uvicorn app.main:app")`. Terminal 1 prints `Content reloaded from ... : demo, library`.
4. Refresh the bot address from step 1. The new greeting is there.
5. Break the file, for example by deleting a closing bracket, and send the signal again. Terminal 1 prints the problem with the file name, path and reason, and the previous content keeps being served.

To show the library bot on the example page, change `data-bot-id="demo"` to `data-bot-id="library"` in `examples/demo.html`, run `npm run build` again and reload the page.

### Try the content editor

With the widget built and terminal 3 serving it, open [http://127.0.0.1:4173/editor.html](http://127.0.0.1:4173/editor.html). The editor runs entirely in the browser; the API does not need to be running. Edit the starter bot, open the chat button in the corner to preview the conversation, then use **Export JSON** and drop the downloaded file into `server/content/` (or import `server/content/demo.json` to start from the demo). See [Content editor](#content-editor).

The detailed sections below cover each step and the embed snippet for other sites.

## Requirements

1. Python 3.11 or newer.
2. Node.js 22 or newer.
3. A browser for the local demo.

Building and installing dependencies needs package registry access. Once those dependencies are installed, the demo uses only local services. Docker and a cloud account are not required.

## Run the API

From the repository root:

```bash
cd server
python3 -m venv .venv
```

Activate the environment on macOS or Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Copy `server/.env.example` to `server/.env`. Then, from `server/` with the environment active:

```bash
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). The example origin setting permits the demo at `http://127.0.0.1:4173`.

## Build and open the demo

In another terminal, from the repository root:

```bash
cd widget
npm ci
npm run build
```

In a third terminal, from the repository root:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory widget/dist
```

Open [http://127.0.0.1:4173/](http://127.0.0.1:4173/). The build copies the example page into the public output folder. Use the chat button to select a question, follow an answer and close the panel. The page uses fictional support content and does not request visitor details.

## Embed the widget

Serve the built `widget/dist/askharbor.js` file and add this before the host page's closing `body` tag:

```html
<script
  src="https://cdn.example.com/askharbor.js"
  data-api-url="https://faq-api.example.com"
  data-bot-id="demo"
  defer
></script>
```

These addresses are placeholders. Replace them with your own widget and API addresses when testing a deployment. Set `ASKHARBOR_ALLOWED_ORIGINS` to the exact host origins, separated by commas. Spaces around each origin and trailing slashes are trimmed, so `https://example.com/` matches the browser origin `https://example.com`. Ports are kept. Paths are not supported.

`ASKHARBOR_ALLOWED_ORIGINS` accepts a comma separated list of exact origins or `*`:

```bash
ASKHARBOR_ALLOWED_ORIGINS=https://www.example.com,https://app.example.com  # production sites
ASKHARBOR_ALLOWED_ORIGINS=http://127.0.0.1:4173                            # the local demo
ASKHARBOR_ALLOWED_ORIGINS=*                                                # any origin, local development only
```

Leaving the variable unset is not the same as setting it to an empty value. Unset means the server falls back to the default `*` and allows any origin. Set but without a usable origin (blank, or only spaces, commas, or slashes) means the server refuses to start and prints an error naming the variable, because an empty allow list would silently block every browser request. To get the default back, delete the variable from the environment and from `server/.env` rather than leaving it empty.

The widget sends a selected option ID to the API. It has no free text field, visitor account system, transcript database or analytics integration. Hosting services can still record request metadata, so check their logging settings before using the application beyond a local demo.

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

Bots can be served from PostgreSQL instead of the content files. This is the foundation for the planned accounts and access control: the schema already includes users, sessions, websites and memberships, but nothing uses them yet — there is no login and the public endpoints stay exactly as they are. File mode remains the default and needs no database.

**What is stored.** One website row per bot, where the website `slug` is the public bot ID (`demo`, `library`), so existing embeds keep working. Each website has one bot document, the same validated JSON as a content file, in a JSONB column with a `revision` number. Every save must name the revision it started from and bumps it by one; a save against a stale revision changes nothing and reports the current revision, so two people editing the same bot cannot silently overwrite each other.

### Set up PostgreSQL natively on Ubuntu

```bash
sudo apt install postgresql
sudo -u postgres createuser --pwprompt askharbor   # choose a local password, e.g. askharbor
sudo -u postgres createdb --owner askharbor askharbor
sudo -u postgres createdb --owner askharbor askharbor_test   # only needed to run the tests
```

Ubuntu starts the server automatically and listens on `127.0.0.1:5432`. Check with `pg_isready`. These are local development names and passwords; a deployment sets its own credentials through the environment.

### Migrate, import and run

From `server/` with the environment active, set the URL (or put it in `server/.env`):

```bash
export ASKHARBOR_DATABASE_URL=postgresql+psycopg://askharbor:askharbor@127.0.0.1:5432/askharbor
python -m alembic upgrade head          # create or update the schema
python -m app.import_content            # load server/content into the database
ASKHARBOR_CONTENT_SOURCE=database python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The import validates the whole directory with the usual content rules before anything is written and commits all bots in one transaction: one bad file means nothing is imported and every problem is listed. A bot ID that already exists in the database is skipped and reported; run `python -m app.import_content --replace` to overwrite existing bots instead, which bumps their revisions like any other save. A different directory can be passed as an argument.

In database mode the server reads content live, so there is no reload signal to send: a change is visible on the next request, in every worker. `SIGHUP` is accepted and logged as ignored. At startup the server checks that the database is reachable and migrated to the current head, and refuses to start with a message naming `python -m alembic upgrade head` otherwise, so a schema change cannot be half-applied silently. Switching back to file mode is `ASKHARBOR_CONTENT_SOURCE=files` (or removing the variable); the files are untouched by the import.

### Test against a real PostgreSQL

The database tests only run when `ASKHARBOR_TEST_DATABASE_URL` points at a disposable database. They migrate it from scratch with Alembic and truncate tables between tests, so never point this at a database whose content you want to keep.

```bash
cd server
ASKHARBOR_TEST_DATABASE_URL=postgresql+psycopg://askharbor:askharbor@127.0.0.1:5432/askharbor_test python -m pytest
```

Without the variable those tests are skipped and the rest of the suite runs as before. CI runs them against a PostgreSQL 16 service container. The suite includes a schema drift check that fails if the SQLAlchemy models and the Alembic migrations stop describing the same tables.

**Limitations.**

- User management and the admin interface do not exist yet; see [Accounts and login](#accounts-and-login) for what works today. The editor still works with files, not the database.
- Database mode queries PostgreSQL on each request (with a small per-revision cache for the built definition). That is fine at demo scale and unmeasured beyond it.
- The import command and the editor do not talk to each other yet; moving an edited bot into the database is export, then import.

## Accounts and login

Accounts are available whenever `ASKHARBOR_DATABASE_URL` is set and the migrations have run, in either content mode. Without a database the account routes answer `503` with an explanation and the widget is unaffected. This round provides login, logout, sessions, the bootstrap admin and the forced password change. Creating users and websites, assigning access and the admin pages are the next round, so for now the only thing a signed in admin can do is list websites at `GET /api/v1/websites`.

**Local development account.** On first start with an empty `users` table the server creates one admin:

| Setting | Default | Variable |
| :--- | :--- | :--- |
| Username | `admin` | `ASKHARBOR_BOOTSTRAP_ADMIN_USERNAME` |
| Password | `ChangeMeLocal123!` | `ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD` |

The account is created with a forced password change: until it is changed, every route except login, logout, `GET /api/v1/auth/me` and the password change itself answers `403` with the code `password_change_required`. The bootstrap runs in every worker at startup inside a PostgreSQL advisory lock, so starting several workers together still creates exactly one admin. It only ever runs when the table is empty: a restart never recreates the account, resets a changed password or touches any other user. To start over locally, drop the `users` rows (or the database) deliberately.

**Production.** Set `ASKHARBOR_ENV=production`. The server then refuses to start while the bootstrap password is the documented local one or shorter than 12 characters, or while `ASKHARBOR_COOKIE_SECURE` is false, and prints which variable to fix. Supply `ASKHARBOR_BOOTSTRAP_ADMIN_PASSWORD` (and optionally the username) once for the first start; it is ignored afterwards and can be removed. The admin still has to change that password at first login.

**Endpoints.** All under `/api/v1`:

| Endpoint | Behavior |
| :--- | :--- |
| `POST /auth/login` | JSON `{"username","password"}`. Sets the session cookie and returns `{"username","is_admin","must_change_password"}`. Wrong name and wrong password get the same `401`. |
| `POST /auth/logout` | Revokes the session in the database and clears the cookie. `204`. |
| `GET /auth/me` | The signed in user, including whether a password change is still required. |
| `POST /auth/password` | JSON `{"current_password","new_password"}`. Checks the current password, applies the policy, clears the forced change and signs out the user's other sessions. |
| `GET /websites` | Websites the user may edit: all for an admin, memberships for others. Requires the password change to be done. |

**Passwords.** Hashed with Argon2id (the `argon2-cffi` defaults: 64 MiB, 3 passes) and never stored or logged in clear. New passwords must be 12 to 200 characters and differ from the current one; there are no composition rules. A login for an unknown username still runs a hash check against a dummy hash, so the response time does not reveal which accounts exist.

**Sessions.** A login creates a database row and a cookie named `askharbor_session` holding a random 256-bit token; the row stores only the token's SHA-256. Sessions last 12 hours (`ASKHARBOR_SESSION_HOURS`), end on logout, and all other sessions of a user end when that user changes their password. Expired or revoked rows are cleaned up at startup. Because sessions live in the database, every worker sees the same logins and a logout is immediate everywhere.

**Cookies and cross-site protection.** The cookie is `HttpOnly`, `SameSite=Lax`, `Path=/` and `Secure`. For plain `http://127.0.0.1` development set `ASKHARBOR_COOKIE_SECURE=false`; production refuses that. Three layers stop cross-site requests: the browser does not attach a `Lax` cookie to cross-site POSTs; the login, logout and password routes compare the `Origin` (or `Referer`) host with the `Host` header and answer `403` on a mismatch; and the login and password bodies must be JSON, which an HTML form cannot send. CORS applies only to `/health` and `/api/v1/bots/`, never to account routes, so an origin allowed for the widget cannot call them with the owner's cookie.

**Login rate limit.** Failed attempts are counted per client address and per username, 5 per 5 minutes by default (`ASKHARBOR_LOGIN_RATE_LIMIT`, `ASKHARBOR_LOGIN_RATE_WINDOW_SECONDS`). While over the limit even a correct password gets `429` with `Retry-After`. Successful logins do not consume the budget. Like the message limit, these counters are per process: with several workers or behind a proxy they are weaker than they look, and the proxy should enforce a limit on the login route as well.

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
python -m pytest
python -m ruff check .
```

From `widget/`:

```bash
npm test
npm run typecheck
npm run build
```

GitHub Actions runs these checks on pushes and pull requests. Browser checks for keyboard navigation, mobile layout and request failures are described in [CONTRIBUTING.md](CONTRIBUTING.md).

## Project files

| Location | Purpose |
| :--- | :--- |
| `widget/src/` | Browser widget, styles, shared content validation and the editor. |
| `server/app/` | API, settings, content loading and validation, database models, storage, accounts and login. |
| `server/alembic/` | Database migrations, applied with `python -m alembic upgrade head`. |
| `server/content/` | Bot content files, one JSON file per bot. |
| `fixtures/content/` | Shared valid and invalid content cases used by the API tests and, later, the editor. |
| `server/tests/` and `widget/tests/` | Automated tests. |
| `examples/demo.html` | Local example host page. |
| `examples/editor.html` | The local content editor page, copied into the build output. |
| [ROADMAP.md](ROADMAP.md) | Planned work and completion criteria. |

## License

[MIT](LICENSE).
