import { styles } from "./styles";
import { HttpTransport } from "./transport";
import type { BotConfig, BotTransport, ChatOption, WidgetOptions } from "./types";

export class AskHarborWidget {
  private readonly transport: BotTransport;
  private readonly host: HTMLElement;
  private readonly shadow: ShadowRoot;
  private config?: BotConfig;
  private panel?: HTMLElement;
  private conversation?: HTMLElement;
  private launcher?: HTMLButtonElement;
  private backButton?: HTMLButtonElement;
  /** Increments whenever the visitor returns to the menu, so late replies are ignored. */
  private flow = 0;

  constructor(options: WidgetOptions) {
    if (options.transport) {
      this.transport = options.transport;
    } else if (options.apiUrl && options.botId) {
      this.transport = new HttpTransport(options.apiUrl, options.botId);
    } else {
      throw new Error("AskHarbor needs apiUrl and botId, or a transport.");
    }
    this.host = document.createElement("div");
    this.host.dataset.askharbor = "widget";
    this.shadow = this.host.attachShadow({ mode: "open" });
    (options.container ?? document.body).append(this.host);
  }

  async init(): Promise<void> {
    try {
      this.config = await this.transport.getConfig();
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
    this.backButton = document.createElement("button");
    this.backButton.className = "back";
    this.backButton.type = "button";
    this.backButton.hidden = true;
    this.backButton.setAttribute("aria-label", "Back to menu");
    this.backButton.textContent = "\u2190 Menu";
    this.backButton.addEventListener("click", () => this.showMenu(true));
    const title = document.createElement("span");
    title.className = "title";
    title.textContent = this.config.name;
    const close = document.createElement("button");
    close.className = "close";
    close.type = "button";
    close.setAttribute("aria-label", "Close chat");
    close.textContent = "×";
    close.addEventListener("click", () => this.toggle(false));
    header.append(this.backButton, title, close);

    this.conversation = document.createElement("div");
    this.conversation.className = "conversation";
    this.conversation.setAttribute("aria-live", "polite");
    this.showMenu(false);

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

  /**
   * Replaces the transcript with the greeting and opening questions from the
   * loaded configuration. Any reply still in flight belongs to an old flow and
   * is dropped when it arrives.
   */
  private showMenu(focusFirstOption: boolean): void {
    if (!this.config || !this.conversation || !this.backButton) return;
    this.flow += 1;
    this.conversation.replaceChildren();
    this.backButton.hidden = true;
    this.addMessage(this.config.greeting, "bot");
    this.showOptions(this.config.options);
    if (focusFirstOption) this.conversation.querySelector<HTMLButtonElement>(".option")?.focus();
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
    const flow = this.flow;
    status.textContent = "Finding an answer…";
    if (this.conversation) this.conversation.scrollTop = this.conversation.scrollHeight;

    try {
      const result = await this.transport.sendMessage(option.id);
      if (flow !== this.flow) return;
      status.remove();
      this.addMessage(result.answer, "bot");
      this.showOptions(result.options);
    } catch (error) {
      if (flow !== this.flow) return;
      console.error("AskHarbor message failed:", error);
      status.textContent = "Sorry, the answer could not be loaded. Please try again.";
      this.showOptions([option], (retryOption, retryGroup) => {
        retryGroup.remove();
        void this.requestAnswer(retryOption, status);
      });
    }
  }
}
