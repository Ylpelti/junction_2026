"use client";

import { useEffect, useRef } from "react";

import type { AnalysisResult, Patient } from "../lib/types";

export function UrgentModal({ patient, result, onOpen }: { patient: Patient; result: AnalysisResult; onOpen: () => void }) {
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => button.current?.focus(), []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(17,24,39,0.55)] p-6">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="cs-urgent-title"
        aria-describedby="cs-urgent-summary"
        className="cs-modal flex w-full max-w-[520px] flex-col overflow-hidden rounded-2xl border-3 border-red-main bg-white"
      >
        <div className="flex items-center gap-3 bg-red-main px-5.5 py-4.5 text-white">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3l10 18H2z" />
            <path d="M12 10v5M12 18v.5" />
          </svg>
          <div className="flex flex-col">
            <span className="text-[12.5px] font-semibold tracking-[0.06em] uppercase opacity-90">CancerSignal</span>
            <span id="cs-urgent-title" className="text-[21px] font-bold">
              Urgent physician review
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-3.5 px-5.5 py-5">
          <span className="text-[15px] font-semibold">
            {patient.name} · {patient.demo}
          </span>
          <span id="cs-urgent-summary" className="text-[15px] leading-normal text-ink-2">
            {result.summary}
          </span>
          <ul className="m-0 flex flex-col gap-1.5 pl-5">
            {result.findings.map((f) => (
              <li key={f.id} className="text-[14.5px] font-semibold text-red-ink">
                {f.title}
              </li>
            ))}
          </ul>
          <button
            ref={button}
            type="button"
            onClick={onOpen}
            className="min-h-13 cursor-pointer rounded-[10px] border-0 bg-red-main px-5.5 py-3 text-base font-bold text-white"
          >
            Open findings
          </button>
          <span className="text-center text-[12.5px] text-mute-2">This alert stays until the findings are opened.</span>
        </div>
      </div>
    </div>
  );
}
