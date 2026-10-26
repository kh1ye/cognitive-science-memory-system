import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { registerMemoryTools } from "./register.mjs";

export default definePluginEntry({
  id: "cognitive-memory",
  name: "Cognitive Memory",
  description: "Local memory search and explicit save",
  register: registerMemoryTools,
});
