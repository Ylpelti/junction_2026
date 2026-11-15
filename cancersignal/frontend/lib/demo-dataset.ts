// Dataset membership only. IDs come from backend/app/db/demo_data/patients.en-v2.json.
// Never put clinical fixture content, expected findings or priorities here.
// Regression tests verify this registry against the canonical source fixture.
export const CANONICAL_PATIENT_IDS: readonly string[] = [
  "890bf4db-36e8-542e-b009-901f2d6a6f41",
  "46ee7817-ff3e-5a1e-9912-046c5e85e0d4",
  "3ebb5257-b8be-5e66-8064-3bffc5c800c0",
  "9704c785-e9fc-5cd0-bdae-4e36e4235a42"
];
export const isCanonicalPatient = (id: string) => CANONICAL_PATIENT_IDS.includes(id);
export const isUuid = (id: unknown): id is string => typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
