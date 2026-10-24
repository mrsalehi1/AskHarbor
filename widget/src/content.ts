/**
 * Bot content validation for the browser, mirroring server/app/content.py.
 *
 * Both sides must accept and reject the same documents for the same reasons,
 * with the same problem paths and the same message vocabulary. The shared
 * fixtures in fixtures/content at the repository root hold the agreed cases;
 * when a rule changes, change it in both files and add a fixture.
 */

export const FORMAT_VERSION = 1;

export const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;
export const HEX_COLOR_PATTERN = /^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/;

export const MAX_ID_LENGTH = 100;
export const MAX_NAME_LENGTH = 80;
export const MAX_GREETING_LENGTH = 500;
export const MAX_LAUNCHER_LABEL_LENGTH = 120;
export const MAX_LABEL_LENGTH = 200;
export const MAX_ANSWER_LENGTH = 4000;

export interface ContentProblem {
  /** Dotted path with bracket indexes, e.g. "answers[1].next_option_ids[0]". "" is the root. */
  path: string;
  message: string;
}

export interface BotContentConfig {
  id: string;
  name: string;
  greeting: string;
  launcher_label: string;
  primary_color: string;
  opening_option_ids: string[];
}

export interface AnswerEntry {
  id: string;
  label: string;
  answer: string;
  next_option_ids?: string[];
}

export interface BotContentDocument {
  format_version: number;
  config: BotContentConfig;
  answers: AnswerEntry[];
}

const MESSAGES = {
  required: "field is required",
  unknown: "unknown field",
  object: "must be a JSON object",
  list: "must be a list",
  text: "must be text",
  wholeNumber: "must be a whole number",
  blank: "text must not be blank",
  hexColor: "must be a hex color like #155eef or #fff",
  idPattern: "must start with a letter or digit and use only letters, digits, - and _",
  atLeast: (count: number) => `must have at least ${count} item(s)`,
  atMost: (count: number) => `must be at most ${count} characters`,
  unsupportedVersion: (value: number) =>
    `unsupported format_version ${value}; this server reads version ${FORMAT_VERSION}`,
} as const;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function checkUnknownKeys(
  value: Record<string, unknown>,
  known: readonly string[],
  prefix: string,
  problems: ContentProblem[],
): void {
  for (const key of Object.keys(value)) {
    if (!known.includes(key)) {
      problems.push({ path: prefix ? `${prefix}.${key}` : key, message: MESSAGES.unknown });
    }
  }
}

function checkText(
  value: unknown,
  path: string,
  maxLength: number,
  problems: ContentProblem[],
): void {
  if (typeof value !== "string") {
    problems.push({ path, message: MESSAGES.text });
  } else if (value.length > maxLength) {
    problems.push({ path, message: MESSAGES.atMost(maxLength) });
  } else if (!value.trim()) {
    problems.push({ path, message: MESSAGES.blank });
  }
}

function checkId(value: unknown, path: string, problems: ContentProblem[]): void {
  if (typeof value !== "string") {
    problems.push({ path, message: MESSAGES.text });
  } else if (value.length > MAX_ID_LENGTH) {
    problems.push({ path, message: MESSAGES.atMost(MAX_ID_LENGTH) });
  } else if (!ID_PATTERN.test(value)) {
    problems.push({ path, message: MESSAGES.idPattern });
  }
}

function checkRequired(
  value: Record<string, unknown>,
  key: string,
  path: string,
  problems: ContentProblem[],
): boolean {
  if (key in value) return true;
  problems.push({ path, message: MESSAGES.required });
  return false;
}

const ROOT_KEYS = ["format_version", "config", "answers"] as const;
const CONFIG_KEYS = [
  "id",
  "name",
  "greeting",
  "launcher_label",
  "primary_color",
  "opening_option_ids",
] as const;
const ANSWER_KEYS = ["id", "label", "answer", "next_option_ids"] as const;

function checkConfigShape(value: unknown, problems: ContentProblem[]): void {
  if (!isPlainObject(value)) {
    problems.push({ path: "config", message: MESSAGES.object });
    return;
  }
  checkUnknownKeys(value, CONFIG_KEYS, "config", problems);
  if (checkRequired(value, "id", "config.id", problems)) {
    checkId(value.id, "config.id", problems);
  }
  if (checkRequired(value, "name", "config.name", problems)) {
    checkText(value.name, "config.name", MAX_NAME_LENGTH, problems);
  }
  if (checkRequired(value, "greeting", "config.greeting", problems)) {
    checkText(value.greeting, "config.greeting", MAX_GREETING_LENGTH, problems);
  }
  if (checkRequired(value, "launcher_label", "config.launcher_label", problems)) {
    checkText(value.launcher_label, "config.launcher_label", MAX_LAUNCHER_LABEL_LENGTH, problems);
  }
  if (checkRequired(value, "primary_color", "config.primary_color", problems)) {
    if (typeof value.primary_color !== "string") {
      problems.push({ path: "config.primary_color", message: MESSAGES.text });
    } else if (!HEX_COLOR_PATTERN.test(value.primary_color)) {
      problems.push({ path: "config.primary_color", message: MESSAGES.hexColor });
    }
  }
  if (checkRequired(value, "opening_option_ids", "config.opening_option_ids", problems)) {
    checkIdList(value.opening_option_ids, "config.opening_option_ids", 1, problems);
  }
}

function checkIdList(
  value: unknown,
  path: string,
  minLength: number,
  problems: ContentProblem[],
): void {
  if (!Array.isArray(value)) {
    problems.push({ path, message: MESSAGES.list });
    return;
  }
  if (value.length < minLength) {
    problems.push({ path, message: MESSAGES.atLeast(minLength) });
  }
  value.forEach((item, index) => checkId(item, `${path}[${index}]`, problems));
}

function checkAnswerShape(value: unknown, path: string, problems: ContentProblem[]): void {
  if (!isPlainObject(value)) {
    problems.push({ path, message: MESSAGES.object });
    return;
  }
  checkUnknownKeys(value, ANSWER_KEYS, path, problems);
  if (checkRequired(value, "id", `${path}.id`, problems)) {
    checkId(value.id, `${path}.id`, problems);
  }
  if (checkRequired(value, "label", `${path}.label`, problems)) {
    checkText(value.label, `${path}.label`, MAX_LABEL_LENGTH, problems);
  }
  if (checkRequired(value, "answer", `${path}.answer`, problems)) {
    checkText(value.answer, `${path}.answer`, MAX_ANSWER_LENGTH, problems);
  }
  if ("next_option_ids" in value) {
    checkIdList(value.next_option_ids, `${path}.next_option_ids`, 0, problems);
  }
}

function findShapeProblems(data: unknown): ContentProblem[] {
  if (!isPlainObject(data)) {
    return [{ path: "", message: MESSAGES.object }];
  }
  const problems: ContentProblem[] = [];
  checkUnknownKeys(data, ROOT_KEYS, "", problems);
  if (checkRequired(data, "format_version", "format_version", problems)) {
    if (typeof data.format_version !== "number" || !Number.isInteger(data.format_version)) {
      problems.push({ path: "format_version", message: MESSAGES.wholeNumber });
    } else if (data.format_version !== FORMAT_VERSION) {
      problems.push({
        path: "format_version",
        message: MESSAGES.unsupportedVersion(data.format_version),
      });
    }
  }
  if (checkRequired(data, "config", "config", problems)) {
    checkConfigShape(data.config, problems);
  }
  if (checkRequired(data, "answers", "answers", problems)) {
    if (!Array.isArray(data.answers)) {
      problems.push({ path: "answers", message: MESSAGES.list });
    } else {
      if (data.answers.length < 1) {
        problems.push({ path: "answers", message: MESSAGES.atLeast(1) });
      }
      data.answers.forEach((entry, index) =>
        checkAnswerShape(entry, `answers[${index}]`, problems),
      );
    }
  }
  return problems;
}

/** Duplicate IDs and references to answers that do not exist. Mirrors the server. */
export function findReferenceProblems(content: BotContentDocument): ContentProblem[] {
  const problems: ContentProblem[] = [];
  const firstSeen = new Map<string, number>();
  content.answers.forEach((entry, index) => {
    const first = firstSeen.get(entry.id);
    if (first !== undefined) {
      problems.push({
        path: `answers[${index}].id`,
        message: `duplicate answer id '${entry.id}' (first defined at answers[${first}])`,
      });
    } else {
      firstSeen.set(entry.id, index);
    }
  });

  const checkList = (path: string, optionIds: string[], what: string): void => {
    const seen = new Set<string>();
    optionIds.forEach((optionId, index) => {
      const location = `${path}[${index}]`;
      if (seen.has(optionId)) {
        problems.push({ path: location, message: `duplicate ${what} '${optionId}'` });
      }
      seen.add(optionId);
      if (!firstSeen.has(optionId)) {
        problems.push({ path: location, message: `${what} '${optionId}' has no matching answer` });
      }
    });
  };

  checkList("config.opening_option_ids", content.config.opening_option_ids, "opening option");
  content.answers.forEach((entry, index) =>
    checkList(`answers[${index}].next_option_ids`, entry.next_option_ids ?? [], "follow up option"),
  );
  return problems;
}

/**
 * Validate parsed JSON data as a bot content document. Shape problems are
 * reported first; cross references are only checked once the shape is valid,
 * because their paths assume well formed answers. Returns every problem found
 * at that stage, or an empty list when the document is valid.
 */
export function validateBotContent(data: unknown): ContentProblem[] {
  const problems = findShapeProblems(data);
  if (problems.length > 0) return problems;
  return findReferenceProblems(data as unknown as BotContentDocument);
}

export interface ParseResult {
  document?: BotContentDocument;
  problems: ContentProblem[];
}

/** Parse and validate raw JSON text. Malformed JSON is reported at the root. */
export function parseBotContent(text: string): ParseResult {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (error) {
    return { problems: [{ path: "", message: `malformed JSON: ${(error as Error).message}` }] };
  }
  const problems = validateBotContent(data);
  if (problems.length > 0) return { problems };
  return { document: data as BotContentDocument, problems: [] };
}

/**
 * Serialize a document in the content file layout: stable key order, two space
 * indentation, a trailing newline, and next_option_ids omitted when empty, so
 * an unchanged import exports byte for byte identically.
 */
export function serializeBotContent(document: BotContentDocument): string {
  const ordered = {
    format_version: FORMAT_VERSION,
    config: {
      id: document.config.id,
      name: document.config.name,
      greeting: document.config.greeting,
      launcher_label: document.config.launcher_label,
      primary_color: document.config.primary_color,
      opening_option_ids: [...document.config.opening_option_ids],
    },
    answers: document.answers.map((entry) => {
      const serialized: AnswerEntry = {
        id: entry.id,
        label: entry.label,
        answer: entry.answer,
      };
      if (entry.next_option_ids && entry.next_option_ids.length > 0) {
        serialized.next_option_ids = [...entry.next_option_ids];
      }
      return serialized;
    }),
  };
  return `${JSON.stringify(ordered, null, 2)}\n`;
}
