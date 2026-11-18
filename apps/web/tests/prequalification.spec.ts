import { expect, test } from "@playwright/test";

test("prospect intake reaches human review and a local tour hold", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("prospect@example.test");
  await page.getByLabel("Password").fill("local-prospect-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/maintenance(?:\/review)?(?:\?.*)?$/);
  await page.goto("/prequalification");
  await page.getByRole("button", { name: "Start intake" }).click();
  await expect(page.getByRole("heading", { name: "Plan a visit", exact: true })).toBeVisible();
  await page.getByLabel("Household income (USD)").fill("1000.00");
  const saved = page.waitForResponse(
    (response) => response.url().includes("/intake") && response.request().method() === "PATCH",
  );
  await page.getByRole("button", { name: "Save income" }).click();
  const saveResponse = await saved;
  expect(saveResponse.ok(), await saveResponse.text()).toBeTruthy();
  await expect(page.getByText("Choose an income period", { exact: true })).toBeVisible();
  await expect(page.getByText("$0.00 per month, based on your entry")).toHaveCount(0);
  await page.getByLabel("Income period").selectOption("monthly");
  await page.getByLabel("Desired move-in date").fill("2026-12-01");
  await page.getByLabel("Number of occupants").fill("1");
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByRole("heading", { name: "Ready for manager review" })).toBeVisible();
  await expect(page.getByText("This is a preliminary review, not a final housing decision.")).toBeVisible();
  await expect(page.getByText("Formal screening has not been started.")).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("Email").fill("manager@example.test");
  await page.getByLabel("Password").fill("local-manager-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/maintenance(?:\/review)?(?:\?.*)?$/);
  await page.goto("/reviews");
  await expect(page.getByRole("heading", { name: "Human review" })).toBeVisible();
  await expect(page.getByText("HUMAN_REVIEW")).toBeVisible();
  await page.getByRole("button", { name: "Record exception" }).click();
  await expect(page.getByText("Exception recorded. No final housing decision was recorded.")).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("Email").fill("prospect@example.test");
  await page.getByLabel("Password").fill("local-prospect-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/maintenance(?:\/review)?(?:\?.*)?$/);
  await page.goto("/prequalification");
  await page.getByRole("button", { name: "Start intake" }).click();
  await expect(page.getByRole("heading", { name: "Plan a visit", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Show tour slots" }).click();
  await page.getByRole("button", { name: "Request this time" }).first().click();
  await expect(page.getByText("Tour time held", { exact: true })).toBeVisible();
  await expect(page.getByText("This is a local hold. No calendar invitation has been sent.")).toBeVisible();
  await page.screenshot({ path: "test-results/prequalification-hold.png", fullPage: true });
});
