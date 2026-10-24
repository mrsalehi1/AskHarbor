export interface ChatOption {
  id: string;
  label: string;
}

export interface BotConfig {
  id: string;
  name: string;
  greeting: string;
  launcher_label: string;
  primary_color: string;
  options: ChatOption[];
}

export interface MessageResponse {
  answer: string;
  options: ChatOption[];
}

/**
 * Where the widget gets its configuration and answers. Embeds use the HTTP
 * transport against the API; the local editor supplies one backed by the
 * draft, so the preview never leaves the browser.
 */
export interface BotTransport {
  getConfig(): Promise<BotConfig>;
  sendMessage(optionId: string): Promise<MessageResponse>;
}

export interface WidgetOptions {
  apiUrl?: string;
  botId?: string;
  container?: HTMLElement;
  transport?: BotTransport;
}
