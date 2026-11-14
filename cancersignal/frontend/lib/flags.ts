// Per-feature fallbacks for gaps in the backend API. Real backend data wins
// wherever an endpoint exists. Each flag has a TODO(backend) at its use site.

/** Appointment time and reason for visit (backend has no appointment data). */
export const USE_FALLBACK_APPOINTMENTS = true;

/** Send to physician, dismiss with reason and physician decisions live in client state (no endpoints). */
export const USE_LOCAL_WORKFLOW = true;

/** Pre-filled routine/other-nurse items in the physician queue (no queue endpoint). */
export const USE_FALLBACK_QUEUE = true;

/**
 * Offer the prototype's synthetic patients and canned analysis results as a demo
 * data source. Used when chosen in the demo bar or when the backend is unreachable.
 * Results from this source are labelled "prototype demo data" in the UI.
 */
export const ALLOW_PROTOTYPE_DATASET = true;
