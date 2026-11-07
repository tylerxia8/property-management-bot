import { expect, test } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page, subject: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Subject").fill(subject);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
}

test("manager export does not settle and owner sees only their statement", async ({ page }) => {
  await signIn(page, "accounting@example.test", "local-accounting-password");
  await page.goto("/distributions");
  await expect(page.getByRole("heading", { name: "Distribution approval" })).toBeVisible();
  await expect(page.getByText("Bank submission is disabled")).toBeVisible();
  await expect(page.getByLabel("Payee")).not.toHaveValue("");
  await page.getByRole("button", { name: "Save masked destination" }).click();
  await expect(page.getByText(/Destination version/)).toBeVisible();
  await page.getByRole("button", { name: "Draft distribution" }).click();
  await expect(page.getByText("Item OWNER 25000 cents DRAFT")).toBeVisible();
  await page.getByRole("button", { name: "Validate reservations" }).click();
  await expect(page.getByRole("heading", { name: "Batch VALIDATED" })).toBeVisible();
  const batchUrl = page.url();

  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "manager@example.test", "local-manager-password");
  await page.goto(batchUrl);
  await expect(page.getByRole("heading", { name: "Batch VALIDATED" })).toBeVisible();
  await page.getByLabel("Step-up subject").fill("manager@example.test");
  await page.getByLabel("Step-up password").fill("local-manager-password");
  await page.getByRole("button", { name: "Record step-up" }).click();
  await expect(page.getByText("Dev/test step-up recorded. This is not production MFA.")).toBeVisible();
  await expect(page.getByText("This form cannot set it.")).toBeVisible();
  await page.getByLabel("Approval reason").fill("Browser review of the fixture snapshot.");
  const approval = page.waitForResponse(response =>
    response.request().method() === "POST" && /\/distribution-batches\/[^/]+\/approve$/.test(response.url()));
  await page.getByRole("button", { name: "Approve snapshot" }).click();
  const approved = await approval;
  expect(approved.ok(), await approved.text()).toBeTruthy();
  await expect(page.getByRole("heading", { name: "Batch APPROVED" })).toBeVisible();
  await page.getByRole("button", { name: "Export instructions" }).click();
  await expect(page.getByText("Export settled: false")).toBeVisible();
  await expect(page.getByText("Export submitted: false")).toBeVisible();
  await expect(page.getByText("First download")).toBeVisible();
  await page.getByRole("button", { name: "Export instructions" }).click();
  await expect(page.getByText("Duplicate download")).toBeVisible();
  await expect(page.getByText("Export settled: false")).toBeVisible();
  await page.getByRole("button", { name: "Submit to provider" }).click();
  await expect(page.getByText("KILL_SWITCH")).toBeVisible();
  await page.screenshot({ path: "test-results/distribution-export.png", fullPage: true });

  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "owner@example.test", "local-owner-password");
  await page.goto("/statements");
  await expect(page.getByRole("heading", { name: "Owner statements" })).toBeVisible();
  await expect(page.getByText("Unrestricted cents: 25000")).toBeVisible();
  await expect(page.getByText("Browser fixture snapshot. Not a bank statement.")).toBeVisible();
  await page.screenshot({ path: "test-results/owner-statement.png", fullPage: true });

  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "other-owner@example.test", "local-owner-password");
  await page.goto("/statements");
  await expect(page.getByText("No statement is visible for this sign-in.")).toBeVisible();
  await expect(page.getByText("Unrestricted cents: 25000")).toHaveCount(0);
});
