import { readFileSync } from "node:fs";
import { test, expect, type Page } from "@playwright/test";
import { patient, second, observation, run, review } from "./fixtures";

test.skip(!!process.env.E2E_REAL, "Mocked suite is separate from real PostgreSQL suite");
async function mock(page: Page, options: { failedDismissal?: boolean; lostNote?: boolean; slowPatient?: boolean } = {}) {
  let runs: typeof run[] = [], requests: typeof review[] = [], dismissal: any = null, decision: any = null;
  let notes: any[] = []; let notePosts = 0;
  await page.route("**/api/v1/**", async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, post = req.method() === "POST";
    const body = post ? req.postDataJSON() : null;
    const send = (data: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data), headers: { "access-control-allow-origin": "*" } });
    if (path.endsWith("/patients")) return send([patient, second]);
    if (path.endsWith("/observations")) {
      if (post) { notePosts++; const note = { ...observation, ...body, id: "saved-note" }; notes.push(note); if (options.lostNote) return route.abort(); return send(note, 201); }
      if (path.includes(second.id)) return send([]);
      return send([observation, ...notes]);
    }
    if (path.endsWith("/analyses")) {
      if (post) { runs = [{ ...run, provenance: { ...run.provenance, input_observation_id: body.note_observation_id } }]; return send(runs[0], 201); }
      if (path.includes(second.id)) return send([]);
      if (options.slowPatient) await new Promise(r => setTimeout(r, 300));
      return send(runs);
    }
    if (path.endsWith("/dismissal")) {
      if (options.failedDismissal && !post) return send({}, 503);
      if (post) dismissal = { ...body, id: "dismissal", analysis_id: run.id, created_at: run.created_at };
      return send(dismissal ?? {}, dismissal ? 200 : 404);
    }
    if (path.endsWith("/decision")) {
      if (post) { decision = { ...body, id: "decision", review_request_id: review.id, status: "reviewed", created_at: run.created_at }; requests = requests.map(r => ({ ...r, status: "reviewed" })); }
      return send(decision ?? {}, decision ? 200 : 404);
    }
    if (path.endsWith("/review-requests")) {
      if (post) { if (!requests.length) requests = [{ ...review, analysis: runs[0] }]; return send(requests[0], 201); }
      return send(requests.filter(r => (url.searchParams.get("status") === "all" || r.status === url.searchParams.get("status")) && (!url.searchParams.has("patient_id") || r.patient_id === url.searchParams.get("patient_id"))));
    }
    return send({}, 404);
  });
  return { count: () => notePosts };
}
async function save(page: Page) {
  await page.getByLabel("Nursing note", { exact: true }).fill("SYNTHETIC new note");
  await page.getByRole("button", { name: "Save note", exact: true }).click();
  await page.getByRole("button", { name: "Open findings", exact: true }).click();
}
test("handoff and physician decision persist across reload, reviewed leaves pending", async ({ page }) => {
  await mock(page); await page.goto("/"); await save(page);
  await page.getByRole("button", { name: "Send to physician", exact: true }).click();
  await expect(page.getByText("Sent to the physician.", { exact: true })).toBeVisible();
  await page.reload(); await expect(page.getByText("Sent to the physician.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Physician view", exact: true }).click();
  await page.getByText("Record a simulated decision", { exact: true }).click();
  await page.getByRole("button", { name: "Simulate FIT order (stool blood test)", exact: true }).click();
  await expect(page.getByText("No pending review requests.")).toBeVisible();
  await expect(page.getByText(/Decided: FIT ordered/)).toBeVisible();
  await page.reload(); await page.getByRole("button", { name: "Physician view", exact: true }).click();
  await expect(page.getByText(/Decided: FIT ordered/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Simulate FIT order/ })).toHaveCount(0);
});
test("dismissal restores exact reason and does not cross patient boundaries", async ({ page }) => {
  await mock(page); await page.goto("/"); await save(page);
  await page.getByRole("button", { name: "Dismiss with reason" }).click();
  await page.getByRole("radio", { name: "Patient declined further investigation" }).click();
  await page.getByRole("button", { name: "Confirm dismissal" }).click();
  await expect(page.getByText(/Dismissed: Patient declined/)).toBeVisible();
  await page.reload(); await expect(page.getByText(/Dismissed: Patient declined/)).toBeVisible();
  await page.getByRole("button", { name: /SYNTHETIC Nieminen/ }).click();
  await expect(page.getByText(/Dismissed:/)).toHaveCount(0);
  await page.getByRole("button", { name: /SYNTHETIC Laine/ }).click();
  await expect(page.getByText(/Dismissed: Patient declined/)).toBeVisible();
});
test("failed dismissal restoration blocks actions instead of treating it as absent", async ({ page }) => {
  await mock(page, { failedDismissal: true }); await page.goto("/"); await save(page); await page.reload();
  await expect(page.getByText(/Saved patient state could not be loaded/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Save note", exact: true })).toBeDisabled();
});
test("lost note response reconciles the saved UUID without another note POST", async ({ page }) => {
  const backend = await mock(page, { lostNote: true }); await page.goto("/");
  await page.getByLabel("Nursing note", { exact: true }).fill("SYNTHETIC new note");
  await page.getByRole("button", { name: "Save note", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save note", exact: true })).toBeDisabled();
  await page.reload(); await page.getByRole("button", { name: "Reconcile saved history" }).click();
  await page.getByRole("button", { name: "Analyse saved note" }).click();
  await expect(page.getByRole("button", { name: "Open findings", exact: true })).toBeVisible();
  expect(backend.count()).toBe(1);
});
test("live queue failure never displays plausible prototype requests", async ({ page }) => {
  await mock(page); await page.goto("/");
  await page.route("**/api/v1/review-requests?**", route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Physician view", exact: true }).click();
  await expect(page.getByText(/Review queue unavailable/)).toBeVisible();
  await expect(page.locator("ol > li")).toHaveCount(0);
  await page.getByRole("button", { name: "Prototype data", exact: true }).click();
  await expect(page.getByText("Demo data").first()).toBeVisible();
});
test("selecting the active patient preserves the loaded analysis", async ({ page }) => {
  await mock(page); await page.goto("/"); await save(page);
  await page.reload(); await expect(page.getByText("Physician review recommended", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /SYNTHETIC Laine/ }).click();
  await expect(page.getByText("Physician review recommended", { exact: true })).toBeVisible();
});
test("in-flight note save locks patient selection and suppresses duplicate clicks", async ({ page }) => {
  const backend = await mock(page); await page.goto("/");
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/observations", async route => { if (route.request().method() === "POST") await gate; await route.fallback(); });
  await page.getByLabel("Nursing note", { exact: true }).fill("SYNTHETIC new note");
  await page.getByRole("button", { name: "Save note", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(page.getByRole("button", { name: /SYNTHETIC Nieminen/ })).toBeDisabled();
  release();
  await expect(page.getByRole("button", { name: "Open findings", exact: true })).toBeVisible();
  expect(backend.count()).toBe(1);
});
test("late patient response cannot replace the next patient's history", async ({ page }) => {
  await mock(page, { slowPatient: true }); await page.goto("/");
  await page.getByRole("button", { name: /SYNTHETIC Nieminen/ }).click();
  await expect(page.getByRole("heading", { name: "SYNTHETIC Nieminen", exact: true })).toBeVisible();
  await expect(page.getByLabel("Nursing note", { exact: true })).toBeEnabled();
  // Wait for the intentionally delayed first patient response via a route event.
  await page.waitForTimeout(350);
  await expect(page.getByText("SYNTHETIC source record", { exact: true })).toHaveCount(0);
});

test("four editable examples never auto-submit and drafts survive switching and reload", async ({ page }) => {
  const examples: Record<string, string> = JSON.parse(readFileSync("data/demo-notes.json", "utf8"));
  const ids = Object.keys(examples);
  let posts = 0;
  await mock(page);
  await page.route("**/api/v1/patients?**", route => route.fulfill({ json: ids.map((id, i) => ({ ...patient, id, synthetic_name: `SYNTHETIC ${["Laine", "Nieminen", "Heikkinen", "Korhonen"][i]}` })) }));
  for (const id of ids.slice(2)) await page.route(`**/api/v1/patients/${id}/observations?**`, route => route.fulfill({ json: [] }));
  page.on("request", req => { if (req.method() === "POST") posts++; });
  await page.goto("/");
  const note = page.getByLabel("Nursing note", { exact: true });
  for (const [i, id] of ids.entries()) {
    await page.getByRole("button", { name: new RegExp(`SYNTHETIC ${["Laine", "Nieminen", "Heikkinen", "Korhonen"][i]}`) }).click();
    await expect(note).toBeEnabled();
    await expect(note).toHaveValue(examples[id as keyof typeof examples]);
    await note.fill(`SYNTHETIC edited ${i}`);
  }
  await page.getByRole("button", { name: /SYNTHETIC Laine/ }).click();
  await expect(note).toHaveValue("SYNTHETIC edited 0");
  await page.reload();
  await expect(note).toHaveValue("SYNTHETIC edited 0");
  await note.fill("");
  await page.reload();
  await expect(note).toHaveValue("");
  expect(posts).toBe(0);
});

test("saving an example runs analysis and does not refill the cleared editor", async ({ page }) => {
  const backend = await mock(page);
  await page.goto("/");
  const note = page.getByLabel("Nursing note", { exact: true });
  await expect(note).toHaveValue(/SYNTHETIC/);
  await page.getByRole("button", { name: "Save note", exact: true }).click();
  await expect(page.getByRole("button", { name: "Open findings", exact: true })).toBeVisible();
  await expect(note).toHaveValue("");
  await page.reload();
  await expect(note).toHaveValue("");
  expect(backend.count()).toBe(1);
});
