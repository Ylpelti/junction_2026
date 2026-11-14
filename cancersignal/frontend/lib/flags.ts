// Per-feature fallbacks for gaps in the backend API. Real backend data wins
// wherever an endpoint exists. Each flag has a TODO(backend) at its use site.

/** Appointment time and reason for visit (backend has no appointment data). */
export const USE_FALLBACK_APPOINTMENTS = true;

/**
 * Send to physician and the physician queue use the backend review-request API
 * (docs/physician-review-api.md). Falls back to the local workflow when the
 * backend is unreachable or the prototype dataset is selected.
 */
export const USE_BACKEND_REVIEW_QUEUE = true;

/**
 * Browser-state workflow: dismissal with reason and physician decisions (no endpoints yet),
 * plus send/queue whenever the backend review API is not used.
 */
export const USE_LOCAL_WORKFLOW = true;

/** Pre-filled routine/other-nurse items in the physician queue (no queue endpoint). */
export const USE_FALLBACK_QUEUE = true;

/**
 * Offer the prototype's synthetic patients and canned analysis results as a demo
 * data source. Used when chosen in the demo bar or when the backend is unreachable.
 * Results from this source are labelled "prototype demo data" in the UI.
 */
export const ALLOW_PROTOTYPE_DATASET = true;
