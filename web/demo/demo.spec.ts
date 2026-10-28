import { expect, test, type Page } from "@playwright/test";
import { stamp } from "../src/format";

/* The README demo, about 40 seconds: name a group, label others "Not a target", watch the machine start guessing,
   fix a wrong guess, update the list, check a character, look at the history, export. Every key pressed shows in
   the corner, with a caption per shot that says the point of it.

   It needs avoc running on a workspace made from the 3-minute test episode (2:00 to 5:00 of episode 1 of
   Uma Musume: Pretty Derby, season 2), with no labels yet. The lines named below are picked for that episode:
   the group numbers and times would differ on any other. Everything is undone first, so it can run again; but the
   history panel then lists every earlier run, so for a clean recording stop avoc, move the labels/ folder out of the workspace
   and put its purpose.json back into a new labels/ folder (keep purpose.json), and start it again.

     npx playwright test -c demo/playwright.config.ts            (in web/; DEMO_LANG=zh for Chinese)

   The video lands in data/demo-out. Turned into a GIF under GitHub's 10 MB limit for attachments with:

     ffmpeg -ss 1 -i video.webm -vf "fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" demo.gif

   and into a sharper video, about 2 MB, for places that play one:

     ffmpeg -ss 1 -i video.webm -c:v libx264 -crf 24 -preset slow -pix_fmt yuv420p -movflags +faststart -an demo.mp4 */

const LANG = process.env.DEMO_LANG === "zh" ? "zh" : "en";
const say = (zh: string, en: string) => (LANG === "zh" ? zh : en);
const NAME = "Teio";

/* Group numbers on the Groups page, and line start times in seconds (after each clip's ends were tightened to its
   voice). Group 1 holds 8 of Teio's lines, so two more bring her to the 10 where guessing starts. The wrong guess is
   a fan calling out her name; the wrong line in her list is a student greeting at the school gate. */
const TEIO_GROUP = 1;
const OTHER_GROUPS = [3, 4];
const MORE_TEIO = [116.76, 171.02];
const WRONG_GUESS = 109.63;
const WRONG_IN_LIST = 144.7;

/* A caption near the bottom, above where the page's own messages pop up (with their buttons), and the last key pressed in the bottom right corner. */
const overlay = () => {
  const make = (id: string, css: string) => {
    const box = document.createElement("div");
    box.id = id;
    box.style.cssText =
      "position:fixed;z-index:99999;pointer-events:none;opacity:0;transition:opacity .25s;font:600 22px system-ui,sans-serif;" +
      css;
    document.body.append(box);
  };
  addEventListener("DOMContentLoaded", () => {
    make(
      "demo-caption",
      "left:50%;bottom:240px;transform:translateX(-50%);padding:10px 22px;border-radius:12px;background:rgba(20,20,20,.82);color:#fff;white-space:nowrap",
    );
    make(
      "demo-key",
      "right:28px;bottom:170px;min-width:48px;text-align:center;padding:8px 16px;border-radius:10px;background:#fff;color:#111;border:2px solid #111;box-shadow:0 3px 0 #111",
    );
  });
};

const caption = (page: Page, text: string) =>
  page.evaluate((text) => {
    const box = document.getElementById("demo-caption")!;
    box.textContent = text;
    box.style.opacity = text ? "1" : "0";
  }, text);

const press = async (
  page: Page,
  key: string,
  shown = key.length === 1 ? key.toUpperCase() : key,
) => {
  await page.evaluate((shown) => {
    const box = document.getElementById("demo-key")!;
    box.textContent = shown;
    box.style.opacity = "1";
    clearTimeout((window as unknown as { keyTimer: number }).keyTimer);
    (window as unknown as { keyTimer: number }).keyTimer = setTimeout(
      () => (box.style.opacity = "0"),
      1100,
    );
  }, shown);
  await page.keyboard.press(key);
};

test("README demo", async ({ page, request }) => {
  /* Collected to read text aloud, and starting with no labels. */
  await request.post("/api/purpose", { data: { purpose: "tts" } });
  while ((await (await request.get("/api/state")).json()).can_undo) await request.post("/api/undo");
  const clips: { id: string; start: number }[] = await (
    await request.get("/api/clips?episode=ep01")
  ).json();
  /* Click a line in the list, and make sure it is the one on the stage, so a miss never labels another line. */
  const pick = async (start: number) => {
    const clip = clips.find((c) => Math.abs(c.start - start) < 0.06);
    if (!clip) throw new Error(`no line starts at ${start} s`);
    /* The rows are the grids with the avatar column. The Characters view only draws the lines near the screen, so
       when the line is not drawn, scroll down from the top until it is. */
    const row = page
      .locator('main div[class*="grid-cols-[36px"]')
      .filter({ hasText: stamp(clip.start) })
      .first();
    if (!(await row.count())) {
      await page.locator("main").evaluate((m) => m.scrollTo({ top: 0 }));
      for (let i = 0; i < 100 && !(await row.count()); i++) {
        await page.locator("main").evaluate((m) => m.scrollBy({ top: 300 }));
        await page.waitForTimeout(50);
      }
    }
    await row.click();
    await expect(page).toHaveURL(new RegExp(`clip=${clip.id}`));
  };
  const group = (n: number) =>
    page.locator('[data-slot="card"]').filter({
      has: page.getByRole("heading", { name: new RegExp(`^(Group ${n}|第 ${n} 组) ·`) }),
    });
  const selectAll = (n: number) => group(n).getByRole("button", { name: /^(Select all|全选)$/ });

  await page.addInitScript((lang) => {
    localStorage.setItem("lang", lang);
    localStorage.setItem("guide-seen", "1");
  }, LANG);
  await page.addInitScript(overlay);
  await page.goto("/#view=groups&ep=ep01");
  await expect(selectAll(TEIO_GROUP)).toBeVisible();
  await page.waitForTimeout(800);

  /* 1. Groups: name a whole group. */
  await caption(
    page,
    say(
      "声音像的台词自动分成一组，整组一次标完",
      "Lines that sound alike come grouped: label a whole group at once",
    ),
  );
  await page.waitForTimeout(1800);
  await selectAll(TEIO_GROUP).click();
  await page.waitForTimeout(700);
  await press(page, "n");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await page.waitForTimeout(600);
  await page.keyboard.type(NAME, { delay: 110 });
  await page.waitForTimeout(500);
  await press(page, "Enter");
  await expect(dialog).toBeHidden();
  await page.waitForTimeout(900);

  /* 2. The groups of other people are "Not a target". */
  await caption(
    page,
    say(
      "只给想要的角色起名，其他人按 Q：「不是目标」",
      'Name only who you want; anyone else is Q, "Not a target"',
    ),
  );
  for (const n of OTHER_GROUPS) {
    await selectAll(n).click();
    await page.waitForTimeout(500);
    await press(page, "q");
    await page.waitForTimeout(900);
  }

  /* 3. Scenes: two more lines of her, and the machine starts guessing. */
  await press(page, "s");
  await caption(
    page,
    say("一个角色标满 10 句，机器就开始猜", "At 10 lines of a character, it starts guessing"),
  );
  for (const start of MORE_TEIO) {
    await pick(start);
    await page.waitForTimeout(1300);
    await press(page, "1");
    await page.waitForTimeout(900);
  }
  await page.waitForTimeout(1200);

  /* A wrong guess, fixed. */
  await caption(
    page,
    say("猜错了就改，它一秒内重新学", "Fix a wrong guess, and it retrains within a second"),
  );
  await pick(WRONG_GUESS);
  await page.waitForTimeout(1800);
  await press(page, "q");
  await page.waitForTimeout(1500);

  /* The new guesses show in place; the list itself waits for Update list. */
  await caption(
    page,
    say(
      "新的猜测就地显示，列表等你点「更新列表」才变",
      "New guesses show in place; the list moves only on Update list",
    ),
  );
  await page.waitForTimeout(2200);
  /* It shows in the message and in the bottom bar; the bottom bar's is always there, grayed when nothing waits. */
  const update = page.getByRole("button", { name: /^(Update list|更新列表)$/ }).last();
  if (await update.isEnabled()) await update.click();
  await page.waitForTimeout(1500);

  /* 4. Characters: what the machine gave her, least sure first. */
  await press(page, "o");
  await caption(
    page,
    say("再按角色检查，最没把握的排最前", "Then check each character, least sure first"),
  );
  await page.waitForTimeout(1800);
  await pick(WRONG_IN_LIST);
  await page.waitForTimeout(1500);
  await press(page, "q");
  await page.waitForTimeout(1300);

  /* Every step can be taken back, even an earlier one alone. */
  await caption(
    page,
    say(
      "每一步都能撤销，较早的某一步也能单独撤回",
      "Every step can be undone, even an earlier one alone",
    ),
  );
  await page.getByRole("button", { name: /^(History|操作历史)$/ }).click();
  await page.waitForTimeout(2600);
  await press(page, "Escape", "Esc");
  await page.waitForTimeout(600);

  /* 5. Export with the text of each line. */
  await press(page, "e");
  await caption(
    page,
    say(
      "导出纯人声和每句的原话，直接拿去训练",
      "Export voice-only clips with the words said, ready to train",
    ),
  );
  await page.waitForTimeout(1000);
  await page.getByRole("button", { name: /GPT-SoVITS/ }).click();
  await page.waitForTimeout(700);
  await page.getByRole("button", { name: /^(Export \d|导出 \d)/ }).click();
  await expect(page.getByRole("button", { name: /Open the folder|打开文件夹/ })).toBeVisible({
    timeout: 60_000,
  });
  await page.waitForTimeout(2500);
});
