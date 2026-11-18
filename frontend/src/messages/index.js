import { en } from "./en.js";

const catalogues = { en };

export function getMessages(lang = "en") {
  return catalogues[lang] ?? en;
}
