import { mountAdmin } from "./admin-app";

const root = document.getElementById("askharbor-admin");
if (root) {
  mountAdmin(root);
} else {
  console.error("AskHarbor panel: no element with id 'askharbor-admin' found.");
}
