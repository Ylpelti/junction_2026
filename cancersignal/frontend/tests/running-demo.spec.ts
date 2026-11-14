import { test, expect } from "@playwright/test";
import { isCanonicalPatient } from "../lib/demo-dataset";
import type { ApiPatient, ApiReviewRequest } from "../lib/mappers";

test.skip(!process.env.E2E_RUNNING_URL, "Explicit read-only verification of an already running demo");
test("running frontend displays only canonical API patients and persisted queue", async ({ page, request }) => {
  const api = process.env.E2E_API_URL ?? "http://localhost:8000";
  const patients: ApiPatient[] = await (await request.get(`${api}/api/v1/patients?limit=200`)).json();
  const requests: ApiReviewRequest[] = await (await request.get(`${api}/api/v1/review-requests?status=all&limit=200`)).json();
  const canonical = patients.filter(p => isCanonicalPatient(p.id));
  const canonicalQueue = requests.filter(r => isCanonicalPatient(r.patient_id));
  const writes: string[] = [];
  await page.route("**/api/v1/**", async route => {
    if (route.request().method() !== "GET") { writes.push(route.request().url()); return route.abort(); }
    return route.continue();
  });
  await page.goto("/");
  await expect(page.getByText(/Backend demo · canonical PostgreSQL/)).toBeVisible();
  await expect(page.locator("nav button")).toHaveCount(canonical.length);
  expect(canonical).toHaveLength(4);
  for (const p of canonical) await expect(page.getByRole("button", { name: new RegExp(p.synthetic_name) })).toBeVisible();
  await expect(page.getByText(/Loading observations and saved workflow/)).toHaveCount(0);
  await expect(page.getByText(/Saved patient state could not be loaded/)).toHaveCount(0);
  await page.screenshot({ path: "test-results/running-canonical-nurse.png", fullPage: true });
  await page.getByRole("button", { name: "Physician view", exact: true }).click();
  await expect(page.getByText(/Loading the review queue/)).toHaveCount(0);
  await expect(page.getByText(/Review queue unavailable/)).toHaveCount(0);
  await expect(page.locator("ol > li")).toHaveCount(canonicalQueue.length);
  for (const r of canonicalQueue) await expect(page.locator("ol")).toContainText(r.patient.synthetic_name);
  for (const name of ["Nieminen Pertti", "Lehtonen Juha", "Salminen Emma"]) await expect(page.getByText(new RegExp(name))).toHaveCount(0);
  expect(writes).toEqual([]);
  await page.screenshot({ path: "test-results/running-canonical-physician.png", fullPage: true });
});
