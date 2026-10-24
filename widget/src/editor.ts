import { mountEditor } from "./editor-app";

const root = document.getElementById("askharbor-editor");
if (root) {
  mountEditor(root);
} else {
  console.error("AskHarbor editor: no element with id 'askharbor-editor' found.");
}
