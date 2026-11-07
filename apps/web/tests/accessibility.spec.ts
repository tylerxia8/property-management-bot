import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page, subject: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Subject").fill(subject);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
}

test("core screens have no serious or critical axe violations", async ({ page }) => {
  await page.goto("/login");
  await expectNoSeriousViolations(page, "login");
  await signIn(page, "manager@example.test", "local-manager-password");
  await expectNoSeriousViolations(page, "properties");
  await page.goto("/distributions");
  await expect(page.getByRole("heading", { name: "Distribution approval" })).toBeVisible();
  await expectNoSeriousViolations(page, "distributions");
  await page.goto("/statements");
  await expect(page.getByRole("heading", { name: "Owner statements" })).toBeVisible();
  await expectNoSeriousViolations(page, "statements");
});

async function expectNoSeriousViolations(page: import("@playwright/test").Page, name: string) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((item) => item.impact === "serious" || item.impact === "critical");
  expect(blocking, `${name}: ${blocking.map((item) => item.id).join(", ")}`).toEqual([]);
}
