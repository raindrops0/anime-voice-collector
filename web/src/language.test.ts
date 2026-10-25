import { expect, test } from "vitest";
import { startingStyles, translationStyles } from "./language";

const bilingual = { JP: "ja", CN: "zh", Sign: "zh" };

test("reading text aloud leaves the other language's style unticked", () => {
  expect(startingStyles(["JP", "CN"], bilingual, "ja", true)).toEqual(["JP"]);
  expect(startingStyles(["JP", "CN"], bilingual, "zh", true)).toEqual(["CN"]);
});

test("sound only keeps every picked style", () => {
  expect(startingStyles(["JP", "CN"], bilingual, "ja", false)).toEqual(["JP", "CN"]);
});

test("with no picked style in the language spoken, all stay ticked", () => {
  expect(startingStyles(["CN"], bilingual, "ja", true)).toEqual(["CN"]);
});

test("a style whose language is unknown stays ticked", () => {
  expect(startingStyles(["JP", "Top"], bilingual, "ja", true)).toEqual(["JP", "Top"]);
});

test("secondary subtitles show only the translation of a bilingual file", () => {
  expect(translationStyles(["JP", "CN"], bilingual, "ja")).toEqual(["CN"]);
  expect(translationStyles(["JP"], bilingual, "ja")).toEqual(["JP"]);
  expect(translationStyles(["CN", "Top"], bilingual, "ja")).toEqual(["CN", "Top"]);
});
