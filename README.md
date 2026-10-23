# AskHarbor

AskHarbor adds a small guided FAQ widget to a website. Visitors choose a question and receive a predefined answer, with follow up choices when needed. It is for site owners who want to publish common answers without building a support interface from scratch.

The browser widget uses TypeScript and Shadow DOM. A Python FastAPI service supplies the branding, questions and answers.

## Current status

This is an early prototype with two fictional bots. It supports embedding, configurable branding, guided answer flows, a single retry when a request fails, a back to menu button, validated origin and content settings, and a per client request limit on the messages endpoint. Automated tests cover the API, the configuration rules, the content format and the widget flows.

Bot content lives in JSON files, one per bot, in `server/content/`. The server validates every file at startup and can reload them without a restart. See [Bot content](#bot-content). A visual editor and deployment automation are planned work. The [roadmap](ROADMAP.md) separates that work from the features available today.

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

**Adding a bot.** Copy `server/content/library.json`, change `config.id` and the content, keep it fictional or public, then restart or send the reload signal. The widget embed for the new bot uses its `config.id` in `data-bot-id`. The shared fixtures in `fixtures/content/` show valid and invalid examples with the problems each one should produce; the planned browser editor will use the same files so both sides agree on what is valid.

**Limitations.**

- The reload signal is meant for the single process command shown in the quick start. With `uvicorn --reload`, the supervisor process does not handle `SIGHUP` and exits, so send the signal only to the child worker, or restart. With `uvicorn --workers N`, each worker holds its own copy and uvicorn treats `SIGHUP` to the supervisor as a request to restart every worker; the new workers validate the content at startup and fail if it is invalid. In both cases `pgrep -f "uvicorn app.main:app"` returns more than one process, so pick the PID deliberately.
- `SIGHUP` does not exist on Windows. The server logs a warning at startup and runs without the reload signal; restart it to pick up changes.
- Answers are plain text. Links, markdown and HTML are shown literally.
- Answers that no opening or follow up option can reach are allowed and not reported.
- The content directory is read once per startup or reload. There is no file watcher.

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
| `widget/src/` | Browser widget and styles. |
| `server/app/` | API, settings, content loading and validation. |
| `server/content/` | Bot content files, one JSON file per bot. |
| `fixtures/content/` | Shared valid and invalid content cases used by the API tests and, later, the editor. |
| `server/tests/` and `widget/tests/` | Automated tests. |
| `examples/demo.html` | Local example host page. |
| [ROADMAP.md](ROADMAP.md) | Planned work and completion criteria. |

## License

[MIT](LICENSE).
