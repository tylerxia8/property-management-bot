import { expect, test } from "@playwright/test";

test("accounting records a check that is not yet available", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Subject").fill("accounting@example.test");
  await page.getByLabel("Password").fill("local-accounting-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
  await page.goto("/accounting");
  await expect(page.getByRole("heading", { name: "Receipts" })).toBeVisible();
  await expect(page.getByText("does not submit money")).toBeVisible();
  await expect(page.getByLabel("Unit")).not.toHaveValue("");
  await expect(page.getByLabel("Payer")).not.toHaveValue("");
  await page.getByRole("button", { name: "Record check" }).click();
  await expect(page.getByText(/is RECORDED/)).toBeVisible();
  await expect(page.getByText("Available cents: 0")).toBeVisible();
  await page.screenshot({ path: "test-results/recorded-check.png", fullPage: true });
});
