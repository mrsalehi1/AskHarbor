# Bot content fixtures

Shared test cases for the bot content format described in the README under
"Bot content". The API tests in `server/tests/test_content_validation.py` and
the widget tests in `widget/tests/content.test.ts` run every file here, so the
server and the browser editor accept and reject the same content for the same
reasons.

## Layout

| Directory | Contents | Expectation |
| :--- | :--- | :--- |
| `valid/` | Complete bot content files in the normal format. | Zero problems. Each file must also load as a bot. |
| `invalid/` | One wrapper object per case, see below. | Every listed problem is reported. |
| `malformed/` | Files that are not valid JSON at all. | One problem at the document root mentioning JSON. |

## Invalid case format

```json
{
  "description": "two answers share an id",
  "expected_problems": [
    { "path": "answers[2].id", "contains": "duplicate answer id 'pricing'" }
  ],
  "content": { "...the bot content document under test..." }
}
```

`content` is the document to validate. For each entry in `expected_problems`
the validator must report a problem at exactly that `path` whose message
contains the `contains` text. Extra problems are allowed, so an implementation
may report more than the fixture lists but never less.

## Paths

Paths are dotted names with zero based indexes in brackets, for example
`config.primary_color`, `answers[1].label` or
`answers[0].next_option_ids[2]`. The document root is the empty string.

## Adding a case

Keep bots fictional. Add the smallest content that shows the problem, then run
the API tests from `server/` to confirm the case fails for the reason you
expect.
