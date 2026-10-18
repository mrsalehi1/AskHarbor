# AskHarbor

AskHarbor is a small embeddable support chatbot for people who own a website and want a guided FAQ in the corner of the page. A site adds one script tag and gets a bottom-corner chat launcher. Questions, answers, branding, and follow-up choices come from a Python API, so the content can change without editing the host website.

It is a personal project. The demo bot is made-up sample content, including the address `support@example.com`. The widget sends only the selected option id. The server stores the bot content the site owner wrote.

## Who it is for

Site owners and developers who want a script-tag support widget with server-owned answers. The widget is for visitors of those sites. It sends only the selected option id to the API.

## Built with

- `widget/` — TypeScript, bundled with esbuild, tested with Vitest. Node.js 20 or newer.
- `server/` — Python 3.11 or newer, FastAPI, Pydantic, and Uvicorn. Tests use pytest. Ruff checks the Python code.

## Project layout

- `widget/` — dependency-free browser widget
- `server/` — FastAPI service and server-owned bot content
- `ROADMAP.md` — work still ahead
- `LICENSE` — MIT

## Run locally

The server requires Python 3.11 or newer.

```bash
cd server
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
copy ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

On macOS or Linux, use `cp ../.env.example .env` instead of `copy`.

Build the widget with Node.js 20 or newer:

```bash
cd widget
npm install
npm run build
```

Serve `widget/dist/askharbor.js` from any static host. During local development, one option is `python -m http.server 4173 --directory widget/dist`.

## Embed

Add the compiled script immediately before the closing `body` tag:

```html
<script
  src="https://cdn.example.com/askharbor.js"
  data-api-url="https://support-api.example.com"
  data-bot-id="demo"
  defer
></script>
```

The widget uses Shadow DOM so it does not inherit styles from the host website. It sends only the selected option id to the API.

For application-controlled initialization, bundle the TypeScript package and call `create({ apiUrl, botId, container? })`.

## Configure a bot

The sample bot lives in `server/app/repository.py`. It is fictional demo content, not customer data. Each bot contains:

- public branding and the opening options
- answer nodes keyed by stable option ids
- optional follow-up option ids

Replace the demo support address and content before you use a bot for a real site. A database can later implement the same repository interface without changing the endpoints or the widget.

Copy `.env.example` to `server/.env` and set the sites allowed to call the API:

```text
ASKHARBOR_ALLOWED_ORIGINS=https://www.example.com,https://app.example.com
```

`.env` is listed in `.gitignore`. The example file contains placeholders only. The default `*` value is for local development. A public deployment should list only websites that are allowed to embed the bot.

## API

### `GET /health`

Returns `{"status":"ok"}`.

### `GET /api/v1/bots/{bot_id}`

Returns the bot name, greeting, launcher label, primary color, and opening options. Unknown bots return `404`.

### `POST /api/v1/bots/{bot_id}/messages`

Request:

```json
{"option_id":"getting-started"}
```

Response:

```json
{
  "answer": "Add the AskHarbor script before your closing body tag...",
  "options": [
    {"id": "installation", "label": "Show installation details"}
  ]
}
```

Unknown option ids return `400`. Malformed requests return `422`.

Interactive API documentation is available at `/docs` while the server runs.

## Test

```bash
cd server
pytest
ruff check .

cd ../widget
npm test
npm run typecheck
npm run build
```

## Plans

The current release is the guided FAQ widget and API. Planned work is listed in [ROADMAP.md](ROADMAP.md):

- store bots outside the in-memory demo repository and edit them without changing Python
- draft, preview, publish, and roll back answer trees
- support many bots, themes, locales, and launcher placements
- keep a retry state, stronger keyboard behavior, and a local embed page
- import, export, and back up bot content, and run CI for the server and the widget

## License

MIT. The full text is in `LICENSE` at the top of this repository.
