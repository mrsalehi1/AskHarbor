# AskHarbor

AskHarbor adds a small guided FAQ widget to a website. Visitors choose a question and receive a predefined answer, with follow up choices when needed. It is for site owners who want to publish common answers without building a support interface from scratch.

The browser widget uses TypeScript and Shadow DOM. A Python FastAPI service supplies the branding, questions and answers.

## Current status

This is an early prototype with one fictional demo bot. It supports embedding, configurable branding, guided answer flows and a retry option when a request fails. Automated tests cover the basic API and widget flows.

Bot content currently lives in `server/app/repository.py`. Content files, a visual editor and deployment automation are planned work. The [roadmap](ROADMAP.md) separates that work from the features available today.

The active product plan is guided FAQ support using public reference content. Earlier AI and RAG ideas are outside this plan. The current code does not call a model or retrieve documents.

## Requirements

1. Python 3.11 or newer.
2. Node.js 22 or newer.
3. A browser for the local demo.

Building and installing dependencies needs package registry access. Once those dependencies are installed, the demo uses only local services. Docker and a cloud account are not required.

## Run the API

From the repository root:

```bash
cd server
python -m venv .venv
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
python -m http.server 4173 --bind 127.0.0.1 --directory widget/dist
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

These addresses are placeholders. Replace them with your own widget and API addresses when testing a deployment. Set `ASKHARBOR_ALLOWED_ORIGINS` to the exact host origins, separated by commas. Keep origin values free of paths and trailing slashes.

The widget sends a selected option ID to the API. It has no free text field, visitor account system, transcript database or analytics integration. Hosting services can still record request metadata, so check their logging settings before using the application beyond a local demo.

The `create({ apiUrl, botId, container? })` function is also exported for applications that import the TypeScript source.

## API

| Endpoint | Behavior |
| :--- | :--- |
| `GET /health` | Returns `{"status":"ok"}`. |
| `GET /api/v1/bots/{bot_id}` | Returns the branding, greeting and opening questions. |
| `POST /api/v1/bots/{bot_id}/messages` | Accepts `{"option_id":"getting-started"}` and returns an answer with follow up choices. |

Unknown bots return `404`. Unknown option IDs return `400`. Invalid request fields return `422`.

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
