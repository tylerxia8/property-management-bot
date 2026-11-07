import { expect, test } from "@playwright/test";

test("prospect intake reaches human review and a local tour hold", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Subject").fill("prospect@example.test");
  await page.getByLabel("Password").fill("local-prospect-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
  await page.goto("/prequalification");
  await page.getByRole("button", { name: "Start intake" }).click();
  await expect(page.getByText("This is preliminary intake.")).toBeVisible();
  await page.getByLabel("Household income in cents").fill("100000");
  const saved = page.waitForResponse(
    (response) => response.url().includes("/intake") && response.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Save income" }).click();
  const saveResponse = await saved;
  expect(saveResponse.ok(), await saveResponse.text()).toBeTruthy();
  await expect(page.getByRole("listitem").filter({ hasText: "A missing period is not treated as zero." })).toBeVisible();
  await expect(page.getByText("Monthly income was not calculated and was not treated as zero.")).toBeVisible();
  await page.getByLabel("Income period").fill("monthly");
  await page.getByRole("button", { name: "Evaluate" }).click();
  await expect(page.getByRole("heading", { name: "Result HUMAN_REVIEW" })).toBeVisible();
  await expect(page.getByText("This is not a final denial or a housing decision.")).toBeVisible();
  await expect(page.getByText("Formal screening permitted: false")).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("/login");
  await page.getByLabel("Subject").fill("manager@example.test");
  await page.getByLabel("Password").fill("local-manager-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
  await page.goto("/reviews");
  await expect(page.getByRole("heading", { name: "Human review" })).toBeVisible();
  await expect(page.getByText("HUMAN_REVIEW")).toBeVisible();
  await page.getByRole("button", { name: "Record exception" }).click();
  await expect(page.getByText("No final housing decision was recorded.")).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await page.goto("/login");
  await page.getByLabel("Subject").fill("prospect@example.test");
  await page.getByLabel("Password").fill("local-prospect-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
  await page.goto("/prequalification");
  await page.getByRole("button", { name: "Start intake" }).click();
  await expect(page.getByText("This is preliminary intake.")).toBeVisible();
  await page.getByRole("button", { name: "Show tour slots" }).click();
  await page.getByRole("button", { name: "Request hold" }).first().click();
  await expect(page.getByText(/Hold HELD in America\/New_York/)).toBeVisible();
  await expect(page.getByText("External calendar event was not created.")).toBeVisible();
  await page.screenshot({ path: "test-results/prequalification-hold.png", fullPage: true });
});
