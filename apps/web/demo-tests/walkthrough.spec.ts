import { expect, test } from "@playwright/test";

test("the packaged sample supports all five guided role screens", async ({ page }) => {
  async function enter(role: string, path: string) {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Maintenance", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /I’m the tenant/ })).toBeVisible();
    await page.evaluate(async role => {
      const response = await fetch("/v1/demo/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }), signal: AbortSignal.timeout(15000) });
      if (!response.ok) throw new Error("The demo role could not be opened.");
      sessionStorage.setItem("grok_dev_token", (await response.json()).token);
    }, role);
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`${path}$`));
  }

  await enter("accounting_staff", "/accounting");
  await expect(page.getByLabel("Unit")).not.toHaveValue("");
  await expect(page.getByLabel("Payer")).not.toHaveValue("");
  await page.getByRole("button", { name: "Record check", exact: true }).click();
  await expect(page.getByText(/is RECORDED/)).toBeVisible();
  await expect(page.getByText("Available cents: 0")).toBeVisible();

  await enter("prospect", "/prequalification");
  await page.getByRole("button", { name: "Start intake", exact: true }).click();
  await page.getByLabel("Household income (USD)").fill("1000.00");
  await page.getByRole("button", { name: "Save income", exact: true }).click();
  await expect(page.getByText("Choose an income period")).toBeVisible();
  await page.getByRole("combobox", { name: "Income period", exact: true }).selectOption("monthly");
  await page.getByLabel("Desired move-in date").fill("2026-12-01");
  await page.getByLabel("Number of occupants").fill("1");
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.getByRole("heading", { name: "Ready for manager review" })).toBeVisible();
  await expect(page.getByText("Formal screening has not been started.")).toBeVisible();

  await enter("property_manager", "/reviews");
  await page.getByRole("button", { name: "Record exception", exact: true }).first().click();
  await expect(page.getByText("Exception recorded. No final housing decision was recorded.")).toBeVisible();
  await enter("prospect", "/prequalification");
  await page.getByRole("button", { name: "Start intake", exact: true }).click();
  await page.getByRole("button", { name: "Show tour slots", exact: true }).click();
  await page.getByRole("button", { name: "Request this time", exact: true }).last().click();
  await expect(page.getByText("Tour time held", { exact: true })).toBeVisible();

  await enter("tenant", "/maintenance");
  await page.getByLabel("Describe the problem").fill("The kitchen sink leaks");
  await page.getByRole("button", { name: "Send request", exact: true }).click();
  await expect(page.getByRole("heading", { name: "The kitchen sink leaks", exact: true })).toBeVisible();
  await expect(page.getByRole("log").getByText(/sink/i)).toBeVisible();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("I smell gas");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("log").getByText(/Piedmont Natural Gas at 800-752-7504/)).toBeVisible();

  await enter("owner", "/statements");
  await expect(page.getByRole("heading", { name: "Owner statements" })).toBeVisible();
  await expect(page.getByText("Unrestricted cents: 0")).toBeVisible();
  await expect(page.getByText(/Fixture demo snapshot/)).toBeVisible();
});
