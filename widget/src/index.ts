import { AskHarborWidget } from "./widget";
import type { WidgetOptions } from "./types";

function create(options: WidgetOptions): AskHarborWidget {
  const widget = new AskHarborWidget(options);
  void widget.init();
  return widget;
}

const embedScript = document.currentScript as HTMLScriptElement | null;
const embedOptions = embedScript?.dataset.apiUrl
  ? { apiUrl: embedScript.dataset.apiUrl, botId: embedScript.dataset.botId ?? "demo" }
  : undefined;

function autoStart(): void {
  if (embedOptions) create(embedOptions);
}

export { AskHarborWidget, create };
export type { WidgetOptions };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", autoStart, { once: true });
} else {
  autoStart();
}
