// Runs the shared content fixtures through the browser-side validation, so the
// editor and the API keep agreeing on what is valid and why. The case format is
// described in fixtures/content/README.md.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  parseBotContent,
  serializeBotContent,
  validateBotContent,
  type BotContentDocument,
} from "../src/content";

const FIXTURES = fileURLToPath(new URL("../../fixtures/content", import.meta.url));
const SERVER_CONTENT = fileURLToPath(new URL("../../server/content", import.meta.url));

function cases(directory: string): { name: string; text: string }[] {
  return readdirSync(join(FIXTURES, directory))
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => ({ name, text: readFileSync(join(FIXTURES, directory, name), "utf-8") }));
}

describe("shared valid fixtures", () => {
  it.each(cases("valid"))("$name is accepted", ({ text }) => {
    const result = parseBotContent(text);
    expect(result.problems).toEqual([]);
    expect(result.document?.config.id).toBeTruthy();
  });
});

describe("shared invalid fixtures", () => {
  it.each(cases("invalid"))("$name reports every expected problem", ({ name, text }) => {
    const testCase = JSON.parse(text) as {
      expected_problems: { path: string; contains: string }[];
      content: unknown;
    };
    expect(testCase.expected_problems.length).toBeGreaterThan(0);

    const reported = validateBotContent(testCase.content);

    for (const expected of testCase.expected_problems) {
      const matches = reported.filter(
        (problem) => problem.path === expected.path && problem.message.includes(expected.contains),
      );
      expect(
        matches.length,
        `${name}: expected a problem at '${expected.path}' containing '${expected.contains}', ` +
          `got ${JSON.stringify(reported)}`,
      ).toBeGreaterThan(0);
    }
  });
});

describe("shared malformed fixtures", () => {
  it.each(cases("malformed"))("$name is reported at the document root", ({ text }) => {
    const result = parseBotContent(text);
    expect(result.document).toBeUndefined();
    expect(result.problems).toHaveLength(1);
    expect(result.problems[0]?.path).toBe("");
    expect(result.problems[0]?.message).toContain("JSON");
  });
});

describe("serialization round trip", () => {
  const files = [
    join(SERVER_CONTENT, "demo.json"),
    join(SERVER_CONTENT, "library.json"),
    join(FIXTURES, "valid", "minimal.json"),
    join(FIXTURES, "valid", "branching.json"),
  ];

  it.each(files.map((path) => ({ path })))(
    "import then export of $path changes nothing",
    ({ path }) => {
      const original = readFileSync(path, "utf-8");
      const result = parseBotContent(original);
      expect(result.problems).toEqual([]);

      const exported = serializeBotContent(result.document as BotContentDocument);

      expect(JSON.parse(exported)).toEqual(JSON.parse(original));
      expect(parseBotContent(exported).problems).toEqual([]);
    },
  );

  it("shipped server content exports byte for byte identically", () => {
    const original = readFileSync(join(SERVER_CONTENT, "demo.json"), "utf-8");
    const document = parseBotContent(original).document as BotContentDocument;
    expect(serializeBotContent(document)).toBe(original);
  });

  it("empty follow up lists are omitted on export", () => {
    const document = parseBotContent(
      readFileSync(join(FIXTURES, "valid", "minimal.json"), "utf-8"),
    ).document as BotContentDocument;
    document.answers[0]!.next_option_ids = [];

    expect(serializeBotContent(document)).not.toContain("next_option_ids");
  });
});
