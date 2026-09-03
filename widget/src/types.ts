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

export interface WidgetOptions {
  apiUrl: string;
  botId: string;
  container?: HTMLElement;
}
