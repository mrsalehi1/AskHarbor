/**
 * Local bot content editor: plain TypeScript forms over one draft document,
 * with the real widget as the conversation preview.
 *
 * The draft is a BotContentDocument, the same shape as a content file, and is
 * validated with the same rules as the API on every change. The preview widget
 * reads from a snapshot of the draft through a local transport, so nothing
 * leaves the browser. Imports are validated before they replace the draft and
 * exports are blocked while the draft has problems.
 */

import {
  parseBotContent,
  serializeBotContent,
  validateBotContent,
  type AnswerEntry,
  type BotContentDocument,
  type ContentProblem,
} from "./content";
import type { BotTransport } from "./types";
import { AskHarborWidget } from "./widget";

export function starterDraft(): BotContentDocument {
  return {
    format_version: 1,
    config: {
      id: "my-first-bot",
      name: "My first bot",
      greeting: "Hi! Pick a question to see its answer.",
      launcher_label: "Open the FAQ",
      primary_color: "#155eef",
      opening_option_ids: ["example-question"],
    },
    answers: [
      {
        id: "example-question",
        label: "Where does this answer come from?",
        answer: "From your draft. Edit this text in the form and watch the preview follow.",
        next_option_ids: ["second-question"],
      },
      {
        id: "second-question",
        label: "What else can I add?",
        answer: "More answers, opening questions and follow up choices. Export when it is ready.",
      },
    ],
  };
}

/** Serves the widget from a draft snapshot, mirroring the server's lookups. */
export function draftTransport(document: BotContentDocument): BotTransport {
  const answers = new Map(document.answers.map((entry) => [entry.id, entry]));
  const label = (id: string): string => answers.get(id)?.label ?? id;
  return {
    async getConfig() {
      return {
        id: document.config.id,
        name: document.config.name,
        greeting: document.config.greeting,
        launcher_label: document.config.launcher_label,
        primary_color: document.config.primary_color,
        options: document.config.opening_option_ids.map((id) => ({ id, label: label(id) })),
      };
    },
    async sendMessage(optionId: string) {
      const entry = answers.get(optionId);
      if (!entry) throw new Error("Unknown option");
      return {
        answer: entry.answer,
        options: (entry.next_option_ids ?? []).map((id) => ({ id, label: label(id) })),
      };
    },
  };
}

export interface EditorHandle {
  getDraft(): BotContentDocument;
  getProblems(): ContentProblem[];
  buildExport(): { filename: string; text: string };
}

type Children = (Node | string)[];

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> & { dataset?: Record<string, string> } = {},
  children: Children = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  const { dataset, ...rest } = props;
  Object.assign(node, rest);
  if (dataset) Object.assign(node.dataset, dataset);
  node.append(...children);
  return node;
}

/** Attribute selector for a data-path value. Paths never contain quotes or backslashes. */
export function pathSelector(path: string): string {
  return `[data-path="${path.replace(/["\\]/g, "\\$&")}"]`;
}

let fieldCounter = 0;

export function mountEditor(root: HTMLElement): EditorHandle {
  let draft = starterDraft();
  let problems: ContentProblem[] = [];
  let previewWidget: AskHarborWidget | undefined;

  // --- skeleton -------------------------------------------------------------
  const importInput = el("input", { type: "file", accept: ".json,application/json", id: "import-input" });
  const importStatus = el("div", { id: "import-status" });
  importStatus.setAttribute("role", "status");
  const exportButton = el("button", { type: "button", id: "export-button", textContent: "Export JSON" });
  const toolbar = el("section", { className: "toolbar" }, [
    el("label", { className: "import-label", htmlFor: "import-input", textContent: "Import JSON file" }),
    importInput,
    exportButton,
    importStatus,
  ]);

  const form = el("form", { id: "bot-form", noValidate: true });
  form.addEventListener("submit", (event) => event.preventDefault());

  const problemHeading = el("h2", { textContent: "Problems" });
  const problemList = el("ul", { id: "problem-list" });
  const noProblems = el("p", { id: "no-problems", textContent: "No problems. The draft is valid." });
  const problemPane = el("section", { className: "problems" }, [problemHeading, problemList, noProblems]);
  problemPane.setAttribute("aria-live", "polite");

  const previewNote = el("p", { id: "preview-note" });
  const previewHost = el("div", { id: "preview-host" });
  const previewPane = el("section", { className: "preview" }, [
    el("h2", { textContent: "Preview" }),
    previewNote,
    previewHost,
  ]);

  root.replaceChildren(toolbar, form, el("aside", { className: "side" }, [problemPane, previewPane]));

  // --- form building --------------------------------------------------------
  function textField(
    labelText: string,
    path: string,
    value: string,
    onInput: (value: string) => void,
    options: { textarea?: boolean; rerenderOnChange?: boolean } = {},
  ): HTMLElement {
    fieldCounter += 1;
    const id = `field-${fieldCounter}`;
    const input = options.textarea
      ? el("textarea", { id, value, rows: 3 })
      : el("input", { id, type: "text", value });
    input.dataset.path = path;
    if (options.rerenderOnChange) input.dataset.rerender = "true";
    input.addEventListener("input", () => {
      onInput(input.value);
      lightRefresh();
    });
    return el("p", { className: "field" }, [
      el("label", { htmlFor: id, textContent: labelText }),
      input,
    ]);
  }

  function answerIdSelect(path: string, value: string, onChange: (value: string) => void): HTMLSelectElement {
    const select = el("select", { dataset: { path, rerender: "true" } });
    const ids = draft.answers.map((entry) => entry.id);
    if (!ids.includes(value)) {
      select.append(el("option", { value, textContent: `(missing) ${value}`, selected: true }));
    }
    for (const id of ids) {
      select.append(el("option", { value: id, textContent: id, selected: id === value }));
    }
    select.addEventListener("change", () => onChange(select.value));
    return select;
  }

  /** Ordered list of answer references with add, remove and move controls. */
  function idListEditor(
    path: string,
    list: string[],
    addLabel: string,
    itemLabel: string,
  ): HTMLElement {
    const container = el("div", { className: "id-list", dataset: { path } });
    list.forEach((value, index) => {
      const row = el("div", { className: "id-row" });
      const select = answerIdSelect(`${path}[${index}]`, value, (next) => {
        list[index] = next;
      });
      const move = (offset: number) =>
        el("button", {
          type: "button",
          textContent: offset < 0 ? "↑" : "↓",
          disabled: offset < 0 ? index === 0 : index === list.length - 1,
          onclick: () => {
            const [item] = list.splice(index, 1);
            list.splice(index + offset, 0, item as string);
            structuralRefresh();
          },
        });
      const up = move(-1);
      const down = move(1);
      up.setAttribute("aria-label", `Move ${itemLabel} ${index + 1} up`);
      down.setAttribute("aria-label", `Move ${itemLabel} ${index + 1} down`);
      const remove = el("button", {
        type: "button",
        textContent: "Remove",
        onclick: () => {
          list.splice(index, 1);
          structuralRefresh();
        },
      });
      remove.setAttribute("aria-label", `Remove ${itemLabel} ${index + 1}`);
      row.append(select, up, down, remove);
      container.append(row);
    });
    container.append(
      el("button", {
        type: "button",
        className: "add",
        textContent: addLabel,
        onclick: () => {
          list.push(draft.answers[0]?.id ?? "");
          structuralRefresh();
        },
      }),
    );
    return container;
  }

  function freshAnswerId(): string {
    const existing = new Set(draft.answers.map((entry) => entry.id));
    let index = draft.answers.length + 1;
    while (existing.has(`new-answer-${index}`)) index += 1;
    return `new-answer-${index}`;
  }

  function renderForms(): void {
    const config = draft.config;
    const branding = el("fieldset", {}, [
      el("legend", { textContent: "Branding" }),
      textField("Bot ID", "config.id", config.id, (v) => (config.id = v), { rerenderOnChange: true }),
      textField("Name", "config.name", config.name, (v) => (config.name = v)),
      textField("Greeting", "config.greeting", config.greeting, (v) => (config.greeting = v), { textarea: true }),
      textField("Launcher label", "config.launcher_label", config.launcher_label, (v) => (config.launcher_label = v)),
      textField("Primary color", "config.primary_color", config.primary_color, (v) => (config.primary_color = v)),
    ]);

    const opening = el("fieldset", {}, [
      el("legend", { textContent: "Opening questions" }),
      el("p", { className: "hint", textContent: "Shown with the greeting, in this order. Labels come from the answers." }),
      idListEditor("config.opening_option_ids", config.opening_option_ids, "Add opening question", "opening question"),
    ]);

    const answerSections = draft.answers.map((entry, index) => {
      if (!entry.next_option_ids) entry.next_option_ids = [];
      const removeButton = el("button", {
        type: "button",
        className: "remove-answer",
        textContent: "Remove this answer",
        onclick: () => {
          draft.answers.splice(index, 1);
          structuralRefresh();
        },
      });
      return el("fieldset", { className: "answer" }, [
        el("legend", { textContent: `Answer ${index + 1}` }),
        textField("Option ID", `answers[${index}].id`, entry.id, (v) => (entry.id = v), { rerenderOnChange: true }),
        textField("Question label", `answers[${index}].label`, entry.label, (v) => (entry.label = v)),
        textField("Answer text", `answers[${index}].answer`, entry.answer, (v) => (entry.answer = v), { textarea: true }),
        el("p", { className: "hint", textContent: "Follow up choices offered after this answer:" }),
        idListEditor(`answers[${index}].next_option_ids`, entry.next_option_ids, "Add follow up", "follow up"),
        removeButton,
      ]);
    });

    const addAnswer = el("button", {
      type: "button",
      id: "add-answer",
      textContent: "Add answer",
      onclick: () => {
        draft.answers.push({
          id: freshAnswerId(),
          label: "New question?",
          answer: "New answer text.",
          next_option_ids: [],
        });
        structuralRefresh();
      },
    });

    form.replaceChildren(branding, opening, ...answerSections, addAnswer);
  }

  // --- validation and preview -------------------------------------------------
  function draftForValidation(): BotContentDocument {
    const copy = structuredClone(draft);
    copy.answers = copy.answers.map((entry) => {
      if (entry.next_option_ids && entry.next_option_ids.length === 0) {
        const { next_option_ids: _empty, ...rest } = entry;
        return rest as AnswerEntry;
      }
      return entry;
    });
    return copy;
  }

  function markFields(): void {
    for (const marked of form.querySelectorAll(".field-invalid")) {
      marked.classList.remove("field-invalid");
      marked.removeAttribute("aria-invalid");
    }
    for (const problem of problems) {
      const field = form.querySelector(pathSelector(problem.path));
      if (field) {
        field.classList.add("field-invalid");
        field.setAttribute("aria-invalid", "true");
      }
    }
  }

  function renderProblems(): void {
    problemList.replaceChildren(
      ...problems.map((problem) =>
        el("li", { textContent: `${problem.path || "(document)"}: ${problem.message}` }),
      ),
    );
    noProblems.hidden = problems.length > 0;
    problemList.hidden = problems.length === 0;
  }

  function updateExportButton(): void {
    exportButton.disabled = problems.length > 0;
    exportButton.title = problems.length > 0 ? "Fix the problems before exporting." : "";
  }

  function updatePreviewNote(): void {
    if (problems.length === 0) {
      previewNote.textContent = "The preview below answers from your draft. Nothing is sent anywhere.";
    } else if (previewWidget) {
      previewNote.textContent = "The draft has problems. The preview still shows the last valid version.";
    } else {
      previewNote.textContent = "Fix the problems to see the preview.";
    }
  }

  function lightRefresh(): void {
    problems = validateBotContent(draftForValidation());
    renderProblems();
    markFields();
    updateExportButton();
    updatePreviewNote();
  }

  function rebuildPreview(): void {
    if (problems.length > 0) return;
    const wasOpen = !(
      previewHost
        .querySelector("[data-askharbor]")
        ?.shadowRoot?.querySelector<HTMLElement>(".panel")?.hidden ?? true
    );
    previewWidget?.destroy();
    previewWidget = new AskHarborWidget({
      container: previewHost,
      transport: draftTransport(draftForValidation()),
    });
    void previewWidget.init().then(() => {
      if (!wasOpen) return;
      previewHost
        .querySelector("[data-askharbor]")
        ?.shadowRoot?.querySelector<HTMLButtonElement>(".launcher")
        ?.click();
      updatePreviewNote();
    });
  }

  function structuralRefresh(): void {
    renderForms();
    lightRefresh();
    rebuildPreview();
  }

  // Text fields refresh validation on every keystroke but only rebuild the
  // preview when editing finishes, so the panel does not reset while typing.
  form.addEventListener("change", (event) => {
    const target = event.target as HTMLElement;
    if (target.dataset.rerender === "true") {
      renderForms();
      lightRefresh();
    }
    rebuildPreview();
  });

  // --- import and export ------------------------------------------------------
  function showImportError(filename: string, importProblems: ContentProblem[]): void {
    importStatus.replaceChildren(
      el("p", { className: "import-error", textContent: `'${filename}' was not imported. Your draft is unchanged.` }),
      el("ul", {}, importProblems.map((problem) =>
        el("li", { textContent: `${problem.path || "(document)"}: ${problem.message}` }),
      )),
    );
  }

  importInput.addEventListener("change", () => {
    const file = importInput.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = parseBotContent(String(reader.result));
      if (result.document) {
        draft = result.document;
        importStatus.replaceChildren(
          el("p", { textContent: `Imported bot '${draft.config.id}' from '${file.name}'.` }),
        );
        structuralRefresh();
      } else {
        showImportError(file.name, result.problems);
      }
      importInput.value = "";
    };
    reader.readAsText(file);
  });

  function buildExport(): { filename: string; text: string } {
    return {
      filename: `${draft.config.id || "bot"}.json`,
      text: serializeBotContent(draftForValidation()),
    };
  }

  exportButton.addEventListener("click", () => {
    if (problems.length > 0) return;
    const { filename, text } = buildExport();
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const anchor = el("a", { href: url, download: filename });
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    importStatus.replaceChildren(el("p", { textContent: `Exported '${filename}'.` }));
  });

  // --- first render -------------------------------------------------------------
  renderForms();
  lightRefresh();
  rebuildPreview();

  return {
    getDraft: () => draft,
    getProblems: () => problems,
    buildExport,
  };
}
