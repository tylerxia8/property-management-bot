import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import AxeBuilder from "@axe-core/playwright";
const photo = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAN0lEQVR4nO3RMQ0AMAzEQLf8OacQ3CWbD8BHcg4Mm+7qOh340A9UiVSJVIlUiVSJVIlUiVSJMA+hxgE/8m7SpQAAAABJRU5ErkJggg==",
  "base64",
);
test("maintenance photo and manager updates persist for the resident", async ({
  page,
}) => {
  const description = `Bathroom tap drips / browser ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: /I’m the tenant/ }).click();
  await page.getByLabel("Describe the problem", { exact: true }).fill(description);
  await page.getByLabel("Photos or videos", { exact: false }).setInputFiles({
    name: "fixture-tap.png", mimeType: "image/png", buffer: photo,
  });
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  await expect(page.getByRole("heading", { name: description, exact: true })).toBeVisible();
  const residentUrl = page.url();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Bathroom sink, under the tap. Please ask the property manager to help.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("Bathroom sink, under the tap.");
  await page.reload();
  await page.getByText("Request photos & videos", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Download photo", exact: true })).toBeVisible();
  await expectAccessible();
  await page.getByRole("button", { name: "Manager view", exact: true }).click();
  await expect(page).toHaveURL(/\/maintenance\/review\?ticket=/);
  await expect(page.getByText(description, { exact: true }).first()).toBeVisible();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Plumber is inspecting the tap. No entry without coordination.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("Plumber is inspecting the tap. No entry without coordination.");
  await expectAccessible();
  await page.getByRole("button", { name: "Tenant view", exact: true }).click();
  await expect(page).toHaveURL(residentUrl);
  await expect(page.getByRole("log")).toContainText("Plumber is inspecting the tap. No entry without coordination.");
  await page.getByText("Request photos & videos", { exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download photo", exact: true }).click();
  expect((await downloaded).suggestedFilename()).toMatch(/^repair-[a-f0-9-]+\.jpg$/);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expectAccessible();
  await page.screenshot({ path: "test-results/maintenance-complete-mobile.png", fullPage: true });
  async function expectAccessible() {
    const result = await new AxeBuilder({ page }).analyze();
    expect(
      result.violations
        .filter((v) => ["serious", "critical"].includes(v.impact || ""))
        .map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => ({
            target: n.target,
            message: n.failureSummary,
          })),
        })),
    ).toEqual([]);
  }
});

test("lost report response retries safely, rejected photos keep the request, and emergencies stop questions", async ({ page }) => {
  const description = `Kitchen sink leaks / retry ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: /I’m the tenant/ }).click();
  await page.getByLabel("Describe the problem", { exact: true }).fill(description);
  let loseResponse = true;
  await page.route("**/v1/maintenance-tickets", async route => {
    if (route.request().method() === "POST" && loseResponse) {
      loseResponse = false;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  await expect(page.getByRole("heading", { name: description, exact: true })).toBeVisible();
  await expect(page.getByRole("button").filter({ hasText: description })).toHaveCount(1);
  await page.getByText("Attach photos or videos", { exact: true }).click();
  await page.getByLabel("Photos or videos", { exact: true }).setInputFiles({ name: "bad.png", mimeType: "image/png", buffer: Buffer.from("This is not an image") });
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Please look at this photo.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("attachment");
  await expect(page.getByRole("heading", { name: description, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("I smell gas");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("Piedmont Natural Gas at 800-752-7504");
  await expect(page.getByText("Emergency request", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("log")).toContainText("Piedmont Natural Gas at 800-752-7504");
  const text = (await page.locator("main").innerText()).toLowerCase();
  expect(text).not.toContain("911 was called");
  expect(text).not.toContain("we called");
  await page.setViewportSize({ width: 320, height: 750 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const result = await new AxeBuilder({ page }).analyze();
  expect(result.violations.filter(v => ["serious", "critical"].includes(v.impact || "")).map(v => v.id)).toEqual([]);
});

test("tenant video upload is downloadable after refresh and visible to the manager", async ({ page }) => {
  await page.waitForTimeout(60_000);
  const description = `Tap noise / video ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: /I’m the tenant/ }).click();
  await page.getByLabel("Describe the problem", { exact: true }).fill(description);
  const uploadInput = page.getByLabel("Photos or videos", { exact: false });
  await expect(uploadInput).toBeEnabled();
  await uploadInput.setInputFiles({ name: "repair.mov", mimeType: "video/quicktime", buffer: readFileSync(join(__dirname, "fixtures", "repair.mov")) });
  const completed = page.waitForResponse(response => response.request().method() === "POST" && /\/v1\/media\/[^/]+\/complete$/.test(response.url()));
  const created = page.waitForResponse(response => response.request().method() === "POST" && /\/v1\/maintenance-tickets$/.test(response.url()));
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  const createdResponse = await created;
  expect(createdResponse.ok(), await createdResponse.text()).toBeTruthy();
  const completedResponse = await completed;
  expect(completedResponse.ok(), await completedResponse.text()).toBeTruthy();
  expect((await completedResponse.json()).status).toBe("READY");
  await expect(page.getByRole("heading", { name: description, exact: true })).toBeVisible();
  await page.getByText("Request photos & videos", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Download video", exact: true })).toBeVisible();
  await page.reload();
  await page.getByText("Request photos & videos", { exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download video", exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^repair-[a-f0-9-]+\.mp4$/);
  expect(await file.failure()).toBeNull();
  await page.getByRole("button", { name: "Manager view", exact: true }).click();
  await expect(page).toHaveURL(/\/maintenance\/review\?ticket=/);
  await page.getByText("Request photos & videos", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Download video", exact: true })).toBeVisible();
});
