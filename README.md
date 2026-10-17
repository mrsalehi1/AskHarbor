# AskHarbor

AskHarbor is a small embeddable support chatbot. A site adds one script tag and
gets a bottom-corner chat launcher. Questions, answers, branding, and follow-up
choices come from a Python API, so content can change without editing the host
website.

This release is a guided FAQ chatbot. It does not call an AI model yet.

## Project layout

- `widget/` — dependency-free browser widget written in TypeScript
- `server/` — FastAPI service and server-owned bot content

## Run locally

The server requires Python 3.11 or newer.

```bash
cd server
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Build the widget with Node.js 20 or newer:

```bash
cd widget
npm install
npm run build
```

Serve `widget/dist/askharbor.js` from any static host. During local development,
one option is `python -m http.server 4173 --directory widget/dist`.

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

The widget uses Shadow DOM to avoid inheriting styles from the host website.
It sends only the selected option ID to the API.

For application-controlled initialization, bundle the TypeScript package and
call `create({ apiUrl, botId, container? })`.

## Configure a bot

The MVP bot lives in `server/app/repository.py`. Each bot contains:

- public branding and the opening options
- answer nodes keyed by stable option IDs
- optional follow-up option IDs

Replace the demo support address and content before deployment. A database can
later implement the same repository interface without changing the endpoints
or widget.

Set allowed browser origins with a comma-separated environment variable:

```text
ASKHARBOR_ALLOWED_ORIGINS=https://www.example.com,https://app.example.com
```

The default `*` value is convenient for local development. Production should
list only websites that are allowed to embed the bot.

## API

### `GET /health`

Returns `{"status":"ok"}`.

### `GET /api/v1/bots/{bot_id}`

Returns the bot name, greeting, launcher label, primary color, and opening
options. Unknown bots return `404`.

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

Unknown option IDs return `400`; malformed requests return `422`.

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

## Future AI and RAG support

The message endpoint is the compatibility boundary for a future answer engine.
A later repository/service can accept free-text messages, retrieve relevant
documents from a vector store, and ask a model to answer with citations. Keep
tenant and bot IDs in that layer, validate document access before retrieval,
and preserve the existing guided options as a fallback when AI is unavailable.

## License

MIT
