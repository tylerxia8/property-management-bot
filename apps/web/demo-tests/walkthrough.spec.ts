import { expect, test } from "@playwright/test";

test("the packaged sample supports all five guided role screens", async ({ page }) => {
  async function enter(button: string, path: string) {
    await page.goto("/");
    await expect(page.getByText("Fixture sample.")).toBeVisible();
    await page.getByRole("button", { name: button, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
  }

  await enter("1. Record rent", "/accounting");
  await expect(page.getByLabel("Unit")).not.toHaveValue("");
  await expect(page.getByLabel("Payer")).not.toHaveValue("");
  await page.getByRole("button", { name: "Record check", exact: true }).click();
  await expect(page.getByText(/is RECORDED/)).toBeVisible();
  await expect(page.getByText("Available cents: 0")).toBeVisible();

  await enter("2. Prequalify a prospect", "/prequalification");
  await page.getByRole("button", { name: "Start intake", exact: true }).click();
  await page.getByRole("button", { name: "Save income", exact: true }).click();
  await expect(page.getByText("Monthly income was not calculated and was not treated as zero.")).toBeVisible();
  await page.getByLabel("Income period", { exact: true }).fill("monthly");
  await page.getByRole("button", { name: "Evaluate", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Result HUMAN_REVIEW" })).toBeVisible();
  await expect(page.getByText("Formal screening permitted: false")).toBeVisible();

  await enter("4. Review as manager", "/reviews");
  await page.getByRole("button", { name: "Record exception", exact: true }).first().click();
  await expect(page.getByText("Exception recorded. No final housing decision was recorded.")).toBeVisible();
  await enter("2. Prequalify a prospect", "/prequalification");
  await page.getByRole("button", { name: "Start intake", exact: true }).click();
  await page.getByRole("button", { name: "Show tour slots", exact: true }).click();
  await page.getByRole("button", { name: "Request hold", exact: true }).last().click();
  await expect(page.getByText(/Hold HELD in America\/New_York/)).toBeVisible();

  await enter("3. Report a repair", "/maintenance");
  await page.getByLabel("What needs attention?").fill("The kitchen sink leaks");
  await page.getByRole("button", { name: "Report issue", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Ticket \d+/ })).toBeVisible();
  await expect(page.getByText(/room and fixture/i)).toBeVisible();
  await page.getByLabel("Follow-up", { exact: true }).fill("I smell gas");
  await page.getByRole("button", { name: "Send follow-up", exact: true }).click();
  await expect(page.getByText("Do not operate electrical switches.")).toBeVisible();

  await enter("5. View an owner statement", "/statements");
  await expect(page.getByRole("heading", { name: "Owner statements" })).toBeVisible();
  await expect(page.getByText("Unrestricted cents: 0")).toBeVisible();
  await expect(page.getByText(/Fixture demo snapshot/)).toBeVisible();
});
