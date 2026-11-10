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
  await page
    .getByRole("button", { name: "3. Report a repair", exact: true })
    .click();
  await expect(page.getByLabel("Your home")).not.toHaveValue("");
  await page
    .getByLabel("What needs attention?", { exact: true })
    .fill(description);
  await page
    .getByLabel("When did it start?", { exact: true })
    .fill("Yesterday; each time the tap runs");
  await page
    .getByLabel("Contact preferences", { exact: true })
    .fill("Email, afternoons");
  await page.getByRole("button", { name: "Report issue", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Ticket \d+/ })).toBeVisible();
  const residentUrl = page.url();
  await page
    .getByRole("combobox", { name: "What is this about?", exact: true })
    .selectOption("exact_location");
  await page
    .getByLabel("Follow-up", { exact: true })
    .fill("Bathroom sink, under the tap");
  await page
    .getByRole("button", { name: "Send follow-up", exact: true })
    .click();
  await expect(
    page.getByText("Follow-up saved.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Which room and fixture/)).toHaveCount(0);
  await page.getByLabel("Attach a photo", { exact: false }).setInputFiles({
    name: "fixture-tap.png",
    mimeType: "image/png",
    buffer: photo,
  });
  await expect(
    page.getByRole("button", { name: "Download photo 1", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Finish intake for manager review",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Intake finished.", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Download photo 1", exact: true }),
  ).toBeVisible();
  await expectAccessible();
  await page
    .getByRole("button", { name: "Open manager queue", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Maintenance queue", exact: true }),
  ).toBeVisible();
  await page.getByRole("button").filter({ hasText: description }).click();
  await page
    .getByRole("combobox", { name: "Status", exact: true })
    .selectOption("IN_PROGRESS");
  await page
    .getByLabel("Update note", { exact: true })
    .fill("Plumber is inspecting the tap. No entry without coordination.");
  await page
    .getByRole("button", { name: "Save status update", exact: true })
    .click();
  await expect(
    page.getByText("Status updated.", { exact: false }),
  ).toBeVisible();
  await expectAccessible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Maintenance", exact: true })
    .click();
  await page.goto(residentUrl);
  await expect(
    page
      .locator(".request-history")
      .getByText(
        "Plumber is inspecting the tap. No entry without coordination.",
        { exact: true },
      ),
  ).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download photo 1", exact: true })
    .click();
  expect((await downloaded).suggestedFilename()).toMatch(
    /^maintenance-photo-.*\.jpg$/,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await expectAccessible();
  await page.screenshot({
    path: "test-results/maintenance-complete-mobile.png",
    fullPage: true,
  });
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

test("lost report response retries safely, rejected photos keep the request, and emergencies stop questions", async ({
  page,
}) => {
  const description = `Kitchen sink leaks / retry ${Date.now()}`;
  await page.goto("/");
  await page
    .getByRole("button", { name: "3. Report a repair", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "What needs attention?", exact: true })
    .fill(description);
  let loseResponse = true;
  await page.route("**/v1/maintenance-tickets", async (route) => {
    if (route.request().method() === "POST" && loseResponse) {
      loseResponse = false;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await page.getByRole("button", { name: "Report issue", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Connection lost.",
  );
  await expect(
    page.getByRole("textbox", { name: "What needs attention?", exact: true }),
  ).toHaveValue(description);
  await page.getByRole("button", { name: "Report issue", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Ticket \d+/ })).toBeVisible();
  await expect(
    page
      .locator(".maintenance-request-list")
      .getByRole("button")
      .filter({ hasText: description }),
  ).toHaveCount(1);
  await page
    .getByLabel("Attach a photo", { exact: false })
    .setInputFiles({
      name: "bad.png",
      mimeType: "image/png",
      buffer: Buffer.from("This is not an image"),
    });
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "This attachment could not be accepted.",
  );
  await expect(page.getByRole("heading", { name: /Ticket \d+/ })).toBeVisible();
  await page
    .getByRole("button", { name: "Continue without photos or videos", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Your request stays open without photos or videos.",
  );
  await page.getByLabel("Follow-up", { exact: true }).fill("I smell gas");
  await page
    .getByRole("button", { name: "Send follow-up", exact: true })
    .click();
  await expect(
    page.getByText("Do not operate electrical switches.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "A little more detail", exact: true }),
  ).toHaveCount(0);
  await page.reload();
  await expect(page.locator(".emergency-panel")).toContainText(
    "No emergency call or contractor dispatch has been made.",
  );
  await page.setViewportSize({ width: 320, height: 750 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const result = await new AxeBuilder({ page }).analyze();
  expect(
    result.violations
      .filter((v) => ["serious", "critical"].includes(v.impact || ""))
      .map((v) => v.id),
  ).toEqual([]);
});


test("tenant video upload is downloadable after refresh and visible to the manager", async ({ page }) => {
  const description = `Tap noise / video ${Date.now()}`;
  await page.goto("/");
  await page.getByRole("button", { name: "3. Report a repair", exact: true }).click();
  await page.getByRole("textbox", { name: "What needs attention?", exact: true }).fill(description);
  await page.getByRole("button", { name: "Report issue", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Ticket \d+/ })).toBeVisible();
  const uploadInput = page.getByLabel("Attach a photo or video", { exact: false });
  await expect(uploadInput).toBeEnabled();
  await uploadInput.setInputFiles({
    name: "repair.mov", mimeType: "video/quicktime",
    buffer: readFileSync(join(__dirname, "fixtures", "repair.mov")),
  });
  await expect(page.getByRole("button", { name: "Download video 1", exact: true })).toBeVisible();
  await page.reload();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download video 1", exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^maintenance-video-.*\.mp4$/);
  expect(await file.failure()).toBeNull();
  await page.getByRole("button", { name: "Open manager queue", exact: true }).click();
  await page.getByRole("button").filter({ hasText: description }).click();
  await expect(page.getByRole("button", { name: "Download video 1", exact: true })).toBeVisible();
});
