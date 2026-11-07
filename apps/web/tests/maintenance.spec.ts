import { expect, test } from "@playwright/test";

test("tenant report keeps a ticket and does not claim responders were contacted", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Subject").fill("tenant@example.test");
  await page.getByLabel("Password").fill("local-tenant-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
  await page.goto("/maintenance");
  await expect(page.getByRole("heading", { name: "Maintenance" })).toBeVisible();
  await expect(page.getByText("does not contact emergency services")).toBeVisible();
  await page.getByLabel("What needs attention?").fill("The kitchen sink leaks");
  await page.getByRole("button", { name: "Report issue" }).click();
  await expect(page.getByRole("heading", { name: /Ticket \d+/ })).toBeVisible();
  await expect(page.getByText(/room and fixture/i)).toBeVisible();
  await page.getByLabel("Follow-up").fill("I smell gas");
  await page.getByRole("button", { name: "Send follow-up" }).click();
  await expect(page.getByText("If there is immediate danger, leave the area if safe and call 911 or the appropriate emergency service.")).toBeVisible();
  await expect(page.getByText("Do not operate electrical switches.")).toBeVisible();
  const text = (await page.locator("main").innerText()).toLowerCase();
  expect(text).not.toContain("were contacted");
  expect(text).not.toContain("911 was called");
  expect(text).not.toContain("we called");
  await page.screenshot({ path: "test-results/maintenance-intake.png", fullPage: true });
});
