import { styles } from "./styles";
import type { BotConfig, ChatOption, MessageResponse, WidgetOptions } from "./types";

export class AskHarborWidget {
  private readonly apiUrl: string;
  private readonly botId: string;
  private readonly host: HTMLElement;
  private readonly shadow: ShadowRoot;
  private config?: BotConfig;
  private panel?: HTMLElement;
  private conversation?: HTMLElement;
  private launcher?: HTMLButtonElement;
  private backButton?: HTMLButtonElement;
  /** Incremented when the visitor leaves a flow, so late replies can be ignored. */
  private requestGeneration = 0;

  constructor(options: WidgetOptions) {
    this.apiUrl = options.apiUrl.replace(/\/$/, "");
    this.botId = options.botId;
    this.host = document.createElement("div");
    this.host.dataset.askharbor = "widget";
    this.shadow = this.host.attachShadow({ mode: "open" });
    (options.container ?? document.body).append(this.host);
  }

  async init(): Promise<void> {
    try {
      const response = await fetch(
        `${this.apiUrl}/api/v1/bots/${encodeURIComponent(this.botId)}`,
      );
      if (!response.ok) throw new Error(`Configuration request failed (${response.status})`);
      this.config = (await response.json()) as BotConfig;
      this.render();
    } catch (error) {
      console.error("AskHarbor could not start:", error);
      this.host.remove();
    }
  }

  destroy(): void {
    this.host.remove();
  }

  private render(): void {
    if (!this.config) return;

    const style = document.createElement("style");
    style.textContent = styles;

    this.launcher = document.createElement("button");
    this.launcher.className = "launcher";
    this.launcher.type = "button";
    this.launcher.setAttribute("aria-expanded", "false");
    this.launcher.setAttribute("aria-label", this.config.launcher_label);
    this.launcher.textContent = "✦";
    this.launcher.addEventListener("click", () => this.toggle(true));

    this.panel = document.createElement("section");
    this.panel.className = "panel";
    this.panel.hidden = true;
    this.panel.setAttribute("role", "dialog");
    this.panel.setAttribute("aria-label", this.config.name);
    this.panel.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this.toggle(false);
    });

    const header = document.createElement("header");
    header.className = "header";
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = this.config.name;
    const close = document.createElement("button");
    close.className = "close";
    close.type = "button";
    close.setAttribute("aria-label", "Close chat");
    close.textContent = "×";
    close.addEventListener("click", () => this.toggle(false));
    this.backButton = document.createElement("button");
    this.backButton.className = "back";
    this.backButton.type = "button";
    this.backButton.textContent = "Back to menu";
    this.backButton.hidden = true;
    this.backButton.addEventListener("click", () => this.backToMenu());
    const controls = document.createElement("div");
    controls.className = "controls";
    controls.append(this.backButton, close);
    header.append(title, controls);

    this.conversation = document.createElement("div");
    this.conversation.className = "conversation";
    this.conversation.setAttribute("aria-live", "polite");
    this.addMessage(this.config.greeting, "bot");
    this.showOptions(this.config.options);

    this.panel.append(header, this.conversation);
    this.shadow.append(style, this.panel, this.launcher);
    this.host.style.setProperty("--ah-primary", this.config.primary_color);
  }

  private toggle(open: boolean): void {
    if (!this.panel || !this.launcher) return;
    this.panel.hidden = !open;
    this.launcher.setAttribute("aria-expanded", String(open));
    if (open) {
      const target = this.panel.querySelector<HTMLButtonElement>(".option, .close");
      target?.focus();
    } else {
      this.launcher.focus();
    }
  }

  private addMessage(text: string, sender: "bot" | "user"): void {
    if (!this.conversation) return;
    const message = document.createElement("p");
    message.className = `message ${sender}`;
    message.textContent = text;
    this.conversation.append(message);
    this.conversation.scrollTop = this.conversation.scrollHeight;
  }

  private showOptions(
    options: ChatOption[],
    onSelect: (option: ChatOption, group: HTMLElement) => void = (option, group) =>
      void this.selectOption(option, group),
  ): void {
    if (!this.conversation || options.length === 0) return;
    const group = document.createElement("div");
    group.className = "options";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", "Choose a question");
    for (const option of options) {
      const button = document.createElement("button");
      button.className = "option";
      button.type = "button";
      button.textContent = option.label;
      button.addEventListener("click", () => onSelect(option, group));
      group.append(button);
    }
    this.conversation.append(group);
  }

  private async selectOption(option: ChatOption, group: HTMLElement): Promise<void> {
    group.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
    this.addMessage(option.label, "user");
    group.remove();
    if (this.backButton) this.backButton.hidden = false;

    const status = document.createElement("p");
    status.className = "status";
    this.conversation?.append(status);
    await this.requestAnswer(option, status);
  }

  /**
   * Requests the answer for an option. The same status element is reused for
   * every attempt, so a retry never duplicates the question or stacks errors.
   */
  private async requestAnswer(option: ChatOption, status: HTMLElement): Promise<void> {
    const generation = this.requestGeneration;
    status.textContent = "Finding an answer…";
    if (this.conversation) this.conversation.scrollTop = this.conversation.scrollHeight;

    try {
      const response = await fetch(
        `${this.apiUrl}/api/v1/bots/${encodeURIComponent(this.botId)}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ option_id: option.id }),
        },
      );
      if (!response.ok) throw new Error(`Message request failed (${response.status})`);
      const result = (await response.json()) as MessageResponse;
      if (generation !== this.requestGeneration) return;
      status.remove();
      this.addMessage(result.answer, "bot");
      this.showOptions(result.options);
    } catch (error) {
      console.error("AskHarbor message failed:", error);
      if (generation !== this.requestGeneration) return;
      status.textContent = "Sorry, the answer could not be loaded. Please try again.";
      this.showOptions([option], (retryOption, retryGroup) => {
        retryGroup.remove();
        void this.requestAnswer(retryOption, status);
      });
    }
  }

  /** Restores the opening questions from the already loaded configuration. */
  private backToMenu(): void {
    if (!this.config || !this.conversation) return;
    this.requestGeneration += 1;
    this.conversation.replaceChildren();
    this.addMessage(this.config.greeting, "bot");
    this.showOptions(this.config.options);
    if (this.backButton) this.backButton.hidden = true;
    this.conversation.querySelector<HTMLButtonElement>(".option")?.focus();
  }
}
