# AskHarbor

AskHarbor adds a small guided FAQ widget to a website. Visitors choose a question and receive a predefined answer, with follow up choices when needed. It is for site owners who want to publish common answers without building a support interface from scratch.

The browser widget uses TypeScript and Shadow DOM. A Python FastAPI service supplies the branding, questions and answers.

## Current status

This is an early prototype with one fictional demo bot. It supports embedding, configurable branding, guided answer flows and a retry option when a request fails. Automated tests cover the basic API and widget flows.

Bot content currently lives in `server/app/repository.py`. Content files, a visual editor and deployment automation are planned work. The [roadmap](ROADMAP.md) separates that work from the features available today.

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

Open [http://127.0.0.1:4173/](http://127.0.0.1:4173/). The page is `examples/demo.html` served next to the built widget. It talks to the demo bot at `http://127.0.0.1:8000`, whose fictional questions and answers live in `server/app/repository.py`. Click the chat button, pick a question, and follow the answer to its follow up choices.

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

The version shown at `/docs` and in `/openapi.json` is read from the installed package metadata, falling back to `server/pyproject.toml` for a source checkout. To release a new API version, change the `version` field in `server/pyproject.toml` only. Bot content is checked when the server starts: a follow up or opening option that points at an answer ID that does not exist stops startup with an error naming the bot, the answer and the missing ID, so a typo in the content cannot silently remove a button.

## Request limits

`POST /messages` allows **30 requests per client address per 60 second window** by default. Answers are predefined, and a visitor following a guided conversation sends one request per click, so an ordinary session stays far below this.

**Where the limit is enforced:** inside the API process itself, on `POST /api/v1/bots/{bot_id}/messages` only. There is no proxy involved; the demo setup in this repository serves the API directly, and the limiter is the only throttle. `GET /health` and `GET /api/v1/bots/{bot_id}` are never limited, so monitoring and widget start-up keep working while a client is throttled.

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `ASKHARBOR_MESSAGE_RATE_LIMIT` | `30` | Requests allowed per client within one window. `0` disables the limit. Negative values are rejected at startup. |
| `ASKHARBOR_MESSAGE_RATE_WINDOW_SECONDS` | `60` | Length of the window. Must be at least 1. |

For example, to allow 10 requests every 30 seconds:

```bash
ASKHARBOR_MESSAGE_RATE_LIMIT=10
ASKHARBOR_MESSAGE_RATE_WINDOW_SECONDS=30
```

Requests over the limit get `429 Too Many Requests`. The response carries a `Retry-After` header with the whole number of seconds (at least 1) until that client's window resets, and the body repeats it:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
Content-Type: application/json

{"detail": "Too many requests. Try again in 42 seconds."}
```

The window is fixed, counted from a client's first request: rejected requests do not extend it, so waiting out the `Retry-After` interval always restores the full budget. The widget treats a `429` like any other failed request: it shows "Sorry, the answer could not be loaded. Please try again." with the same question offered as a retry, and the visitor can also use the menu button to start over. The widget does not read `Retry-After` or wait automatically, so a visitor who retries immediately will see the same message until the window resets.

What the limiter stores: a fixed window counter per client address, in process memory, capped at 10000 entries. Expired windows are evicted first, then the oldest live one. Nothing is written to disk, no visitor IDs, cookies or profiles are created, and the counters disappear when the process stops. The client address is taken from the TCP connection; `X-Forwarded-For` is not read, so behind a reverse proxy all visitors share the proxy's address and one limit.

More than one worker breaks the accounting. Each uvicorn worker keeps its own counters, so with `--workers 4` a client can send roughly four times the configured limit, and a request rejected by one worker may be accepted by the next. For a single process demo this is fine. For multi worker or multi instance deployments, enforce the limit at the reverse proxy or load balancer instead and set `ASKHARBOR_MESSAGE_RATE_LIMIT=0` to avoid confusing double limiting. The deployment stage of the [roadmap](ROADMAP.md) is where that proxy configuration is meant to be written down.

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
| `server/app/` | API, settings and demo answers. |
| `server/tests/` and `widget/tests/` | Automated tests. |
| `examples/demo.html` | Local example host page. |
| [ROADMAP.md](ROADMAP.md) | Planned work and completion criteria. |

## License

[MIT](LICENSE).
