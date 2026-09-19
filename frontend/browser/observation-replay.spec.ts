import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

test("synthetic video → exact-window replay → seek → reload → export", async ({ page }) => {
  const folder = mkdtempSync(join(tmpdir(), "gametagger-video-test-"));
  const video = join(folder, "synthetic.mp4");
  try {
    execFileSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=12",
      "-t", "4", "-pix_fmt", "yuv420p", "-c:v", "libx264", video], { timeout: 15000 });
    await page.goto("/analyze");
    await page.getByRole("button", { name: "Explicit demo", exact: true }).click();
    await page.getByLabel("Game or project name").fill("Illustrative ordered-video replay");
    await page.getByRole("checkbox").check();
    await page.getByLabel("Evidence files").setInputFiles(video);
    await page.getByRole("button", { name: "Prepare analysis", exact: true }).click();
    await expect(page).toHaveURL(/\/runs\//);
    await expect(page.getByRole("link", { name: "Download exact window manifest" })).toBeVisible();
    const parentUrl = page.url();
    const rid = parentUrl.split("/").pop();
    const manifest = await (await page.request.get(`/api/runs/${rid}/observation-request`)).json();
    const bundle = JSON.parse(execFileSync("../.venv/bin/python", ["browser/fixtures/ordered_replay.py"],
      { input: JSON.stringify(manifest), encoding: "utf8", timeout: 10000 }));
    await page.getByLabel("Saved observation JSON").setInputFiles({ name: "wrong-replay.json", mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify({ ...bundle, input_sha256: "f".repeat(64) })) });
    await page.getByRole("button", { name: "Validate and save replay" }).click();
    await expect(page.getByRole("alert")).toContainText("Replay rejected");
    await expect(page).toHaveURL(parentUrl);
    await page.getByLabel("Saved observation JSON").setInputFiles({ name: "illustrative-replay.json", mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(bundle)) });
    await page.getByRole("button", { name: "Validate and save replay" }).click();
    await expect(page).not.toHaveURL(parentUrl);
    await expect(page.getByText("Saved observation replay · unverified", { exact: true })).toBeVisible();
    await expect(page.getByText("Colored bars fill the sampled image.", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Not classified", exact: true })).toBeVisible();
    await expect(page.getByLabel("Window execution status")).toContainText("not evaluated");
    await expect(page.getByLabel("Window execution status")).toContainText("error");
    await page.getByRole("button", { name: "View source at 0.00s" }).click();
    await expect(page.locator("video")).toHaveJSProperty("currentTime", 0);
    await page.reload();
    await expect(page.getByText("Colored bars fill the sampled image.", { exact: true })).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440);
    await page.screenshot({ path: "../docs/screenshots/video-replay-desktop.png", fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: "../docs/screenshots/video-replay-phone.png", fullPage: true });
    const saved = page.waitForEvent("download");
    await page.getByRole("link", { name: "Export JSON", exact: true }).click();
    expect((await saved).suggestedFilename()).toMatch(/gametagger-.*\.json/);
    await page.getByRole("link", { name: "Open original preparation run" }).click();
    await expect(page).toHaveURL(parentUrl);
    await expect(page.getByText("Colored bars fill the sampled image.", { exact: true })).toHaveCount(0);
  } finally { rmSync(folder, { recursive: true, force: true }); }
});
