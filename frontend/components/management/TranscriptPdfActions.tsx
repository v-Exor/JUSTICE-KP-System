"use client";

import { Download, LoaderCircle, Printer } from "lucide-react";

export default function TranscriptPdfActions({
  canPrintTranscript,
  canDownloadPdf,
  canPrintSummary,
  downloading,
  onPrintTranscript,
  onDownloadPdf,
  onPrintSummary,
}: {
  canPrintTranscript: boolean;
  canDownloadPdf: boolean;
  canPrintSummary: boolean;
  downloading: boolean;
  onPrintTranscript: () => void;
  onDownloadPdf: () => void;
  onPrintSummary: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {canPrintTranscript && <button className="case-summary-secondary-action inline-flex h-9 items-center gap-2 rounded-md border border-white/20 px-3 text-xs font-black hover:bg-white/10" onClick={onPrintTranscript} type="button"><Printer size={15} /> Print transcript</button>}
      {canDownloadPdf && <button className="case-summary-secondary-action inline-flex h-9 items-center gap-2 rounded-md border border-white/20 px-3 text-xs font-black hover:bg-white/10 disabled:cursor-wait disabled:opacity-60" disabled={downloading} onClick={onDownloadPdf} type="button">{downloading ? <LoaderCircle className="animate-spin" size={15} /> : <Download size={15} />} {downloading ? "Generating..." : "Transcript PDF"}</button>}
      {canPrintSummary && <button className="inline-flex h-9 items-center gap-2 rounded-md bg-blue-600 px-3 text-xs font-black hover:bg-blue-500" onClick={onPrintSummary} type="button"><Printer size={15} /> Print one-page summary</button>}
    </div>
  );
}
