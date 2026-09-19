import { test, expect } from "@playwright/test";
// Synthetic UI fixtures test workflow only, never model quality or benchmark truth.
const png = Buffer.from(
  "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",
  "base64",
);
test("offline upload → durable partial result → review → catalog → export", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(page.getByText("Local API connected")).toBeVisible();
  await page.getByRole("link", { name: "Analyze a game", exact: true }).click();
  await page
    .getByRole("button", { name: "Explicit demo", exact: true })
    .click();
  await page
    .getByLabel("Game or project name")
    .fill("Illustrative UI test data");
  await page.getByLabel("Release / edition").fill("Synthetic fixture");
  await page
    .getByRole("combobox", { name: "Platform", exact: true })
    .selectOption("mobile");
  await page.getByRole("checkbox").check();
  await page.getByLabel("Evidence files").setInputFiles({
    name: "synthetic.png",
    mimeType: "image/png",
    buffer: png,
  });
  await page
    .getByLabel("Source attribution")
    .fill("UI test fixture, no real-game claim");
  await page
    .getByLabel("Source description (optional)")
    .fill("A synthetic color patch; not gameplay.");
  await page
    .getByRole("button", { name: "Prepare analysis", exact: true })
    .click();
  await expect(page).toHaveURL(/\/runs\//);
  await expect(
    page.locator(".result-primary").getByText("partial", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Not classified", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByAltText("Uploaded evidence: synthetic.png"),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Not classified", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Review / edit", exact: true })
    .click();
  await page.getByLabel("Approved value").selectOption("puzzle");
  await page
    .getByLabel("Reason / source verification")
    .fill(
      "Illustrative workflow test only; this is not a human-reviewed game label.",
    );
  await page.getByRole("button", { name: "Save reviewed decision" }).click();
  await expect(
    page.getByRole("heading", { name: "Puzzle", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Human-approved catalog primary")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export JSON" }).click();
  expect((await download).suggestedFilename()).toMatch(/^gametagger-.*\.json$/);
  await page.getByRole("button", { name: "Prepare another run" }).click();
  await expect(
    page.getByRole("heading", { name: "Puzzle", exact: true }),
  ).toBeVisible();
  await page.goto("/catalog?dataset=demo");
  await expect(
    page.getByText("Illustrative UI test data", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "2 runs →" }).click();
  await expect(
    page.getByRole("heading", { name: "Puzzle", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/result-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/result-phone.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
test("experiments retain all cases, disclose errors, and show both comparison flows", async ({
  page,
}) => {
  await page.goto("/experiments");
  await expect(page.getByText("Inconclusive", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Effectiveness scorecard" }),
  ).toBeVisible();
  await page.getByLabel("Cohort").selectOption("mobile");
  await expect(page.getByText("0 matched cases")).toBeVisible();
  await page.getByRole("button", { name: "pipelines", exact: true }).click();
  await page.getByRole("button", { name: /Combined model/ }).click();
  await expect(
    page.getByText(/Actual deployed version is unverified/),
  ).toBeVisible();
  await page.getByLabel("Hold observations constant").check();
  await page
    .getByRole("button", { name: "Conventional classifier", exact: true })
    .click();
  await page.screenshot({
    path: "test-results/experiments-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "scorecard", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Filter saved outcome" })
    .selectOption("error");
  await expect(page.getByRole("button", { name: /Inspect/ })).toHaveCount(3);
  const inspect = page.getByRole("button", { name: /Inspect/ }).first();
  await inspect.click();
  await expect(
    page.getByRole("button", { name: "Close saved case" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close saved case" }).click();
  await page.goto("/roadmap");
  await expect(page.getByText(/Runtime unknown/)).toBeVisible();
  await page.goto("/taxonomy");
  await expect(
    page.getByRole("heading", { name: "One primary. Many dimensions." }),
  ).toBeVisible();
});
test("responsive overview, menu and empty/error states", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "Analyze a game", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/overview-desktop.png",
    fullPage: true,
  });
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/overview-${width}.png`,
      fullPage: true,
    });
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.getByRole("link", { name: "Taxonomy", exact: true }).click();
    await expect(page).toHaveURL(/\/taxonomy$/);
    await page.goto("/");
  }
  await page.goto("/runs/missing");
  await expect(page.getByRole("alert")).toContainText("Run not found");
});

test("a valid saved illustrative report is labelled and cannot compute effects", async ({
  page,
}) => {
  await page.goto("/experiments");
  await page
    .getByRole("combobox", { name: "Saved comparison" })
    .selectOption("illustrative-ui-test");
  await expect(page.getByRole("status")).toContainText(
    "Illustrative / UI test data",
  );
  await expect(page.getByRole("combobox", { name: "Cohort" })).toBeDisabled();
  await expect(page.getByText("0 matched cases")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Baseline" })).toContainText(
    "synthetic-interface-test",
  );
  await page
    .getByText("Comparison eligibility, denominators and provenance", {
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Illustrative/unavailable data cannot establish an effect", {
      exact: true,
    }),
  ).toBeVisible();
});

test("invalid uploads surface an error without a fabricated analysis", async ({
  page,
}) => {
  await page.goto("/analyze");
  await page
    .getByLabel("Game or project name")
    .fill("Illustrative invalid-file test");
  await page.getByRole("checkbox").check();
  await page
    .getByLabel("Evidence files")
    .setInputFiles({
      name: "invalid.png",
      mimeType: "image/png",
      buffer: Buffer.from("<html>not an image</html>"),
    });
  await page.getByRole("button", { name: "Prepare analysis" }).click();
  await expect(page.getByRole("alert")).toContainText("Invalid media");
  await expect(page).toHaveURL(/\/analyze$/);
  await expect(
    page.getByRole("button", { name: "Prepare analysis" }),
  ).toBeEnabled();
});
