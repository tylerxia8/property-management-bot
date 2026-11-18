import { expect, test } from "@playwright/test";

test("tenant report keeps a ticket and does not claim responders were contacted", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("tenant@example.test");
  await page.getByLabel("Password").fill("local-tenant-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/maintenance(?:\?.*)?$/);
  await page.goto("/maintenance");
  await expect(page.getByRole("heading", { name: "Repairs" })).toBeVisible();
  await expect(page.getByText("Immediate danger? Get somewhere safe and call emergency services.")).toBeVisible();
  await page.getByLabel("Describe the problem").fill("The kitchen sink leaks");
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByRole("heading", { name: "The kitchen sink leaks", exact: true })).toBeVisible();
  await expect(page.getByRole("log")).toContainText("sink");
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("I smell gas");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("log")).toContainText("Piedmont Natural Gas at 800-752-7504");
  await expect(page.getByRole("log")).toContainText("Do not operate electrical switches.");
  const text = (await page.locator("main").innerText()).toLowerCase();
  expect(text).not.toContain("were contacted");
  expect(text).not.toContain("911 was called");
  expect(text).not.toContain("we called");
  await page.screenshot({ path: "test-results/maintenance-intake.png", fullPage: true });
});
