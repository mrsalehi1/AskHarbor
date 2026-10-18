# Roadmap

AskHarbor is a guided FAQ widget today: one script tag, a launcher, and answers the site owner wrote. The work below is the rest of the product. None of it is started.

The widget keeps sending only the selected option id. Saved data is the owner's bot content, plus a count on each option. Those counts have no visitor name, message, or account attached.

## 1. Reliable core

- Replace the in-memory demo repository with durable storage that keeps the same bot and message API.
- Let a site owner edit the bot name, greeting, color, questions, and answers without changing Python code.
- Keep the widget on the page when the API is down, and show a short retry state instead of removing it.
- Tighten keyboard use: focus the panel when it opens, return focus to the launcher when it closes, and keep contrast readable.
- Honor reduced motion and a readable mobile layout.
- Add a small local HTML page that loads `widget/dist/askharbor.js` against the demo bot.
- Run the server tests, Ruff, widget tests, typecheck, and production build in CI.

## 2. Content studio

- Edit the answer tree in an admin screen that runs with the API.
- Reorder opening options and follow-ups.
- Write answers in Markdown, with images the owner hosts.
- Validate option ids, missing follow-ups, and broken links before a save is accepted.
- Duplicate a bot, then archive one without deleting its history.
- Keep drafts separate from the live tree.
- Preview a draft in the widget before it is public.
- Publish a draft, roll back to an earlier published tree, and diff the two.
- Import and export a bot as JSON.

## 3. Widget on the host site

- Choose launcher corner, offset, and z-index from the embed attributes.
- Ship a few themes, and keep Shadow DOM from inheriting host styles.
- Translate the launcher, retry text, and close control. Answer text stays whatever the owner wrote for that locale.
- Let the owner publish more than one locale on the same bot.
- Walk back to the previous option inside the open panel. That path stays in the page session and is dropped when the panel closes.
- Offer a text filter over the current list of options.
- Show an owner-written message outside configured hours, using the site's timezone on the bot.
- Open the panel on load when the embed asks for that.

## 4. Many sites

- Host many bots, each with its own id, branding, locales, and answer tree.
- Give each bot its own list of allowed site origins.
- Keep a staging bot and a live bot, and copy a published tree from staging to live.
- Serve the public config and message routes only for a published bot.

## 5. Owner workspace

- Sign the site owner into the admin screen on their own installation.
- Group bots into sites the owner manages.
- Record content edits (who on that installation changed which bot, and when) so a publish can be audited.
- Leave visitor traffic out of that record.

## 6. Option counts

- Increment a counter when an option id is selected.
- Show those totals to the owner next to each option.
- Store the number only. Do not store a visitor identifier with it.

## 7. Publishing and operations

- Document production as a static host for `askharbor.js`, the API process, and an explicit `ASKHARBOR_ALLOWED_ORIGINS` list.
- Add a Docker Compose setup for the API and its database.
- Version the embed script so a site can pin a build.
- Set cache headers and an ETag on public bot config.
- Add a readiness check next to `/health`.
- Log process events and status codes. Leave request bodies and option ids out of those logs.
- Back up and restore bot content, including drafts and published versions.

## 8. Quality

- Test CORS, unknown follow-up ids, draft versus published bots, import validation, and rollback.
- Test keyboard open and close, the retry state, and locale switching.
- Add an example site in the repo that embeds the demo bot.
- Document the admin flow, the JSON format, and how to move from the in-memory demo to durable storage.
