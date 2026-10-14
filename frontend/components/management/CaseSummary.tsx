"use client";

import axios from "axios";
import { CheckCircle2, ChevronLeft, Download, FileArchive, FileText, Mic, Shield } from "lucide-react";
import { useState, type ReactNode } from "react";
import { formatPhilippineDateTime } from "../philippineTime";
import TranscriptPdfActions from "./TranscriptPdfActions";

type CompletedTranscriptSegment = {
  speaker: string;
  start?: number | null;
  end?: number | null;
  text: string;
  confidence?: number | null;
};

export type CompletedCaseSummary = {
  workflow: { workflow_id: string; case_id: string; case_analysis_id: number; transcript_id: number | null; status: string; revision: number; created_at: string; updated_at: string };
  privacy: { is_sensitive: boolean; sensitivity_category: string; redacted: boolean; notice: string };
  final_outcome: { outcome: string; record_status: string; finalized_at: string; cancelled: boolean; cancellation_reason: string | null; cancelled_at: string | null; cancelled_by: string | null };
  case_information: Record<string, unknown>;
  transcript: (Record<string, unknown> & {
    id: number;
    content: string;
    redacted: boolean;
    recording_type: "blotter_case" | "blotter_hearing";
    recording_type_label: string;
    participant_roles: string[];
    participant_transcripts: Array<{ role: string; segment_count: number; text: string }>;
    segments: CompletedTranscriptSegment[];
    created_at: string;
    updated_at: string;
  }) | null;
  phase2_analysis: Record<string, unknown> & { analysis_id: number; jurisdiction_decision: string; exclusion_ground: string; confidence_level: string; recommended_next_action: string };
  jurisdiction: { decision: string; exclusion_ground: string; confidence_level: string };
  xai_reasoning: { trace: string[]; explanation: string };
  phase3_routing: Record<string, unknown> & { sensitive_routing: Record<string, unknown> | null; mediation_eligibility: Record<string, unknown> | null; recommended_route: string };
  referral_resolution: { workflow_resolution: Record<string, unknown> | null; referrals: Array<Record<string, unknown>> };
  hearings: Array<Record<string, unknown>>;
  evidence: Array<Record<string, unknown> & { id: number; file_name: string; download_url: string | null }>;
  official_decision: Record<string, unknown> | null;
  phase4_packet: (Record<string, unknown> & { generated_forms: Array<Record<string, unknown> & { id: number; title: string; download_url: string | null }> }) | null;
  audit_history: Array<{ id: number; action: string; actor: string; actor_role: string; risk_level: string; details: Record<string, unknown>; created_at: string }>;
  actions: { can_view_transcript: boolean; can_print_transcript: boolean; can_download_transcript_pdf: boolean; can_view_evidence: boolean; can_download_evidence: boolean; can_download_forms: boolean; can_print_summary: boolean };
};

function summaryLabel(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function summaryValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.map(summaryValue).join(", ") : "None";
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length ? entries.map(([key, item]) => `${summaryLabel(key)}: ${summaryValue(item)}`).join(" · ") : "None";
  }
  return String(value);
}

function SummaryFields({ values, omit = [] }: { values: Record<string, unknown>; omit?: string[] }) {
  const entries = Object.entries(values).filter(([key]) => !omit.includes(key));
  if (!entries.length) return <p className="text-sm font-bold text-gray-500">No record available.</p>;
  return (
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {entries.map(([key, value]) => (
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3" key={key}>
          <dt className="text-[11px] font-black uppercase tracking-wide text-gray-500">{summaryLabel(key)}</dt>
          <dd className="mt-1 break-words text-sm font-bold leading-5 text-gray-900">{summaryValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function CaseSummarySection({ number, title, children, id }: { number: number; title: string; children: ReactNode; id?: string }) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:p-5" id={id}>
      <div className="mb-4 flex items-center gap-3 border-b border-gray-100 pb-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-blue-600 text-xs font-black text-white">{number}</span>
        <h3 className="text-base font-black text-gray-950">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function formatTranscriptTime(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--:--";
  const totalSeconds = Math.max(0, Math.floor(value));
  return `${Math.floor(totalSeconds / 60).toString().padStart(2, "0")}:${(totalSeconds % 60).toString().padStart(2, "0")}`;
}

function openPrintableRecord(title: string, lines: string[], layout: "document" | "compact" = "document") {
  const popup = window.open("", "_blank");
  if (!popup) {
    window.alert("Allow pop-ups for this site to print the record.");
    return;
  }
  popup.opener = null;
  const escapeHtml = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\"/g, "&quot;").replace(/'/g, "&#039;");
  popup.document.write(`<!doctype html><html><head><title>${escapeHtml(title)}</title><style>@page{size:A4;margin:10mm}body{font-family:Arial,sans-serif;margin:28px;color:#111827}h1{font-size:18px;border-bottom:2px solid #1d4ed8;padding-bottom:9px;margin:0 0 10px}.content{display:block}.line{white-space:pre-wrap;font-size:11px;line-height:1.45;padding:4px 0;border-bottom:1px solid #e5e7eb}.compact .content{display:grid;grid-template-columns:1fr 1fr;column-gap:18px}.compact .line{font-size:9.5px;line-height:1.3;padding:2px 0;break-inside:avoid}@media print{body{margin:0}}</style></head><body class="${layout}"><h1>${escapeHtml(title)}</h1><div class="content">${lines.map((line) => `<div class="line">${escapeHtml(line)}</div>`).join("")}</div><script>window.onload=()=>window.print()<\/script></body></html>`);
  popup.document.close();
}

function completedTranscriptLines(summary: CompletedCaseSummary) {
  if (!summary.transcript) return [];
  const coverage = summary.transcript.participant_transcripts.map((participant) => `${participant.role}: ${participant.segment_count > 0 ? `${participant.segment_count} recorded statement${participant.segment_count === 1 ? "" : "s"}` : "No recorded statement"}`);
  const lines = summary.transcript.segments.length
    ? summary.transcript.segments.map((segment) => `[${formatTranscriptTime(segment.start)}–${formatTranscriptTime(segment.end)}] ${segment.speaker}: ${segment.text}`)
    : [summary.transcript.content || "No transcript text was saved."];
  return [`Case ID: ${summary.workflow.case_id}`, `Recording: ${summary.transcript.recording_type_label}`, `Participants: ${summary.transcript.participant_roles.join(", ")}`, ...coverage, "", "Transcript", ...lines];
}

async function downloadTranscriptPdf(summary: CompletedCaseSummary, apiBaseUrl: string) {
  const response = await axios.get<Blob>(`${apiBaseUrl}/api/management/cases/${encodeURIComponent(summary.workflow.workflow_id)}/transcript.pdf`, { responseType: "blob" });
  const disposition = String(response.headers["content-disposition"] ?? "");
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? `${summary.workflow.case_id.replace(/[^A-Za-z0-9_-]+/g, "-")}-complete-transcript.pdf`;
  const objectUrl = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
  return String(response.headers["x-document-sha256"] ?? "");
}

function printCaseSummary(summary: CompletedCaseSummary) {
  const printableFields = ["barangay_name", "city_municipality", "case_year", "case_type", "dispute_category", "complainant_residency", "respondent_residency", "proceeding_origin", "offense_classification", "debt_amount_php", "maximum_penalty_years", "fine_amount_php", "sensitivity_level"];
  openPrintableRecord(`Completed Case Summary — ${summary.workflow.case_id}`, [
    `Workflow ID: ${summary.workflow.workflow_id}`,
    `Case ID: ${summary.workflow.case_id}`,
    `Status: ${summary.final_outcome.record_status}`,
    `Final outcome: ${summary.final_outcome.outcome}`,
    `Finalized: ${formatPhilippineDateTime(summary.final_outcome.finalized_at)}`,
    `Privacy: ${summary.privacy.notice}`,
    ...Object.entries(summary.case_information).filter(([key, value]) => printableFields.includes(key) && value !== null && value !== "").map(([key, value]) => `${summaryLabel(key)}: ${summaryValue(value)}`),
    `Jurisdiction: ${summaryValue(summary.jurisdiction.decision)}`,
    `Exclusion ground: ${summaryValue(summary.jurisdiction.exclusion_ground)}`,
    `Recommended route: ${summaryValue(summary.phase3_routing.recommended_route)}`,
    `Official decision: ${summaryValue(summary.official_decision)}`,
    `Hearings: ${summary.hearings.length}`,
    `Evidence records: ${summary.evidence.length}`,
    `KP forms: ${summary.phase4_packet?.generated_forms.length ?? 0}`,
    `Audit events: ${summary.audit_history.length}`,
  ], "compact");
}

export default function CaseSummaryPage({ summary, apiBaseUrl, onBack }: { summary: CompletedCaseSummary; apiBaseUrl: string; onBack: () => void }) {
  const [activePanel, setActivePanel] = useState<"summary" | "transcript" | "records">("summary");
  const [downloading, setDownloading] = useState(false);
  const [pdfMessage, setPdfMessage] = useState("");

  const handleDownload = async () => {
    setDownloading(true);
    setPdfMessage("");
    try {
      const hash = await downloadTranscriptPdf(summary, apiBaseUrl);
      setPdfMessage(hash ? `Transcript PDF downloaded. SHA-256: ${hash}` : "Transcript PDF downloaded and recorded in the audit timeline.");
    } catch (error) {
      let detail = "Unable to generate the transcript PDF.";
      if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
        try {
          const payload = JSON.parse(await error.response.data.text()) as { detail?: string };
          detail = payload.detail ?? detail;
        } catch {
          // Keep the safe fallback for a non-JSON server response.
        }
      }
      setPdfMessage(detail);
    } finally {
      setDownloading(false);
    }
  };

  const transcriptMetadata = summary.transcript ? Object.fromEntries(Object.entries(summary.transcript).filter(([key]) => !["content", "segments", "participant_roles", "participant_transcripts", "redacted"].includes(key))) : {};
  const routingDetails = Object.fromEntries(Object.entries(summary.phase3_routing).filter(([key]) => !["mediation_suggestions", "emotion_analysis"].includes(key)));
  const caseInformation = Object.fromEntries(Object.entries(summary.case_information).filter(([key, value]) => !["case_id", "created_at"].includes(key) && value !== null && value !== "" && value !== false && value !== 0));

  return (
    <div className="page-enter mx-auto max-w-7xl space-y-4">
      <header className="case-summary-header rounded-lg border border-transparent bg-slate-950 p-5 text-white shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <button className="case-summary-back-button mb-4 inline-flex h-10 items-center gap-2 rounded-md border border-sky-200 bg-white px-4 text-sm font-black text-slate-950 shadow-lg shadow-sky-500/20 transition hover:border-sky-300 hover:bg-sky-50 hover:text-blue-800 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-sky-400/40" onClick={onBack} type="button"><ChevronLeft size={17} /> Back to Cases</button>
            <p className="case-summary-eyebrow text-xs font-black uppercase tracking-[0.22em] text-sky-300">Completed case record</p>
            <h1 className="mt-1 text-2xl font-black">{summary.workflow.case_id}</h1>
            <p className="case-summary-meta mt-1 text-xs text-slate-400">Workflow {summary.workflow.workflow_id} · Analysis #{summary.workflow.case_analysis_id}</p>
          </div>
          <TranscriptPdfActions canDownloadPdf={summary.actions.can_download_transcript_pdf} canPrintSummary={summary.actions.can_print_summary} canPrintTranscript={summary.actions.can_print_transcript} downloading={downloading} onDownloadPdf={() => handleDownload().catch(() => undefined)} onPrintSummary={() => printCaseSummary(summary)} onPrintTranscript={() => openPrintableRecord(`Transcript — ${summary.workflow.case_id}`, completedTranscriptLines(summary))} />
        </div>
        {pdfMessage && <p className="mt-4 break-all rounded-md border border-white/20 bg-white/10 px-3 py-2 text-xs font-bold text-sky-100" role="status">{pdfMessage}</p>}
      </header>

      <div className={`flex items-start gap-3 rounded-lg border p-4 ${summary.privacy.is_sensitive ? "border-red-300 bg-red-50 text-red-900" : "border-emerald-200 bg-emerald-50 text-emerald-900"}`}>
        {summary.privacy.is_sensitive ? <Shield className="mt-0.5 shrink-0" size={20} /> : <CheckCircle2 className="mt-0.5 shrink-0" size={20} />}
        <div><p className="font-black">{summary.privacy.is_sensitive ? `Sensitive case — ${summary.privacy.sensitivity_category}` : "Standard case record"}</p><p className="mt-1 text-sm font-medium">{summary.privacy.notice}</p></div>
      </div>

      <nav aria-label="Case summary sections" className="flex flex-wrap gap-2 rounded-lg border border-gray-200 bg-white p-2 shadow-sm">
        {([["summary", "Case summary", FileText], ["transcript", "Transcript", Mic], ["records", "Records & audit", FileArchive]] as const).map(([panel, label, Icon]) => (
          <button className={`inline-flex h-10 items-center gap-2 rounded-md px-4 text-sm font-black transition ${activePanel === panel ? "bg-blue-600 text-white" : "text-gray-600 hover:bg-gray-100"}`} key={panel} onClick={() => setActivePanel(panel)} type="button"><Icon size={16} /> {label}</button>
        ))}
      </nav>

      {activePanel === "summary" && <div className="grid gap-4 xl:grid-cols-2">
        <CaseSummarySection number={1} title="Case overview"><SummaryFields values={{ case_id: summary.workflow.case_id, workflow_status: summary.workflow.status, case_analysis_id: summary.workflow.case_analysis_id, created_at: formatPhilippineDateTime(summary.workflow.created_at), last_updated: formatPhilippineDateTime(summary.workflow.updated_at) }} /></CaseSummarySection>
        <CaseSummarySection number={2} title="Final outcome"><SummaryFields values={{ outcome: summary.final_outcome.outcome, record_status: summary.final_outcome.record_status, finalized_at: formatPhilippineDateTime(summary.final_outcome.finalized_at), cancelled: summary.final_outcome.cancelled }} /></CaseSummarySection>
        <CaseSummarySection number={3} title="Case information"><SummaryFields values={caseInformation} /></CaseSummarySection>
        <CaseSummarySection number={4} title="Jurisdiction and routing"><SummaryFields values={{ ...summary.jurisdiction, recommended_next_action: summary.phase2_analysis.recommended_next_action, recommended_route: summary.phase3_routing.recommended_route }} /></CaseSummarySection>
        <CaseSummarySection number={5} title="XAI reasoning"><ol className="space-y-2">{summary.xai_reasoning.trace.length ? summary.xai_reasoning.trace.map((item, index) => <li className="flex gap-3 rounded-md border border-blue-100 bg-blue-50 p-3 text-sm leading-5 text-blue-950" key={`${index}-${item}`}><span className="font-black">{index + 1}.</span><span>{item}</span></li>) : <li className="text-sm font-bold text-gray-500">No XAI trace was recorded.</li>}</ol></CaseSummarySection>
        <CaseSummarySection number={6} title="Official result"><SummaryFields values={{ official_decision: summary.official_decision, referral_resolution: summary.referral_resolution.workflow_resolution, phase3_routing: routingDetails }} /></CaseSummarySection>
      </div>}

      {activePanel === "transcript" && <CaseSummarySection id="case-summary-transcript" number={1} title="Printable transcript">
        {summary.transcript ? <><SummaryFields values={transcriptMetadata} /><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{summary.transcript.participant_transcripts.map((participant) => <div className={`rounded-md border p-3 ${participant.segment_count ? "border-blue-200 bg-blue-50" : "border-amber-200 bg-amber-50"}`} key={participant.role}><p className="font-black text-gray-950">{participant.role}</p><p className="mt-1 text-xs font-bold text-gray-600">{participant.segment_count ? `${participant.segment_count} recorded statement${participant.segment_count === 1 ? "" : "s"}` : "No recorded statement in this saved transcript"}</p></div>)}</div><div className={`mt-4 rounded-md border p-4 ${summary.transcript.redacted ? "border-red-200 bg-red-50" : "border-gray-200 bg-gray-50"}`}>{summary.transcript.redacted ? <p className="text-sm font-bold text-red-800">Transcript content is protected for your role.</p> : summary.transcript.segments.length ? <div className="space-y-3">{summary.transcript.segments.map((segment, index) => <div className="rounded-md border border-gray-200 bg-white p-3" key={`${segment.speaker}-${segment.start}-${index}`}><div className="flex flex-wrap items-center gap-2"><span className="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-black text-blue-800">{segment.speaker}</span><span className="text-xs font-bold text-gray-500">{formatTranscriptTime(segment.start)}–{formatTranscriptTime(segment.end)}</span></div><p className="mt-2 text-sm leading-6 text-gray-800">{segment.text}</p></div>)}</div> : <p className="whitespace-pre-wrap text-sm leading-6 text-gray-800">{summary.transcript.content || "No transcript text was saved."}</p>}</div></> : <p className="text-sm font-bold text-gray-500">No linked transcript is available.</p>}
      </CaseSummarySection>}

      {activePanel === "records" && <div className="grid gap-4 xl:grid-cols-2">
        <CaseSummarySection number={1} title="Hearings">{summary.hearings.length ? <div className="space-y-3">{summary.hearings.map((hearing, index) => <SummaryFields key={String(hearing.id ?? index)} values={hearing} omit={["id", "case_id"]} />)}</div> : <p className="text-sm font-bold text-gray-500">No hearing history was recorded.</p>}</CaseSummarySection>
        <CaseSummarySection number={2} title="Evidence">{summary.evidence.length ? <div className="space-y-3">{summary.evidence.map((item) => <div className="flex items-center justify-between gap-3 rounded-md border border-gray-200 bg-gray-50 p-4" key={item.id}><div><p className="font-black text-gray-950">{item.file_name}</p><p className="mt-1 text-xs text-gray-500">Uploaded {formatPhilippineDateTime(String(item.uploaded_at ?? ""))}</p></div>{item.download_url && <a className="inline-flex h-9 items-center gap-2 rounded-md border border-blue-200 bg-white px-3 text-xs font-black text-blue-700" href={`${apiBaseUrl}${item.download_url}`}><Download size={15} /> Download</a>}</div>)}</div> : <p className="text-sm font-bold text-gray-500">No evidence was attached.</p>}</CaseSummarySection>
        <CaseSummarySection number={3} title="KP forms">{summary.phase4_packet ? <div className="grid gap-3 sm:grid-cols-2">{summary.phase4_packet.generated_forms.map((form) => <div className="rounded-md border border-gray-200 bg-gray-50 p-4" key={form.id}><p className="font-black text-gray-950">{form.title}</p>{form.download_url ? <a className="mt-3 inline-flex h-9 items-center gap-2 rounded-md border border-blue-200 bg-white px-3 text-xs font-black text-blue-700" href={`${apiBaseUrl}${form.download_url}`} rel="noreferrer" target="_blank"><Download size={15} /> View / download</a> : <p className="mt-3 text-xs font-bold text-gray-500">Download unavailable for your role.</p>}</div>)}</div> : <p className="text-sm font-bold text-gray-500">No Phase 4 packet is linked to this workflow.</p>}</CaseSummarySection>
        <CaseSummarySection number={4} title="Audit timeline">{summary.audit_history.length ? <ol className="relative ml-2 border-l border-gray-200 pl-5">{summary.audit_history.map((event) => <li className="relative pb-5 last:pb-0" key={event.id}><span className="absolute -left-[25px] top-1 size-2 rounded-full bg-blue-600 ring-4 ring-white" /><p className="font-black text-gray-950">{summaryLabel(event.action)}</p><p className="mt-1 text-xs font-bold text-gray-500">{formatPhilippineDateTime(event.created_at)} · {event.actor || "system"}</p></li>)}</ol> : <p className="text-sm font-bold text-gray-500">No audit events were found.</p>}</CaseSummarySection>
      </div>}
    </div>
  );
}
