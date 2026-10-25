import { describe, expect, test } from "vitest";
import { batchRows, namePrefix, type Pairs } from "./batch";

const pairs: Pairs = {
  episodes: [
    { number: 1, videos: ["D:/s2/S02E01 [x265].mkv"], subtitles: ["D:/sub/- 01.ass"] },
    {
      number: 2,
      videos: ["D:/s2/S02E02 [AV1].mkv", "D:/s2/S02E02 [x265].mkv"],
      subtitles: ["D:/sub/- 02.ass"],
    },
    { number: 3, videos: ["D:/s2/S02E03 [x265].mkv"], subtitles: [] },
  ],
  no_number: [],
};
const none = { videos: "", subtitles: "", display_subtitles: "" };

describe("batchRows", () => {
  test("names each episode and says what stops it", () => {
    const rows = batchRows(pairs, "usagi-s2-ep", none, new Set(["usagi-s2-ep01"]));
    expect(rows.map((r) => r.name)).toEqual(["usagi-s2-ep01", "usagi-s2-ep02", "usagi-s2-ep03"]);
    expect(rows.map((r) => r.problem)).toEqual([
      "已经有这一集",
      "有 2 个视频，用上面的筛选留下一个",
      "没有字幕",
    ]);
  });

  test("a filter keeps one of two encodes", () => {
    const rows = batchRows(pairs, "ep", { ...none, videos: "X265" }, new Set());
    expect(rows[1].video).toBe("D:/s2/S02E02 [x265].mkv");
    expect(rows[1].problem).toBeNull();
  });

  test("refuses a name the folder rules do not allow", () => {
    expect(batchRows(pairs, "my show ", none, new Set())[0].problem).toMatch(/只能用英文字母/);
  });
});

test("namePrefix follows the latest episode name", () => {
  expect(namePrefix(["ep01", "usagi-s3-ep12"])).toBe("usagi-s3-ep");
  expect(namePrefix(["final"])).toBe("ep");
  expect(namePrefix([])).toBe("ep");
});
