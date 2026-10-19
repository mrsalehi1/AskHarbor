# Roadmap

AskHarbor's next stage is a dependable guided FAQ tool that a site owner can configure and embed. The plan uses predefined answers and public reference content. It replaces the earlier AI and RAG direction.

## Starting point

The current prototype has a TypeScript widget, a FastAPI service, one fictional demo bot, basic API and widget tests, and a local example page. Bot definitions are still written in Python. The setup and CI added alongside this roadmap are preparation work and are excluded from the estimates below.

## 1. Make answer flows reliable

Estimated effort: 4 to 6 hours.

1. Fix the stale error messages described in [issue 1](https://github.com/mrsalehi1/AskHarbor/issues/1). A successful retry should clear the earlier failure without duplicating the question.
2. Handle empty and incorrectly formatted origin settings with clear validation. See [issue 2](https://github.com/mrsalehi1/AskHarbor/issues/2) and [issue 3](https://github.com/mrsalehi1/AskHarbor/issues/3).
3. Detect missing answer references instead of silently removing follow up options. See [issue 4](https://github.com/mrsalehi1/AskHarbor/issues/4).
4. Read the API version from package metadata. See [issue 5](https://github.com/mrsalehi1/AskHarbor/issues/5).
5. Add regression tests for the corrected behavior, including repeated failures and recovery.

Done when valid conversations still work, invalid content produces useful errors, and the existing issues have passing regression coverage.

## 2. Load bot content from files

Estimated effort: 6 to 8 hours.

1. Define a versioned JSON format for branding, opening questions, answer nodes and follow up choices.
2. Load a configured content file instead of editing Python to change answers.
3. Validate duplicate IDs, missing references, empty labels, invalid colors and malformed files.
4. Make import and reload atomic so rejected content leaves the last valid definition available.
5. Keep the fictional demo as an example and document how to create a second bot.

Done when two independent bots can be configured from files, valid content survives reload, and rejected changes leave existing content intact.

## 3. Add a local content editor

Estimated effort: 8 to 12 hours.

1. Let a site owner edit branding, questions, answers and follow up choices in the browser.
2. Show a draft conversation preview before exporting a bot definition.
3. Support JSON import and export using the same validation rules as the API.
4. Preserve the current draft when an import fails and explain the error.
5. Keep the editor local, using public or fictional FAQ content and browser file operations.

Done when a user can create, preview, export and reload a complete bot without editing Python. Invalid imports must preserve the draft. The exported file must load successfully in the API.

## 4. Improve accessibility and browser behavior

Estimated effort: 4 to 6 hours.

1. Check opening, closing, Escape, keyboard focus and screen reader announcements.
2. Test narrow screens, long answers and long question labels.
3. Cover loading errors, delayed responses, retries and removal of the widget while a request is pending.
4. Add browser tests with a local API or controlled responses.

Done when the documented flows work with a keyboard and on mobile layouts, with browser tests for the important failure cases.

## 5. Make demonstration deployments repeatable

Estimated effort: 4 to 6 hours.

1. Package the API and static widget for a documented AWS demonstration deployment.
2. Keep infrastructure configuration in the repository and use placeholders for account specific settings.
3. Check the health endpoint during deployment and document rollback and cleanup.
4. Add configurable request limits, or enforce them at the deployment proxy, as described in [issue 6](https://github.com/mrsalehi1/AskHarbor/issues/6).
5. Use the fictional bot for deployment checks and document the host's request logging settings.

Done when a fresh deployment serves the widget and demo API, health checks succeed, and rollback and cleanup have been rehearsed. Cloud checks require a separately configured account; local development remains available without one.

## Planning estimate

The open work above is estimated at 26 to 38 hours, including implementation, tests and documentation. These are planning estimates based on the current prototype. Update them as work is completed or a task changes.

All five stages remain planned. Existing issue fixes are part of stage 1 and stage 5, rather than additional work counted twice.

## Data and product boundaries

Development examples use fictional content. The current plan does not add visitor profiles, contact collection, stored conversations, customer datasets or regulated records. Request metadata at the hosting layer needs separate attention when testing a deployment.

Model training, model evaluation, AI inference infrastructure, document embeddings and RAG are outside this roadmap. Any later change in direction should be recorded explicitly before that work begins.
