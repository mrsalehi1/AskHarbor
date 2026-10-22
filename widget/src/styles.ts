export const styles = `
  :host {
    --ah-primary: #155eef;
    color: #101828;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    line-height: 1.4;
  }
  * { box-sizing: border-box; }
  button { font: inherit; }
  .launcher {
    align-items: center;
    background: var(--ah-primary);
    border: 0;
    border-radius: 999px;
    bottom: 20px;
    box-shadow: 0 8px 24px rgb(16 24 40 / 24%);
    color: white;
    cursor: pointer;
    display: flex;
    height: 56px;
    justify-content: center;
    position: fixed;
    right: 20px;
    width: 56px;
    z-index: 2147483000;
  }
  .launcher:focus-visible, .close:focus-visible, .option:focus-visible, .back:focus-visible {
    outline: 3px solid #84adff;
    outline-offset: 2px;
  }
  .panel {
    background: white;
    border: 1px solid #eaecf0;
    border-radius: 16px;
    bottom: 88px;
    box-shadow: 0 16px 40px rgb(16 24 40 / 20%);
    display: flex;
    flex-direction: column;
    max-height: min(560px, calc(100vh - 112px));
    overflow: hidden;
    position: fixed;
    right: 20px;
    width: min(360px, calc(100vw - 32px));
    z-index: 2147482999;
  }
  .panel[hidden] { display: none; }
  .header {
    align-items: center;
    background: var(--ah-primary);
    color: white;
    display: flex;
    justify-content: space-between;
    min-height: 60px;
    padding: 12px 16px;
  }
  .title { font-size: 16px; font-weight: 650; }
  .controls { align-items: center; display: flex; gap: 8px; }
  .back {
    background: rgb(255 255 255 / 16%);
    border: 0;
    border-radius: 8px;
    color: white;
    cursor: pointer;
    font-size: 13px;
    padding: 6px 10px;
  }
  .back:hover { background: rgb(255 255 255 / 28%); }
  .back[hidden] { display: none; }
  .close {
    background: transparent;
    border: 0;
    color: white;
    cursor: pointer;
    font-size: 24px;
    line-height: 1;
    padding: 4px;
  }
  .conversation {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
    padding: 16px;
  }
  .message {
    border-radius: 12px;
    font-size: 14px;
    margin: 0;
    max-width: 90%;
    padding: 10px 12px;
    white-space: pre-wrap;
  }
  .bot { align-self: flex-start; background: #f2f4f7; }
  .user { align-self: flex-end; background: var(--ah-primary); color: white; }
  .options { display: grid; gap: 8px; }
  .option {
    background: white;
    border: 1px solid #b2ccff;
    border-radius: 10px;
    color: #1849a9;
    cursor: pointer;
    padding: 9px 12px;
    text-align: left;
  }
  .option:hover { background: #eff4ff; }
  .option:disabled { cursor: wait; opacity: .6; }
  .status { color: #667085; font-size: 13px; margin: 0; }
  @media (max-width: 480px) {
    .panel { bottom: 84px; left: 16px; right: 16px; width: auto; }
    .launcher { bottom: 16px; right: 16px; }
  }
  @media (prefers-reduced-motion: no-preference) {
    .panel { animation: ah-enter 160ms ease-out; }
    @keyframes ah-enter { from { opacity: 0; transform: translateY(8px); } }
  }
`;
