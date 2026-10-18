# Roadmap

AskHarbor is a guided FAQ chatbot today. The widget and API do not call a model yet. The work below is planned and not started.

Guided options stay available as a fallback when an AI answer is unavailable.

## Near term

- Replace the in-memory demo repository with durable storage that keeps the same bot and message API.
- Let a site owner edit the bot name, greeting, color, questions, and answers without changing Python code.
- Keep the widget on the page when the API is down, and show a short retry state instead of removing it.
- Tighten keyboard use: focus the panel when it opens, return focus to the launcher when it closes, and keep contrast readable.
- Add a small local HTML page that loads `widget/dist/askharbor.js` against the demo bot.
- Run the server tests, Ruff, widget tests, typecheck, and production build in CI.

## AI answer chatbot

Visitors will be able to type a question and get an answer, not only pick a guided option.

- Free-text chat on the existing embed, with the selected guided option still supported.
- Multi-turn conversation history for the open widget session.
- Opening statement, suggested questions, and follow-up questions.
- Stream the answer into the panel as it is generated.
- Show citations for passages used in the answer.
- Accept file and image messages when the selected model can read them.
- Speech-to-text input and text-to-speech playback.
- Optional moderation before a message is sent or an answer is shown.
- Remember conversation variables across turns in that chat.
- Fall back to the guided answer tree when retrieval or the model fails.

## RAG pipeline

Each bot will answer from its own knowledge, from ingestion through retrieval.

- Knowledge bases attached to a bot.
- Upload PDF, PowerPoint, Word, plain text, Markdown, HTML, CSV, and Excel files.
- Import a web page and refresh synced sources.
- Extract text from those documents.
- Chunk with automatic, custom, parent-child, and question-answer modes.
- Embed chunks and search them in a vector index.
- Hybrid keyword and vector search, plus reranking.
- Filter retrieval with document metadata.
- Set top-k and a minimum relevance score.
- Test a query against the knowledge base before publishing the bot.

## Workflow

- Build and test an AI workflow on a visual canvas.
- Ship a workflow as a chat app or as an API call.
- Include chatflow steps for a back-and-forth assistant.
- Use steps for a model call, knowledge retrieval, branching, an HTTP request, and a code step.
- Reuse the same knowledge, tools, and models inside a workflow.

## Model support

- Connect many proprietary and open-source models through their provider APIs.
- Accept any OpenAI-compatible endpoint, including a model the owner hosts.
- Set separate defaults for chat, embeddings, reranking, and speech.
- Compare two models on the same prompt before choosing one for the bot.

## Prompt workspace

- Edit the system prompt, variables, and the knowledge attached to a bot.
- Preview the answer in the same workspace used to edit the prompt.
- Compare outputs while changing the prompt or the model.
- Turn on extra chat features, including speech, from that workspace.

## Agents

- Run an agent as the chat app or as one step in a workflow.
- Give the agent skills and tools.
- Connect tools from a catalog, from MCP servers, and from the owner's own APIs.
- Let an agent handle files and commands inside a sandbox for open-ended tasks.

## Operations

- Store application logs and review them over time.
- Annotate production conversations and reuse a corrected answer.
- Improve prompts, knowledge, and model choice from that production record.
- Export traces to an external observability tool.

## APIs

- Expose chat, text generation, workflow runs, and knowledge management over HTTP.
- Issue API keys for those endpoints.
- Keep the embed script as the website integration.
- Publish a bot to the website widget, a hosted page, or the API.

## Workspace

- Host more than one bot, each with its own id, branding, knowledge, and answer tree.
- Invite teammates and give them roles.
- Run the stack self-hosted.
- Offer a hosted setup later, without a separate rewrite.
- Add single sign-on and stricter access control for larger teams.
- Translate the workspace interface.

## Widget and release work

- Let the embed choose launcher position and a few theme settings while Shadow DOM still isolates host styles.
- Document a production layout: static hosting for the script, the API process, and an explicit `ASKHARBOR_ALLOWED_ORIGINS` list.
- Add tests for CORS, unknown follow-up ids, retrieval, and bots loaded from the durable store.
