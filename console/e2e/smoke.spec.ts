// The checklist's smoke test: seed one golden, open the queue, open the case, amend the window by
// -10 min, submit, see COMMITTED. Runs against `qgate-eval serve` (api) + `vite preview` (console).
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

// SHOTS=1 also writes the README's two gate screenshots.
const shot = (page: import("@playwright/test").Page, name: string) =>
  process.env.SHOTS
    ? page.screenshot({ path: `../docs/img/${name}.png`, fullPage: true })
    : Promise.resolve();

const tokens = JSON.parse(readFileSync("e2e/.tokens.json", "utf8")) as {
  viewer: string;
  approver: string;
};

async function signIn(page: import("@playwright/test").Page, token: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Token" }).click();
  await page.getByLabel("Access token").fill(token);
  await page.getByRole("button", { name: "Use token" }).click();
}

test("viewer sees the queue but cannot decide", async ({ page }) => {
  await signIn(page, tokens.viewer);
  await expect(page.getByRole("heading", { name: "Queue" })).toBeVisible();
  const row = page.getByRole("row", { name: /ST-19/ });
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByRole("heading", { name: /ST-19/ })).toBeVisible();
  const decide = page.getByRole("link", { name: "Decide" });
  await expect(decide).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByText("Your token can view, not decide")).toBeVisible();
});

test("approver amends the window by ten minutes and the hold is committed", async ({
  page,
}) => {
  await signIn(page, tokens.approver);
  await page.getByRole("row", { name: /ST-19/ }).click();
  const before = Number(await page.getByTestId("vin-count").innerText());
  await shot(page, "gate-case");
  await page.getByRole("link", { name: "Decide" }).click();

  await page.getByLabel("Amend").check();
  const start = page.getByLabel("Window start");
  const value = await start.inputValue(); // yyyy-MM-ddTHH:mm in local time
  const shifted = new Date(new Date(value).getTime() + 10 * 60_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  await start.fill(
    `${shifted.getFullYear()}-${pad(shifted.getMonth() + 1)}-${pad(
      shifted.getDate(),
    )}T` + `${pad(shifted.getHours())}:${pad(shifted.getMinutes())}`,
  );
  await expect
    .poll(async () =>
      Number(await page.getByTestId("preview-count").innerText()),
    )
    .toBeLessThan(before);
  await page.getByLabel("Reason").fill("tool changed ten minutes in");
  await shot(page, "gate-decide");
  await page.getByRole("button", { name: "Submit decision" }).click();

  await expect(page.getByText("Committed")).toBeVisible({ timeout: 30_000 });
  const after = Number(await page.getByTestId("vin-count").innerText());
  expect(after).toBeLessThan(before);

  await page.getByRole("link", { name: "Audit" }).click();
  await expect(page.getByRole("heading", { name: "Audit" })).toBeVisible();
  await expect(page.getByTestId("agreement-rate")).toHaveText("0%"); // one decision, amended
  await expect(page.getByTestId("narrowed")).toHaveText("1");
});
