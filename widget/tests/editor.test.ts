// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parseBotContent } from "../src/content";
import {
  draftTransport,
  mountEditor,
  pathSelector,
  starterDraft,
  type EditorHandle,
} from "../src/editor-app";
import { AskHarborWidget } from "../src/widget";

const DEMO_JSON = readFileSync(resolve(process.cwd(), "../server/content/demo.json"), "utf-8");

function field(name: string): HTMLInputElement {
  const element = document.querySelector<HTMLInputElement>(pathSelector(name));
  expect(element, `field ${name} should exist`).not.toBeNull();
  return element as HTMLInputElement;
}

function setField(name: string, value: string): void {
  const input = field(name);
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function problemTexts(): string[] {
  return Array.from(document.querySelectorAll("#problem-list li")).map(
    (item) => item.textContent ?? "",
  );
}

function previewRoot(): ShadowRoot {
  const host = document.querySelector<HTMLElement>("#preview-host [data-askharbor]");
  expect(host, "preview widget should be mounted").not.toBeNull();
  return host!.shadowRoot!;
}

async function importFile(name: string, text: string): Promise<void> {
  const input = document.querySelector<HTMLInputElement>("#import-input")!;
  const file = new File([text], name, { type: "application/json" });
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  input.dispatchEvent(new Event("change", { bubbles: true }));
  await vi.waitFor(() => {
    expect(document.querySelector("#import-status")?.textContent).not.toBe("");
  });
}

describe("editor", () => {
  let editor: EditorHandle;

  beforeEach(async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("the editor must not touch the network")),
    );
    document.body.replaceChildren(document.createElement("div"));
    editor = mountEditor(document.body.firstElementChild as HTMLElement);
    await vi.waitFor(() => previewRoot());
  });

  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("starts with a valid draft, no problems and export enabled", () => {
    expect(editor.getProblems()).toEqual([]);
    expect(problemTexts()).toEqual([]);
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(false);
    expect(document.querySelector("#no-problems")?.textContent).toContain("valid");
  });

  it("reflects form edits in the draft and validates as you type", () => {
    setField("config.name", "Harbor Helper");
    expect(editor.getDraft().config.name).toBe("Harbor Helper");

    setField("config.primary_color", "blue");
    expect(problemTexts()).toEqual([
      "config.primary_color: must be a hex color like #155eef or #fff",
    ]);
    expect(field("config.primary_color").getAttribute("aria-invalid")).toBe("true");
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(true);

    setField("config.primary_color", "#00aa55");
    expect(problemTexts()).toEqual([]);
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(false);
  });

  it("previews the conversation from the draft without any network use", async () => {
    const root = previewRoot();
    root.querySelector<HTMLButtonElement>(".launcher")!.click();

    expect(root.querySelector(".message.bot")?.textContent).toBe(
      "Hi! Pick a question to see its answer.",
    );
    const option = root.querySelector<HTMLButtonElement>(".option")!;
    expect(option.textContent).toBe("Where does this answer come from?");
    option.click();

    await vi.waitFor(() => {
      expect(root.textContent).toContain("From your draft.");
    });
    expect(
      Array.from(root.querySelectorAll(".option")).map((button) => button.textContent),
    ).toEqual(["What else can I add?"]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rebuilds the preview when a field edit is committed with a change event", async () => {
    setField("config.greeting", "A fresh greeting.");
    field("config.greeting").dispatchEvent(new Event("change", { bubbles: true }));

    await vi.waitFor(() => {
      const root = previewRoot();
      root.querySelector<HTMLButtonElement>(".launcher")!.click();
      expect(root.querySelector(".message.bot")?.textContent).toBe("A fresh greeting.");
    });
  });

  it("keeps the last valid preview while the draft has problems", () => {
    setField("config.greeting", "");
    field("config.greeting").dispatchEvent(new Event("change", { bubbles: true }));

    expect(problemTexts()).toEqual(["config.greeting: text must not be blank"]);
    const root = previewRoot();
    root.querySelector<HTMLButtonElement>(".launcher")!.click();
    expect(root.querySelector(".message.bot")?.textContent).toBe(
      "Hi! Pick a question to see its answer.",
    );
    expect(document.querySelector("#preview-note")?.textContent).toContain("last valid version");
  });

  it("adds and removes answers through the form", () => {
    document.querySelector<HTMLButtonElement>("#add-answer")!.click();
    expect(editor.getDraft().answers).toHaveLength(3);
    expect(editor.getProblems()).toEqual([]);

    const remove = Array.from(
      document.querySelectorAll<HTMLButtonElement>(".remove-answer"),
    ).at(-1)!;
    remove.click();
    expect(editor.getDraft().answers).toHaveLength(2);
  });

  it("flags a dangling reference when the answer it points at is removed", () => {
    // The second answer is the follow up of the first one.
    Array.from(document.querySelectorAll<HTMLButtonElement>(".remove-answer")).at(-1)!.click();

    expect(problemTexts()).toEqual([
      "answers[0].next_option_ids[0]: follow up option 'second-question' has no matching answer",
    ]);
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(true);
  });

  it("imports a valid file and replaces the draft", async () => {
    await importFile("demo.json", DEMO_JSON);

    expect(editor.getDraft().config.id).toBe("demo");
    expect(document.querySelector("#import-status")?.textContent).toContain("Imported bot 'demo'");
    expect(field("config.name").value).toBe("AskHarbor");
    const root = previewRoot();
    root.querySelector<HTMLButtonElement>(".launcher")!.click();
    expect(root.querySelector(".message.bot")?.textContent).toBe(
      "Hi! What can I help you with?",
    );
  });

  it("keeps the draft and lists the problems when an import is invalid", async () => {
    setField("config.name", "Precious work");
    // Reference problems only surface once the shape is valid, mirroring the
    // server, so this file is well shaped but points at a missing answer.
    const broken = JSON.parse(DEMO_JSON);
    broken.answers[0].next_option_ids = ["nope"];

    await importFile("broken.json", JSON.stringify(broken));

    expect(editor.getDraft().config.name).toBe("Precious work");
    expect(field("config.name").value).toBe("Precious work");
    const status = document.querySelector("#import-status")?.textContent ?? "";
    expect(status).toContain("'broken.json' was not imported");
    expect(status).toContain("Your draft is unchanged");
    expect(status).toContain(
      "answers[0].next_option_ids[0]: follow up option 'nope' has no matching answer",
    );
    expect(editor.getProblems()).toEqual([]);
  });

  it("keeps the draft when an import is not JSON at all", async () => {
    await importFile("junk.json", "{ this is not json");

    expect(editor.getDraft().config.id).toBe("my-first-bot");
    expect(document.querySelector("#import-status")?.textContent).toContain("malformed JSON");
  });

  it("exports the draft as a valid named file and refuses while invalid", () => {
    const { filename, text } = editor.buildExport();
    expect(filename).toBe("my-first-bot.json");
    expect(parseBotContent(text).problems).toEqual([]);

    const createObjectURL = vi.fn(() => "blob:fake");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", Object.assign(Object.create(URL), { createObjectURL, revokeObjectURL }));
    document.querySelector<HTMLButtonElement>("#export-button")!.click();
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(document.querySelector("#import-status")?.textContent).toContain(
      "Exported 'my-first-bot.json'",
    );

    setField("config.name", " ");
    expect(document.querySelector<HTMLButtonElement>("#export-button")?.disabled).toBe(true);
    document.querySelector<HTMLButtonElement>("#export-button")!.click();
    expect(createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("an exported starter draft matches the shared fixture the API tests load", () => {
    const fixture = readFileSync(
      resolve(process.cwd(), "../fixtures/content/valid/editor-starter.json"),
      "utf-8",
    );
    expect(editor.buildExport().text).toBe(fixture);
  });

  it("reorders opening questions with the move buttons", async () => {
    await importFile("demo.json", DEMO_JSON);
    const openingList = document.querySelector('[data-path="config.opening_option_ids"]')!;
    const down = openingList.querySelector<HTMLButtonElement>('[aria-label="Move opening question 1 down"]')!;
    down.click();

    expect(editor.getDraft().config.opening_option_ids).toEqual([
      "features",
      "getting-started",
      "contact",
    ]);
    expect(editor.getProblems()).toEqual([]);
  });
});

describe("draft transport", () => {
  it("serves config and answers from the document and rejects unknown options", async () => {
    const transport = draftTransport(starterDraft());
    const config = await transport.getConfig();
    expect(config.options).toEqual([
      { id: "example-question", label: "Where does this answer come from?" },
    ]);

    const reply = await transport.sendMessage("example-question");
    expect(reply.answer).toContain("From your draft.");
    expect(reply.options).toEqual([{ id: "second-question", label: "What else can I add?" }]);

    await expect(transport.sendMessage("missing")).rejects.toThrow("Unknown option");
  });
});

describe("widget transport seam", () => {
  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
  });

  it("uses a provided transport instead of fetch", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("no network")));
    const widget = new AskHarborWidget({ transport: draftTransport(starterDraft()) });
    await widget.init();

    const root = document.querySelector<HTMLElement>("[data-askharbor]")!.shadowRoot!;
    expect(root.querySelector(".launcher")?.getAttribute("aria-label")).toBe("Open the FAQ");
    expect(fetch).not.toHaveBeenCalled();
    widget.destroy();
  });

  it("requires either a transport or apiUrl and botId", () => {
    expect(() => new AskHarborWidget({})).toThrow("apiUrl and botId, or a transport");
    expect(() => new AskHarborWidget({ apiUrl: "https://api.example.com" })).toThrow();
  });
});
