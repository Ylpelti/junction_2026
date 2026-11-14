import { formatMeasurement } from "../lib/format";
import type { AnalysisResult } from "../lib/types";

/** Original API records; presentation only, no derived clinical quantities. */
export function AnalysisEvidence({ analysis }: { analysis: AnalysisResult }) {
  return <details className="rounded-xl border border-line bg-white p-3 text-sm">
    <summary className="cursor-pointer font-semibold">Clinical findings and source observations</summary>
    {analysis.clinicalFindings?.map(f => <p key={f.id}>{f.description} · {f.status}{f.uncertainty ? ` · ${f.uncertainty}` : ""}</p>)}
    {analysis.sourceObservations?.map(o => <article key={o.id} className="mt-3 border-t border-line pt-2">
      <p className="break-all text-xs text-mute">{o.id} · {o.observed_at} · recorded {o.recorded_at}</p>
      <p className="whitespace-pre-wrap">{o.text}</p>
      <p>{[o.code, formatMeasurement(o.numeric_value, o.unit), o.status].filter(v => v != null).join(" · ")}</p>
      <details className="text-xs text-mute"><summary>Original stored measurement</summary>{o.numeric_value ?? "—"} {o.unit ?? ""}</details>
      {o.encounter_id && <p className="break-all text-xs">Encounter: {o.encounter_id}</p>}
    </article>)}
    {!analysis.sourceObservations?.length && <p>No source observations returned.</p>}
    {analysis.missing.map((item, i) => <p key={i} className="text-mute">{item}</p>)}
  </details>;
}
