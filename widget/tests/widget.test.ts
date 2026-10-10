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
