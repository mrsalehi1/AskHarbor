# Contributing

AskHarbor is an early guided FAQ project. Check [ROADMAP.md](ROADMAP.md) and the open issues before choosing work. Discuss a large change before starting it.

## Local development

Follow the API, widget and example page setup in [README.md](README.md). Use the fictional demo bot when testing. Dependencies need to be installed once before working without a network connection.

Keep credentials and local settings in ignored environment files. Commit examples with placeholder values. Examples and bug reports should use public or fictional content.

## Checking a change

Run the API tests and Ruff from `server/`. Run the widget tests, TypeScript check and build from `widget/`. The README lists the commands.

For a widget change, open the local example page and check:

1. Open and close the chat with the keyboard.
2. Select an opening question and a follow up question.
3. Check a narrow browser window and a long answer.
4. Stop the API, try an option, restart it and retry.
5. Check Escape and where focus goes after closing.

Record the behavior you observe rather than treating the checklist as a claim that every flow already passes. The README quick start describes the expected retry behavior.

## Pull requests

Describe the problem, the resulting behavior and the checks you ran. Include regression coverage for behavior changes. State any checks you could not complete.

Use your GitHub account's linked commit email. Preserve the repository's actual history. New features should keep the current guided FAQ scope and use the same fictional examples.
