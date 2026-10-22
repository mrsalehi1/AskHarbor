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

describe("AskHarborWidget", () => {
  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
  });

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
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => config })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ answer: "It is free.", options: [] }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const widget = new AskHarborWidget({ apiUrl: "https://api.example.com", botId: "demo" });
    await widget.init();

    const host = document.querySelector<HTMLElement>("[data-askharbor='widget']");
    host?.shadowRoot?.querySelector<HTMLButtonElement>(".option")?.click();
    await vi.waitFor(() => {
      expect(host?.shadowRoot?.textContent).toContain("It is free.");
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
  afterEach(() => {
    document.body.replaceChildren();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const failure = { ok: false, status: 503 };
  const success = {
    ok: true,
    json: async () => ({
      answer: "It is free.",
      options: [{ id: "trial", label: "Is there a trial?" }],
    }),
  };

  async function startWidget(responses: unknown[]) {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => config });
    for (const response of responses) fetchMock.mockResolvedValueOnce(response);
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const widget = new AskHarborWidget({ apiUrl: "https://api.example.com", botId: "demo" });
    await widget.init();
    const root = document.querySelector<HTMLElement>("[data-askharbor='widget']")!.shadowRoot!;
    return { fetchMock, root };
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
