import { expect, test } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page, subject: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Subject").fill(subject);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/properties$/);
}

test("local shell discloses dev auth and enforces role capabilities", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("It is not production OIDC or MFA.")).toBeVisible();
  await page.getByLabel("Subject").fill("accounting@example.test");
  await page.getByLabel("Password").fill("wrong-password-value");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Subject or password is incorrect.")).toBeVisible();

  await signIn(page, "accounting@example.test", "local-accounting-password");
  await expect(page.getByText("Elm Street House")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create property" })).toHaveCount(0);
  await expect(page.getByText("properties.create")).toHaveCount(0);
  await expect(page.getByText("Signed in as Casey Accounting")).toContainText("not production OIDC or MFA");
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "tenant@example.test", "local-tenant-password");
  await expect(page.getByText("You do not have access to this action.")).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "admin@example.test", "local-admin-password");
  await page.getByLabel("Name").fill("Canal House");
  await page.getByLabel("Address").fill("20 Canal Street");
  await page.getByLabel("City").fill("Durham");
  await page.getByLabel("Region").fill("NC");
  await page.getByLabel("Postal code").fill("27701");
  await page.getByLabel("Country").fill("US");
  await page.getByLabel("Timezone").fill("America/New_York");
  await page.getByRole("button", { name: "Create property" }).click();
  await page.getByRole("link", { name: "Canal House" }).click();
  await page.getByLabel("Unit label").fill("Main");
  await page.getByRole("button", { name: "Add unit" }).click();
  await expect(page.getByText("Main")).toBeVisible();
  await page.goto("/properties");
  await page.getByRole("button", { name: "Sign out" }).click();

  await signIn(page, "manager@example.test", "local-manager-password");
  await page.getByRole("link", { name: "Canal House" }).click();
  await expect(page.getByLabel("Name")).toHaveValue("Canal House");
  await page.getByLabel("Name").fill("Canal House North");
  const saved = page.waitForResponse(response => response.request().method() === "PATCH" && response.url().includes("/v1/properties/"));
  await page.getByRole("button", { name: "Save changes" }).click();
  const saveResponse = await saved;
  expect(saveResponse.ok(), await saveResponse.text()).toBeTruthy();
  await expect(page.getByRole("heading", { name: "Canal House North" })).toBeVisible();
  await expect(page.getByText("Main")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add unit" })).toHaveCount(0);
  await page.screenshot({ path: "test-results/manager-property.png", fullPage: true });
});
