import { test, expect } from "@playwright/test";

function nearFullViewport(
  inner: { x: number; y: number; width: number; height: number },
  vp: { width: number; height: number },
  ratio = 0.97,
) {
  expect(inner.width).toBeGreaterThanOrEqual(vp.width * ratio);
  expect(inner.height).toBeGreaterThanOrEqual(vp.height * ratio);
  expect(inner.x).toBeGreaterThanOrEqual(-1);
  expect(inner.y).toBeGreaterThanOrEqual(-1);
  expect(inner.x + inner.width).toBeLessThanOrEqual(vp.width + 2);
  expect(inner.y + inner.height).toBeLessThanOrEqual(vp.height + 2);
}

test.describe("deck layout (strict geometry)", () => {
  test.beforeEach(async ({ page }) => {
    // Fonts keep sockets warm; avoid networkidle flakes on static HTML.
    await page.goto("/index.html", { waitUntil: "load" });
  });

  test("deck root fills the viewport (no collapsed stage)", async ({ page }) => {
    const vp = page.viewportSize()!;
    const deckBox = await page.getByTestId("deck-root").boundingBox();

    expect(deckBox).toBeTruthy();
    nearFullViewport(deckBox!, vp, 0.96);
  });

  test("slide track matches deck height — regression for squashed carousel", async ({ page }) => {
    const deckBox = await page.getByTestId("deck-root").boundingBox();
    const trackBox = await page.getByTestId("slides-track").boundingBox();

    expect(deckBox).toBeTruthy();
    expect(trackBox).toBeTruthy();
    expect(trackBox!.height).toBeGreaterThanOrEqual(deckBox!.height * 0.98);
    expect(trackBox!.width).toBeGreaterThan(deckBox!.width * 3.5); // four panels across
  });

  test("slide 1 hero is not clipped horizontally and occupies upper/mid viewport", async ({
    page,
  }) => {
    const vp = page.viewportSize()!;
    const h1 = page.getByRole("heading", { level: 1, name: "AgentOS Research" });
    await expect(h1).toBeVisible({ timeout: 15_000 });

    const bb = await h1.boundingBox();
    expect(bb).toBeTruthy();

    expect(bb!.x).toBeGreaterThanOrEqual(16);
    expect(bb!.x + bb!.width).toBeLessThanOrEqual(vp.width - 16);

    const midY = bb!.y + bb!.height / 2;
    expect(midY).toBeLessThan(vp.height * 0.55);
  });

  test("keyboard navigation advances content (functional smoke)", async ({ page }) => {
    await page.keyboard.press("ArrowRight");

    await expect(page.getByRole("heading", { level: 2, name: /Hero/ })).toBeVisible({
      timeout: 15_000,
    });

    await page.keyboard.press("ArrowRight");

    await expect(page.getByRole("heading", { level: 2, name: /三块高光/ })).toBeVisible();

    await page.keyboard.press("Home");
    await expect(page.getByRole("heading", { level: 1, name: "AgentOS Research" })).toBeVisible();
  });

  test("End → last slide: track still full height; CTA not a 1px-tall strip", async ({ page }) => {
    const vp = page.viewportSize()!;
    await page.keyboard.press("End");

    const deckBox = await page.getByTestId("deck-root").boundingBox();
    const trackBox = await page.getByTestId("slides-track").boundingBox();
    const ctaBox = await page.getByTestId("cta-panel").boundingBox();

    expect(deckBox).toBeTruthy();
    expect(trackBox).toBeTruthy();
    expect(ctaBox).toBeTruthy();

    expect(trackBox!.height).toBeGreaterThanOrEqual(deckBox!.height * 0.97);
    expect(ctaBox!.height).toBeGreaterThan(Math.min(220, vp.height * 0.28));
  });
});
