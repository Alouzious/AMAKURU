import { en, type Messages } from "./en";

const catalogues: Record<string, Messages> = { en };

export function getMessages(lang: string = "en"): Messages {
  return catalogues[lang] ?? en;
}

export type { Messages };
