// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskHarborWidget } from "../src/widget";

const config = {
  id: "demo",
  name: "Test support",
  greeting: "How can we help?",
  launcher_label: "Open test support",
  primary_color: "#123456",
  options: [{ id: "pricing", label: "What does it cost?" }],
};

const failure = { ok: false, status: 503 };
const success = {
  ok: true,
  json: async () => ({
    answer: "It is free.",
    options: [{ id: "trial", label: "Is there a trial?" }],
  }),
};
const finalAnswer = {
  ok: true,
  json: async () => ({ answer: "It is free.", options: [] }),
};

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function startWidget(responses: unknown[] = []) {
  const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => config });
  for (const response of responses) {
    if (response instanceof Promise) fetchMock.mockReturnValueOnce(response);
    else fetchMock.mockResolvedValueOnce(response);
  }
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  const widget = new AskHarborWidget({ apiUrl: "https://api.example.com", botId: "demo" });
  await widget.init();
  const root = document.querySelector<HTMLElement>("[data-askharbor='widget']")!.shadowRoot!;
  return { fetchMock, root, widget };
}

function count(root: ShadowRoot, selector: string, text?: string): number {
  return Array.from(root.querySelectorAll(selector)).filter(
    (element) => text === undefined || element.textContent?.includes(text),
  ).length;
}

function clickOption(root: ShadowRoot, label: string): void {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>(".option")).find(
    (candidate) => candidate.textContent === label,
  );
  expect(button, `option "${label}" should be visible`).toBeDefined();
  button!.click();
}

function backButton(root: ShadowRoot): HTMLButtonElement {
  const button = root.querySelector<HTMLButtonElement>(".back");
  expect(button, "back to menu button should exist").not.toBeNull();
  return button!;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("AskHarborWidget", () => {
  it("loads configuration and opens an accessible panel", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => config,
    }));
    const widget = new AskHarborWidget({ apiUrl: "https://api.example.com/", botId: "demo" });

    await widget.init();

    const host = document.querySelector<HTMLElement>("[data-askharbor='widget']");
    const launcher = host?.shadowRoot?.querySelector<HTMLButtonElement>(".launcher");
    const panel = host?.shadowRoot?.querySelector<HTMLElement>(".panel");
    expect(launcher?.getAttribute("aria-label")).toBe("Open test support");
    launcher?.click();
    expect(panel?.hidden).toBe(false);
  });

  it("sends the selected option and displays the answer", async () => {
    const { fetchMock, root } = await startWidget([
      { ok: true, json: async () => ({ answer: "It is free.", options: [] }) },
    ]);

    root.querySelector<HTMLButtonElement>(".option")?.click();
    await vi.waitFor(() => {
      expect(root.textContent).toContain("It is free.");
    });
    expect(fetchMock).toHaveBeenLastCalledWith(
      "https://api.example.com/api/v1/bots/demo/messages",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("removes itself when configuration cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404 }));
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const widget = new AskHarborWidget({ apiUrl: "https://api.example.com", botId: "missing" });

    await widget.init();

    expect(document.querySelector("[data-askharbor='widget']")).toBeNull();
  });
});

describe("AskHarborWidget retry behavior", () => {
  it("shows the question, answer and follow ups once after a successful request", async () => {
    const { root } = await startWidget([success]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".message.bot", "It is free.")).toBe(1));

    expect(count(root, ".message.user", "What does it cost?")).toBe(1);
    expect(count(root, ".status")).toBe(0);
    expect(count(root, ".option", "Is there a trial?")).toBe(1);
  });

  it("clears the error after one failure followed by a successful retry", async () => {
    const { fetchMock, root } = await startWidget([failure, success]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".status", "Sorry")).toBe(1));
    expect(count(root, ".message.user", "What does it cost?")).toBe(1);
    expect(count(root, ".option", "What does it cost?")).toBe(1);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".message.bot", "It is free.")).toBe(1));

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(count(root, ".message.user", "What does it cost?")).toBe(1);
    expect(count(root, ".status")).toBe(0);
    expect(count(root, ".option", "Is there a trial?")).toBe(1);
    expect(count(root, ".option", "What does it cost?")).toBe(0);
  });

  it("keeps a single error and retry option across repeated failures", async () => {
    const { fetchMock, root } = await startWidget([failure, failure, failure, success]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".status", "Sorry")).toBe(1));

    for (let attempt = 0; attempt < 2; attempt += 1) {
      clickOption(root, "What does it cost?");
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3 + attempt));
      await vi.waitFor(() => expect(count(root, ".status", "Sorry")).toBe(1));
      expect(count(root, ".status")).toBe(1);
      expect(count(root, ".message.user", "What does it cost?")).toBe(1);
      expect(count(root, ".option", "What does it cost?")).toBe(1);
    }

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".message.bot", "It is free.")).toBe(1));

    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(count(root, ".message.user", "What does it cost?")).toBe(1);
    expect(count(root, ".status")).toBe(0);
    expect(count(root, ".option", "Is there a trial?")).toBe(1);
    expect(count(root, ".option", "What does it cost?")).toBe(0);
  });
});

describe("AskHarborWidget back to menu", () => {
  it("is hidden on the opening menu and restores it after a final answer", async () => {
    const { root } = await startWidget([finalAnswer]);
    const back = backButton(root);
    expect(back.hidden).toBe(true);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".message.bot", "It is free.")).toBe(1));
    expect(back.hidden).toBe(false);
    expect(count(root, ".option")).toBe(0);

    back.click();

    expect(back.hidden).toBe(true);
    expect(count(root, ".message.bot", "How can we help?")).toBe(1);
    expect(count(root, ".option", "What does it cost?")).toBe(1);
    expect(count(root, ".message.bot", "It is free.")).toBe(0);
  });

  it("returns to the menu from the middle of a conversation", async () => {
    const { root } = await startWidget([success]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".option", "Is there a trial?")).toBe(1));

    backButton(root).click();

    expect(count(root, ".option", "Is there a trial?")).toBe(0);
    expect(count(root, ".option", "What does it cost?")).toBe(1);
    expect(count(root, ".option")).toBe(1);
  });

  it("clears a failed request when returning to the menu", async () => {
    const { root } = await startWidget([failure]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".status", "Sorry")).toBe(1));

    backButton(root).click();

    expect(count(root, ".status")).toBe(0);
    expect(count(root, ".option", "What does it cost?")).toBe(1);
    expect(count(root, ".option")).toBe(1);
    expect(backButton(root).hidden).toBe(true);
  });

  it("ignores a late successful reply after returning to the menu", async () => {
    const pending = deferred<unknown>();
    const { root } = await startWidget([pending.promise]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".status", "Finding")).toBe(1));
    expect(backButton(root).hidden).toBe(false);

    backButton(root).click();
    expect(count(root, ".option", "What does it cost?")).toBe(1);

    pending.resolve(success);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(count(root, ".message.bot", "It is free.")).toBe(0);
    expect(count(root, ".option", "Is there a trial?")).toBe(0);
    expect(count(root, ".option", "What does it cost?")).toBe(1);
    expect(count(root, ".option")).toBe(1);
    expect(count(root, ".status")).toBe(0);
  });

  it("ignores a late failure after returning to the menu", async () => {
    const pending = deferred<unknown>();
    const { root } = await startWidget([pending.promise]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".status", "Finding")).toBe(1));

    backButton(root).click();

    pending.reject(new Error("network down"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(count(root, ".status")).toBe(0);
    expect(count(root, ".option")).toBe(1);
    expect(count(root, ".option", "What does it cost?")).toBe(1);
  });

  it("is a native button that works from the keyboard and moves focus to the menu", async () => {
    const { root } = await startWidget([success]);

    clickOption(root, "What does it cost?");
    await vi.waitFor(() => expect(count(root, ".option", "Is there a trial?")).toBe(1));

    const back = backButton(root);
    expect(back.tagName).toBe("BUTTON");
    expect(back.type).toBe("button");
    back.focus();
    expect(root.activeElement).toBe(back);

    back.click();

    expect(root.activeElement?.textContent).toBe("What does it cost?");
  });
});
