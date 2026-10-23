import type { BotConfig, BotTransport, MessageResponse } from "./types";

/** Talks to the AskHarbor API over HTTP. This is what embedded widgets use. */
export class HttpTransport implements BotTransport {
  private readonly apiUrl: string;
  private readonly botId: string;

  constructor(apiUrl: string, botId: string) {
    this.apiUrl = apiUrl.replace(/\/$/, "");
    this.botId = botId;
  }

  async getConfig(): Promise<BotConfig> {
    const response = await fetch(
      `${this.apiUrl}/api/v1/bots/${encodeURIComponent(this.botId)}`,
    );
    if (!response.ok) throw new Error(`Configuration request failed (${response.status})`);
    return (await response.json()) as BotConfig;
  }

  async sendMessage(optionId: string): Promise<MessageResponse> {
    const response = await fetch(
      `${this.apiUrl}/api/v1/bots/${encodeURIComponent(this.botId)}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ option_id: optionId }),
      },
    );
    if (!response.ok) throw new Error(`Message request failed (${response.status})`);
    return (await response.json()) as MessageResponse;
  }
}
