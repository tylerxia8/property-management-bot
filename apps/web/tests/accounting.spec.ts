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

test("accounting imports CSV safely and reports validation and evidence conflicts", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Subject").fill("accounting@example.test");
  await page.getByLabel("Password").fill("local-accounting-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
  const token = await page.evaluate(() => sessionStorage.getItem("grok_dev_token"));
  const bank = await page.request.post(`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/v1/bank-accounts`, {
    headers: { Authorization: `Bearer ${token}`, "Idempotency-Key": `csv-browser-bank-${crypto.randomUUID()}` },
    data: { display_name: "CSV browser fixture", masked_label: "****9001" },
  });
  expect(bank.status()).toBe(201);
  const bankId = (await bank.json()).id;
  await page.goto("/accounting");
  const upload = page.getByLabel("Bank transaction CSV");
  const submit = page.getByRole("button", { name: "Import transactions", exact: true });
  const csv = `bank_account_id,external_id,amount_cents,posted_on\n${bankId},browser-bank-event,10001,2026-11-07\n`;
  const file = { name: "bank.csv", mimeType: "text/csv", buffer: Buffer.from(csv) };
  await upload.setInputFiles(file);
  await submit.click();
  await expect(page.getByRole("status")).toContainText("Imported 1 new transactions; 0 exact repeats.");
  // The same selection retries its original request; a new selection deduplicates bank events.
  await submit.click();
  await expect(page.getByRole("status")).toContainText("Imported 1 new transactions; 0 exact repeats.");
  await upload.setInputFiles(file);
  await submit.click();
  await expect(page.getByRole("status")).toContainText("Imported 0 new transactions; 1 exact repeats.");
  await upload.setInputFiles({ ...file, buffer: Buffer.from(csv.replace(",10001,", ",20000,")) });
  await submit.click();
  await expect(page.getByRole("alert").filter({ hasText: "different amount or date" })).toBeVisible();
  await upload.setInputFiles({ ...file, buffer: Buffer.from(csv.replace(",10001,", ",10.01,")) });
  await submit.click();
  await expect(page.getByRole("alert").filter({ hasText: "Line 2." })).toBeVisible();
});
