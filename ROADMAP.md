# Roadmap

AskHarbor is a guided FAQ chatbot today. The work below is what comes next on this project. None of it is started.

## Near term

- Replace the in-memory demo repository with durable storage that keeps the same bot and message API.
- Let a site owner edit the bot name, greeting, color, questions, and answers without changing Python code.
- Keep the widget on the page when the API is down, and show a short retry state instead of removing it.
- Tighten keyboard use: focus the panel when it opens, return focus to the launcher when it closes, and keep contrast readable.
- Add a small local HTML page that loads `widget/dist/askharbor.js` against the demo bot.
- Run the server tests, Ruff, widget tests, typecheck, and production build in CI.

## After that

- Support more than one bot, each with its own id, branding, and answer tree.
- Let the embed choose launcher position and a few theme settings while Shadow DOM still isolates host styles.
- Document a production layout: static hosting for the script, the API process, and an explicit `ASKHARBOR_ALLOWED_ORIGINS` list.
- Add tests for CORS, unknown follow-up ids, and bots loaded from the durable store.

## Later

The message endpoint can stay the boundary for a later answer step. Guided options remain the fallback. That step is not part of the current release, and this repository does not call a model.
