"use client";

import axios from "axios";
import {
  AlertTriangle,
  Brain,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  Download,
  Eye,
  FileCheck2,
  Gavel,
  RefreshCw,
  Route,
  ShieldAlert,
  UploadCloud,
  UsersRound,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState, type ReactNode } from "react";
import { formatDisplayLabel, humanizeDisplayText } from "./displayText";
import { formatPhilippineDateTime } from "./philippineTime";

function resolveApiBaseUrl() {
  const browserHost = typeof window === "undefined" ? "" : window.location.hostname;
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  const fallbackHost = browserHost || "localhost";

  if (!configured) {
    return `http://${fallbackHost}:8000`;
  }

  try {
    const configuredUrl = new URL(configured);
    const loopbackHosts = new Set(["localhost", "127.0.0.1", "::1"]);

    if (browserHost && loopbackHosts.has(browserHost) && loopbackHosts.has(configuredUrl.hostname)) {
      configuredUrl.hostname = browserHost;
    }

    return configuredUrl.origin;
  } catch {
    return configured;
  }
}

const API_BASE_URL = resolveApiBaseUrl();
axios.defaults.withCredentials = true;

type CaseAnalysisSummary = {
  id: number;
  case_id: string;
  barangay_name: string;
  jurisdiction_decision: string;
  recommended_next_action: string;
  created_at: string;
};

type Phase3Dashboard = {
  case_id: string;
  phase1: {
    transcript_id: number | null;
    transcript: string;
    segments: Array<Record<string, unknown>>;
  };
  phase2: {
    analysis_id: number;
    case_information: Record<string, unknown>;
    extracted_entities: Record<string, unknown>;
    detected_keywords: { detected_keywords?: string[]; keyword_count?: number; vawc_trigger?: boolean };
    jurisdiction_decision: string;
    normalized_jurisdiction_decision: "within_kp" | "outside_kp" | "ambiguous";
    exclusion_ground: string;
    confidence_level: string;
    recommended_next_action: string;
    xai_trace: string[];
    rule_results: Array<Record<string, unknown>>;
  };
  phase3: {
    sensitive_routing: Phase3Route | null;
    mediation_eligibility: MediationEligibility | null;
    mediation_suggestions: MediationSuggestions | null;
    referrals: ReferralRecord[];
    hearings: HearingRecord[];
    evidence: EvidenceRecord[];
    emotion_analysis: EmotionAnalysis | null;
    official_decision: OfficialDecision | null;
    final_recommended_action: string;
    disclaimer: string;
  };
};

export type Phase3DashboardView = "all" | "preparation" | "analysis" | "routing" | "mediation";

type Phase3Route = {
  id?: number;
  case_id: string;
  is_sensitive: boolean;
  sensitive_category: string;
  recommended_route: string;
  reason: string;
  matched_keywords: string[];
  confidence_level: string;
  blocking_mediation: boolean;
};

type MediationEligibility = {
  eligible_for_mediation: boolean;
  reason: string;
  required_action: string;
};

type MediationSuggestionItem = {
  title: string;
  description: string;
  recommended_terms: string[];
  why_suggested: string;
  risk_level: "low" | "medium" | "high";
};

type MediationSuggestions = {
  dispute_category: string;
  suggestions_json: MediationSuggestionItem[];
  xai_explanation_json: string[];
};

type ReferralRecord = {
  id: number;
  referral_type: string;
  destination: string;
  reason: string;
  matched_keywords: string[];
  xai_reference: string[];
  status: "pending" | "completed" | "cancelled";
  created_at: string;
};

type ReferralWorkflowAction = "complete_and_advance" | "cancel_referral";
type ReferralWorkflowActionHandler = (
  referralId: number,
  action: ReferralWorkflowAction,
  reason?: string,
) => Promise<{ message?: string }>;

type HearingRecord = {
  id: number;
  hearing_type: string;
  scheduled_date: string;
  scheduled_time: string;
  location: string;
  assigned_lupon_member: string;
  status: "scheduled" | "completed" | "missed" | "cancelled";
  notes: string;
};

type EvidenceRecord = {
  id: number;
  file_name: string;
  file_type: string;
  evidence_text: string;
  extracted_entities_json: Record<string, unknown>;
  uploaded_at: string;
};

type EmotionAnalysis = {
  emotion_label: string;
  tension_score: number;
  detected_terms: string[];
  mediation_advice: string;
};

type OfficialDecision = {
  official_decision: string;
  official_notes: string;
  approved_by: string;
  approved_at: string;
  system_recommendation: string;
};

type Phase4Template = {
  form_id: string;
  form_number: string;
  title: string;
  purpose: string;
  stage: string;
  required_fields: string[];
  when_used: string[];
  source_template_url: string;
};

type Phase4Recommendation = {
  case_id: string;
  final_recommended_action: string;
  recommended_forms: Phase4Template[];
  optional_forms: Phase4Template[];
  missing_fields: Record<string, string[]>;
  validation_status: "ready" | "needs_review";
  form_accuracy_pct: number;
};

type Phase4GeneratedForm = {
  id: number;
  form_id: string;
  title: string;
  purpose: string;
  download_url: string;
  missing_fields: string[];
  validation_status: "ready" | "needs_review";
  created_at: string;
};

type Phase4Packet = {
  id: number;
  case_id: string;
  source_phase3_action: string;
  selected_forms: string[];
  generated_form_count: number;
  missing_fields: Record<string, string[]>;
  validation_status: "ready" | "needs_review";
  form_accuracy_pct: number;
  processing_time_min: number;
  generated_by: string;
  approved_by: string;
  created_at: string;
  generated_forms: Phase4GeneratedForm[];
};

function statusClass(tone: "green" | "yellow" | "red" | "blue" | "gray") {
  const classes = {
    blue: "border-blue-200 bg-blue-50 text-blue-700",
    gray: "border-gray-200 bg-gray-50 text-gray-700",
    green: "border-emerald-200 bg-emerald-50 text-emerald-700",
    red: "border-red-200 bg-red-50 text-red-700",
    yellow: "border-amber-200 bg-amber-50 text-amber-700",
  };
  return classes[tone];
}

function formatApiError(error: unknown, fallback: string) {
  if (!axios.isAxiosError(error)) {
    return fallback;
  }

  const detail = error.response?.data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object" && "msg" in item) {
          const location = "loc" in item && Array.isArray(item.loc) ? item.loc.join(".") : "field";
          return `${location}: ${String(item.msg)}`;
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }

  return fallback;
}

function formatCaseDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return new Intl.DateTimeFormat("en-PH", {
    day: "numeric",
    month: "long",
    timeZone: "Asia/Manila",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00+08:00`));
}

function formatDisplayValue(value: unknown, label = "") {
  const isDateField = label.trim().toLowerCase() === "dates";
  if (Array.isArray(value)) {
    return value.length
      ? value.map((item) => {
        if (typeof item !== "string") return String(item);
        if (isDateField) return formatCaseDate(item);
        return item.includes("_") ? formatDisplayLabel(item) : item;
      }).join(", ")
      : "None";
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (isDateField) return formatCaseDate(trimmed);
    return trimmed.includes("_") && /^\w+$/.test(trimmed) ? formatDisplayLabel(trimmed) : trimmed || "None";
  }
  if (value && typeof value === "object") {
    return Object.keys(value).length ? JSON.stringify(value) : "None";
  }
  return String(value ?? "None");
}

function hasMeaningfulValue(value: unknown) {
  if (Array.isArray(value)) return value.length > 0;
  if (value && typeof value === "object") return Object.keys(value).length > 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return Boolean(normalized && normalized !== "none" && normalized !== "unknown" && normalized !== "not detected");
  }
  return value !== null && value !== undefined;
}

function formatHearingSchedule(date: string, time: string) {
  if (!date) return "Date not set";
  const normalizedTime = time || "00:00";
  return formatPhilippineDateTime(`${date}T${normalizedTime}:00+08:00`);
}

function isFinalDecisionTrace(item: string) {
  return /^\s*Final Decision\s*:/i.test(item);
}

function isFiredRuleTrace(item: string) {
  return /\bFired\s*:/i.test(item) && !/\bNot Fired\s*:/i.test(item);
}

const SIMPLE_RULE_COPY: Record<string, { title: string; description: string }> = {
  "KP-COVER-01": {
    title: "KP Coverage",
    description: "The parties may use the barangay settlement process.",
  },
  "KP-DECISION-01": {
    title: "Mediation Route Clear",
    description: "No exclusion was found, so the case may proceed to mediation.",
  },
  "KP-VENUE-01": {
    title: "Venue Confirmed",
    description: "The parties meet the barangay residency requirement.",
  },
};

function simplifyFiredRule(item: string) {
  const match = item.match(/^\s*([A-Z0-9-]+)\s+Fired\s*:\s*(.*)$/i);
  const code = match?.[1]?.toUpperCase() ?? "KP Rule";
  const fallbackDescription = (match?.[2] ?? item)
    .replace(/\s*\[(?:R\.?A\.?|Republic Act)[^\]]*\]\s*\.?$/i, "")
    .replace(/\s+/g, " ")
    .trim();
  return SIMPLE_RULE_COPY[code] ?? {
    title: formatDisplayLabel(code.replace(/^KP-/, "")),
    description: fallbackDescription,
  };
}

function humanizeTechnicalText(value: string) {
  return value.replace(/\b[a-z0-9]+(?:_[a-z0-9]+)+\b/gi, (token) => formatDisplayLabel(token));
}

function formatSuggestionReason(value: string) {
  const categoryMatch = value.match(/dispute_category\s*=\s*([a-z0-9_]+)/i);
  if (categoryMatch) {
    return `Matches the ${formatDisplayLabel(categoryMatch[1])} case category.`;
  }
  return humanizeTechnicalText(value);
}

function SectionCard({ title, icon: Icon, children, tone = "blue" }: { title: string; icon: LucideIcon; children: ReactNode; tone?: "blue" | "green" | "yellow" | "red" | "gray" }) {
  const iconColors = {
    blue: "text-blue-600",
    gray: "text-gray-600",
    green: "text-emerald-600",
    red: "text-red-600",
    yellow: "text-amber-600",
  };
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="flex items-center gap-2 text-lg font-black text-gray-950">
        <Icon className={iconColors[tone]} size={20} />
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function StatusBadge({ label, tone }: { label: string; tone: "green" | "yellow" | "red" | "blue" | "gray" }) {
  return <span className={`inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-black ${statusClass(tone)}`}>{humanizeDisplayText(label)}</span>;
}

function FieldList({ items, columns = "sm:grid-cols-2" }: { items: Array<[string, unknown]>; columns?: string }) {
  return (
    <div className={`grid gap-3 ${columns}`}>
      {items.map(([label, value]) => (
        <div className="rounded-md border border-gray-200 bg-gray-50 p-3" key={label}>
          <p className="text-xs font-black uppercase tracking-wide text-gray-500">{formatDisplayLabel(label)}</p>
          <p className="mt-2 break-words text-sm font-bold text-gray-900">{formatDisplayValue(value, label)}</p>
        </div>
      ))}
    </div>
  );
}

export function SensitiveRoutingCard({ route }: { route: Phase3Route | null }) {
  if (!route) {
    return (
      <SectionCard title="Sensitive Case Routing" icon={ShieldAlert} tone="gray">
        <p className="text-sm font-bold text-gray-600">Run Phase 3 processing to generate routing.</p>
      </SectionCard>
    );
  }
  const tone = route.blocking_mediation ? "red" : "green";
  return (
    <SectionCard title="Sensitive Case Routing" icon={ShieldAlert} tone={tone}>
      <div className="-mt-2 mb-5 flex flex-wrap gap-2">
        <StatusBadge label={route.is_sensitive ? "Sensitive" : "Not sensitive"} tone={tone} />
        <StatusBadge label={route.sensitive_category} tone={route.sensitive_category === "None" ? "gray" : tone} />
        <StatusBadge label={route.confidence_level} tone="blue" />
      </div>
      <FieldList
        items={[
          ["Recommended Route", route.recommended_route],
          ["Blocking Mediation", route.blocking_mediation ? "Yes" : "No"],
          ["Reason", route.reason],
          ["Matched Keywords", route.matched_keywords],
        ]}
      />
    </SectionCard>
  );
}

export function MediationEligibilityCard({ eligibility }: { eligibility: MediationEligibility | null }) {
  if (!eligibility) {
    return (
      <SectionCard title="Mediation Eligibility" icon={Gavel} tone="gray">
        <p className="text-sm font-bold text-gray-600">No eligibility result yet.</p>
      </SectionCard>
    );
  }
  return (
    <SectionCard title="Mediation Eligibility" icon={Gavel} tone={eligibility.eligible_for_mediation ? "green" : "yellow"}>
      <div className="flex flex-wrap gap-2">
        <StatusBadge label={eligibility.eligible_for_mediation ? "Eligible" : "Not eligible"} tone={eligibility.eligible_for_mediation ? "green" : "yellow"} />
        <StatusBadge label={eligibility.required_action} tone="blue" />
      </div>
      <p className="mt-4 text-sm font-bold leading-6 text-gray-700">{eligibility.reason}</p>
    </SectionCard>
  );
}

export function MediationSuggestionsPanel({ suggestions }: { suggestions: MediationSuggestions | null }) {
  const explanations = suggestions
    ? Array.from(new Set([
      ...suggestions.suggestions_json.map((item) => formatSuggestionReason(item.why_suggested)),
      ...suggestions.xai_explanation_json.map(formatSuggestionReason),
    ]))
    : [];

  return (
    <SectionCard title="Mediation Suggestions" icon={UsersRound} tone={suggestions?.suggestions_json.length ? "green" : "gray"}>
      {!suggestions?.suggestions_json.length ? (
        <p className="text-sm font-bold text-gray-600">No mediation suggestions were generated for this case.</p>
      ) : (
        <div>
          <div className="grid gap-3 lg:grid-cols-3">
            {suggestions.suggestions_json.map((item) => (
            <article className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-4" key={item.title}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-black text-emerald-950">{humanizeTechnicalText(item.title)}</h3>
                <StatusBadge label={`${formatDisplayLabel(item.risk_level)} risk`} tone={item.risk_level === "high" ? "red" : item.risk_level === "medium" ? "yellow" : "green"} />
              </div>
              <p className="mt-2 text-sm leading-5 text-gray-700">{humanizeTechnicalText(item.description)}</p>
              <p className="mt-4 text-xs font-black uppercase tracking-wide text-emerald-700">Recommended Terms</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {item.recommended_terms.map((term) => (
                  <span className="rounded-md border border-emerald-200 bg-white px-2 py-1 text-xs font-bold text-emerald-900" key={term}>
                    {humanizeTechnicalText(term)}
                  </span>
                ))}
              </div>
            </article>
            ))}
          </div>
          <div className="mt-4 rounded-lg border-2 border-blue-200 bg-blue-50 p-4 text-blue-950">
            <p className="text-xs font-black uppercase tracking-wide text-blue-700">Why these suggestions</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {explanations.map((explanation) => (
                <span className="inline-flex items-center gap-2 rounded-md bg-white px-3 py-2 text-sm font-bold" key={explanation}>
                  <CheckCircle2 className="shrink-0 text-blue-600" size={15} />
                  {explanation}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

export function ReferralPanel({
  referrals,
  officialDecision,
  onRefresh,
  onWorkflowAction,
}: {
  referrals: ReferralRecord[];
  officialDecision: OfficialDecision | null;
  onRefresh: () => void | Promise<void>;
  onWorkflowAction?: ReferralWorkflowActionHandler;
}) {
  const [activeAction, setActiveAction] = useState<{ referralId: number; action: ReferralWorkflowAction } | null>(null);
  const [feedbackByReferral, setFeedbackByReferral] = useState<Record<number, { message: string; tone: "green" | "red" }>>({});

  const runWorkflowAction = async (referralId: number, action: ReferralWorkflowAction, reason = "") => {
    if (!onWorkflowAction || activeAction) {
      return;
    }

    setActiveAction({ referralId, action });
    setFeedbackByReferral((current) => {
      const next = { ...current };
      delete next[referralId];
      return next;
    });

    try {
      const result = await onWorkflowAction(referralId, action, reason);
      await onRefresh();
      setFeedbackByReferral((current) => ({
        ...current,
        [referralId]: { message: result.message || "Referral workflow updated.", tone: "green" },
      }));
    } catch (error) {
      const fallback = action === "cancel_referral" ? "The referral record could not be cancelled." : "The referral could not be completed.";
      const message = error instanceof Error ? error.message : formatApiError(error, fallback);
      setFeedbackByReferral((current) => ({ ...current, [referralId]: { message, tone: "red" } }));
    } finally {
      setActiveAction(null);
    }
  };

  return (
    <SectionCard title="Referral Records" icon={Route} tone={referrals.length ? "red" : "gray"}>
      {!referrals.length ? (
        <p className="text-sm font-bold text-gray-600">No referral records yet.</p>
      ) : (
        <div className="space-y-3">
          {referrals.map((referral) => {
            const firedRules = referral.xai_reference.filter(isFiredRuleTrace);
            const isCompleting = activeAction?.referralId === referral.id && activeAction.action === "complete_and_advance";
            const isCancelling = activeAction?.referralId === referral.id && activeAction.action === "cancel_referral";
            const feedback = feedbackByReferral[referral.id];
            const statusLabel = referral.status.charAt(0).toUpperCase() + referral.status.slice(1);
            const statusTone = referral.status === "completed" ? "green" : referral.status === "cancelled" ? "red" : "yellow";
            const statusPanelClass = referral.status === "completed"
              ? "border-emerald-300 bg-emerald-50 text-emerald-900"
              : referral.status === "cancelled"
                ? "border-red-300 bg-red-50 text-red-900"
                : "border-amber-300 bg-amber-50 text-amber-900";

            return (
            <article className="rounded-lg border border-gray-200 bg-gray-50 p-4" key={referral.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-black text-gray-950">{referral.referral_type}</p>
                  <p className="mt-1 text-sm font-bold text-gray-600">{referral.destination}</p>
                </div>
                <StatusBadge label={statusLabel} tone={statusTone} />
              </div>
              <p className="mt-3 text-sm leading-6 text-gray-700">{referral.reason}</p>
              <p className="mt-2 text-xs font-bold text-red-700">Matched: {referral.matched_keywords.join(", ") || "None"}</p>
              <details className="mt-3">
                <summary className="cursor-pointer text-xs font-black text-blue-700">View Fired KP Rules</summary>
                <ul className="mt-2 space-y-2 text-xs font-bold leading-5 text-gray-700">
                  {firedRules.map((item) => (
                    <li className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2" key={item}>
                      <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-700" size={14} />
                      <span>{item}</span>
                    </li>
                  ))}
                  {!firedRules.length && <li className="text-gray-500">No fired KP rule was recorded.</li>}
                </ul>
              </details>
              <div className={`mt-4 rounded-lg border-2 p-4 ${statusPanelClass}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-black uppercase tracking-wider">Referral status</p>
                    <p className="mt-1 text-lg font-black">{statusLabel}</p>
                  </div>
                  {referral.status === "completed" ? <CheckCircle2 size={26} /> : referral.status === "cancelled" ? <XCircle size={26} /> : <Route size={26} />}
                </div>
                {officialDecision && (
                  <div className="mt-3 rounded-md border border-current/20 bg-white/80 px-3 py-2 text-xs leading-5">
                    <p className="font-black uppercase tracking-wide">Official decision</p>
                    <p className="mt-1 font-bold">{officialDecision.official_decision}</p>
                    <p className="mt-1">Approved by {officialDecision.approved_by} on {formatPhilippineDateTime(officialDecision.approved_at)}</p>
                  </div>
                )}
                {referral.status === "pending" && onWorkflowAction ? (
                  <div className="mt-4 rounded-md border border-gray-200 bg-white p-4 text-gray-800">
                    <p className="text-xs font-black uppercase tracking-wide text-gray-600">Official workflow actions</p>
                    <p className="mt-1 text-xs leading-5 text-gray-600">
                      Mark the referral completed after it has been handled through the official local process, or cancel this referral record if it should no longer be used.
                    </p>
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        className="inline-flex min-h-11 items-center gap-2 rounded-md bg-emerald-600 px-4 text-sm font-black text-white shadow-md transition hover:bg-emerald-700 focus:ring-4 focus:ring-emerald-200 disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={Boolean(activeAction)}
                        onClick={() => runWorkflowAction(referral.id, "complete_and_advance")}
                        type="button"
                      >
                        <CheckCircle2 size={17} />
                        {isCompleting ? "Saving..." : "Mark Referral Completed"}
                      </button>
                      <button
                        className="inline-flex min-h-11 items-center gap-2 rounded-md bg-red-600 px-4 text-sm font-black text-white shadow-md transition hover:bg-red-700 focus:ring-4 focus:ring-red-200 disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={Boolean(activeAction)}
                        onClick={() => {
                          if (window.confirm("Cancel this referral record? This will not cancel the case or change the KP decision.")) {
                            runWorkflowAction(referral.id, "cancel_referral");
                          }
                        }}
                        type="button"
                      >
                        <XCircle size={17} />
                        {isCancelling ? "Cancelling..." : "Cancel Referral Record"}
                      </button>
                    </div>
                  </div>
                ) : referral.status === "completed" ? (
                  <div className="mt-4 flex items-start gap-3 rounded-md border border-emerald-300 bg-white/80 p-4 text-emerald-900" role="status">
                    <CheckCircle2 className="mt-0.5 shrink-0" size={20} />
                    <div>
                      <p className="font-black">Referral Completed</p>
                      <p className="mt-1 text-xs font-bold leading-5">This referral is recorded as completed. No further referral action is needed.</p>
                    </div>
                  </div>
                ) : referral.status === "cancelled" ? (
                  <div className="mt-4 flex items-start gap-3 rounded-md border border-red-300 bg-white/80 p-4 text-red-900" role="status">
                    <XCircle className="mt-0.5 shrink-0" size={20} />
                    <div>
                      <p className="font-black">Referral Record Cancelled</p>
                      <p className="mt-1 text-xs font-bold leading-5">Only this referral record was cancelled. The case and KP decision were not cancelled.</p>
                    </div>
                  </div>
                ) : (
                  <p className="mt-3 text-xs font-bold leading-5">This is a read-only referral record. Open its active workflow to perform an official action.</p>
                )}
                {feedback && (
                  <p className={`mt-3 rounded-md border px-3 py-2 text-xs font-bold ${statusClass(feedback.tone)}`} role="status">
                    {feedback.message}
                  </p>
                )}
              </div>
            </article>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

export function HearingScheduler({ caseId, onRefresh }: { caseId: string; onRefresh: () => void }) {
  const [form, setForm] = useState({
    hearing_type: "initial",
    scheduled_date: "",
    scheduled_time: "09:00",
    location: "Barangay Hall",
    assigned_lupon_member: "",
  });
  const [message, setMessage] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/phase3/hearings`, { ...form, case_id: caseId, status: "scheduled", notes: "" });
      setMessage("Hearing schedule saved.");
      onRefresh();
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setMessage(detail ?? "Unable to save hearing schedule.");
    }
  };

  return (
    <form className="rounded-lg border border-blue-100 bg-blue-50/40 p-4" onSubmit={submit}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1.15fr_1fr_1fr_1.25fr_1.15fr]">
        <label className="text-sm font-bold text-gray-700">
          Hearing Type
          <select className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3 shadow-sm" onChange={(event) => setForm({ ...form, hearing_type: event.target.value })} value={form.hearing_type}>
            <option value="initial">Initial</option>
            <option value="mediation">Mediation</option>
            <option value="follow_up">Follow-up</option>
            <option value="final">Final</option>
          </select>
        </label>
        <label className="text-sm font-bold text-gray-700">Date<input className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3 shadow-sm" onChange={(event) => setForm({ ...form, scheduled_date: event.target.value })} required type="date" value={form.scheduled_date} /></label>
        <label className="text-sm font-bold text-gray-700">Time<input className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3 shadow-sm" onChange={(event) => setForm({ ...form, scheduled_time: event.target.value })} required type="time" value={form.scheduled_time} /></label>
        <label className="text-sm font-bold text-gray-700">Location<input className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3 shadow-sm" onChange={(event) => setForm({ ...form, location: event.target.value })} required value={form.location} /></label>
        <label className="text-sm font-bold text-gray-700">Lupon Member<input className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3 shadow-sm" onChange={(event) => setForm({ ...form, assigned_lupon_member: event.target.value })} required value={form.assigned_lupon_member} /></label>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button className="inline-flex h-10 items-center gap-2 rounded-md bg-blue-600 px-5 text-sm font-black text-white shadow-sm transition hover:bg-blue-700 focus:ring-4 focus:ring-blue-200" type="submit">
          <CalendarDays size={16} />
          Schedule Hearing
        </button>
        {message && <p className="rounded-md border border-blue-100 bg-white px-3 py-2 text-sm font-bold text-blue-800" role="status">{message}</p>}
      </div>
    </form>
  );
}

export function HearingTimeline({ hearings, onRefresh }: { hearings: HearingRecord[]; onRefresh: () => void }) {
  const [updating, setUpdating] = useState<{ id: number; status: HearingRecord["status"] } | null>(null);
  const [message, setMessage] = useState("");

  const update = async (id: number, status: HearingRecord["status"]) => {
    setUpdating({ id, status });
    setMessage("");
    try {
      await axios.patch(`${API_BASE_URL}/api/phase3/hearings/${id}`, { status });
      setMessage(
        status === "completed"
          ? "Hearing marked as completed."
          : status === "missed"
            ? "Hearing marked as missed."
            : "Hearing schedule cancelled.",
      );
      onRefresh();
    } catch (error) {
      setMessage(formatApiError(error, "Unable to update the hearing status."));
    } finally {
      setUpdating(null);
    }
  };

  return (
    <div className="space-y-3">
      {message && <p className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm font-bold text-blue-800" role="status">{message}</p>}
      {!hearings.length && <p className="text-sm font-bold text-gray-600">No hearings scheduled.</p>}
      {hearings.map((hearing) => (
        <article className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm" key={hearing.id}>
          <div className="p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-black text-gray-950">{formatDisplayLabel(hearing.hearing_type)} Hearing</p>
              <p className="mt-1 text-sm font-bold text-gray-700">{formatHearingSchedule(hearing.scheduled_date, hearing.scheduled_time)}</p>
              <p className="mt-1 text-xs font-bold text-gray-500">{hearing.location} · Lupon Member: {hearing.assigned_lupon_member || "Not assigned"}</p>
            </div>
            <StatusBadge label={formatDisplayLabel(hearing.status)} tone={hearing.status === "completed" ? "green" : hearing.status === "cancelled" ? "gray" : hearing.status === "missed" ? "red" : "blue"} />
          </div>
          </div>
          <div className="border-t border-gray-100 bg-gray-50 px-4 py-3">
            <p className="text-xs font-black uppercase tracking-wide text-gray-600">Update hearing result</p>
            <p className="mt-1 text-xs leading-5 text-gray-500">Choose what happened to this scheduled hearing. You can correct the result later if needed.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button aria-label="Mark hearing as completed" className="inline-flex min-h-10 items-center gap-2 rounded-md bg-emerald-600 px-4 text-xs font-black text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={Boolean(updating) || hearing.status === "completed"} onClick={() => update(hearing.id, "completed")} title="The scheduled hearing took place" type="button">
                <CheckCircle2 size={16} />
                {updating?.id === hearing.id && updating.status === "completed" ? "Updating..." : "Mark Completed"}
              </button>
              <button aria-label="Mark hearing as missed" className="inline-flex min-h-10 items-center gap-2 rounded-md bg-red-600 px-4 text-xs font-black text-white shadow-sm transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={Boolean(updating) || hearing.status === "missed"} onClick={() => update(hearing.id, "missed")} title="The scheduled hearing was not attended" type="button">
                <AlertTriangle size={16} />
                {updating?.id === hearing.id && updating.status === "missed" ? "Updating..." : "Mark Missed"}
              </button>
              <button aria-label="Cancel hearing schedule" className="inline-flex min-h-10 items-center gap-2 rounded-md border border-gray-300 bg-white px-4 text-xs font-black text-gray-700 shadow-sm transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50" disabled={Boolean(updating) || hearing.status === "cancelled"} onClick={() => update(hearing.id, "cancelled")} title="This hearing will not proceed as scheduled" type="button">
                <XCircle size={16} />
                {updating?.id === hearing.id && updating.status === "cancelled" ? "Cancelling..." : "Cancel Schedule"}
              </button>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

export function EvidenceUploadPanel({ caseId, onRefresh }: { caseId: string; onRefresh: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");

  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (!file) {
      setMessage("Choose a file first.");
      return;
    }
    const data = new FormData();
    data.append("file", file);
    data.append("evidence_text", "");
    try {
      await axios.post(`${API_BASE_URL}/api/phase3/evidence/upload/${caseId}`, data, { headers: { "Content-Type": "multipart/form-data" } });
      setFile(null);
      setMessage("Evidence uploaded.");
      onRefresh();
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setMessage(detail ?? "Evidence upload failed.");
    }
  };

  return (
    <form className="rounded-lg border border-blue-100 bg-blue-50/40 p-4" onSubmit={upload}>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
      <label className="block min-w-0 text-sm font-bold text-gray-700">
        Evidence File
        <input accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.doc,.docx" className="mt-2 block w-full min-w-0 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" />
      </label>
        <button className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-blue-600 px-5 text-sm font-black text-white shadow-sm transition hover:bg-blue-700 focus:ring-4 focus:ring-blue-200" type="submit">
          <UploadCloud size={16} />
          Upload Evidence
        </button>
      </div>
      {message && <p className="mt-3 rounded-md border border-blue-100 bg-white px-3 py-2 text-sm font-bold text-blue-800" role="status">{message}</p>}
    </form>
  );
}

export function EvidenceFileList({ evidence }: { evidence: EvidenceRecord[] }) {
  return (
    <div className="space-y-3">
      {!evidence.length && <p className="text-sm font-bold text-gray-600">No evidence uploaded.</p>}
      {evidence.map((item) => (
        <article className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" key={item.id}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="grid size-10 shrink-0 place-items-center rounded-md bg-blue-50 text-blue-700">
                <FileCheck2 size={18} />
              </div>
              <div className="min-w-0">
                <p className="truncate font-black text-gray-950" title={item.file_name}>{item.file_name}</p>
                <p className="mt-1 text-xs font-bold text-gray-500">{item.file_type.toUpperCase()} · {formatPhilippineDateTime(item.uploaded_at)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <StatusBadge label="Uploaded" tone="green" />
              <a className="inline-flex min-h-9 items-center gap-2 rounded-md border border-blue-200 bg-white px-3 text-xs font-black text-blue-700 transition hover:bg-blue-50" download={item.file_name} href={`${API_BASE_URL}/api/phase3/evidence/${item.id}/download`}>
                <Download size={14} />
                Download
              </a>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

export function EmotionTensionCard({ emotion }: { emotion: EmotionAnalysis | null }) {
  if (!emotion) {
    return (
      <SectionCard title="Emotion and Tension" icon={Brain} tone="gray">
        <p className="text-sm font-bold text-gray-600">No emotion analysis yet.</p>
      </SectionCard>
    );
  }
  const tone = emotion.emotion_label === "aggressive" || emotion.emotion_label === "angry" ? "red" : emotion.emotion_label === "sad" ? "yellow" : "green";
  const detectedTerms = emotion.detected_terms.filter(Boolean);
  return (
    <SectionCard title="Emotion & Tension" icon={Brain} tone={tone}>
      <div className="grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <p className="text-xs font-black uppercase tracking-wide text-gray-500">Analysis Summary</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <StatusBadge label={formatDisplayLabel(emotion.emotion_label)} tone={tone} />
            <StatusBadge label={`Tension Score ${emotion.tension_score}`} tone="blue" />
          </div>
          <p className="mt-3 text-sm font-bold leading-6 text-gray-700">
            {detectedTerms.length ? `Detected terms: ${detectedTerms.join(", ")}` : "No emotional trigger terms were detected."}
          </p>
        </div>
        <div className="rounded-lg border border-blue-100 bg-blue-50 p-4">
          <p className="text-xs font-black uppercase tracking-wide text-blue-700">Mediation Guidance</p>
          <p className="mt-3 text-sm font-bold leading-6 text-blue-950">{emotion.mediation_advice}</p>
        </div>
      </div>
    </SectionCard>
  );
}

function PreprocessingNerCard({ dashboard }: { dashboard: Phase3Dashboard }) {
  const entities = Object.entries(dashboard.phase2.extracted_entities ?? {});
  const detectedEntities = entities.filter(([, value]) => hasMeaningfulValue(value));
  const omittedEntityCount = entities.length - detectedEntities.length;
  const keywords = dashboard.phase2.detected_keywords.detected_keywords ?? [];
  const isProtectedCaseTrigger = Boolean(dashboard.phase2.detected_keywords.vawc_trigger);

  return (
    <SectionCard title="Analysis Results" icon={Brain} tone="blue">
      <div className={`rounded-lg border p-4 ${isProtectedCaseTrigger ? "border-red-200 bg-red-50" : "border-blue-100 bg-blue-50"}`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className={`text-xs font-black uppercase tracking-wide ${isProtectedCaseTrigger ? "text-red-700" : "text-blue-700"}`}>Legal Keyword Review</p>
            {keywords.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {keywords.map((keyword) => <StatusBadge key={keyword} label={formatDisplayLabel(keyword)} tone={isProtectedCaseTrigger ? "red" : "blue"} />)}
              </div>
            ) : (
              <p className="mt-2 text-sm font-bold text-gray-700">No legal keywords were detected.</p>
            )}
          </div>
          <StatusBadge label={isProtectedCaseTrigger ? "Protected-case trigger detected" : "No protected-case trigger"} tone={isProtectedCaseTrigger ? "red" : "green"} />
        </div>
        {isProtectedCaseTrigger && (
          <p className="mt-3 text-sm font-bold text-red-900">VAWC-sensitive language requires the protected referral route.</p>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs font-black uppercase tracking-wide text-gray-500">Named Entities</p>
        {omittedEntityCount > 0 && <span className="text-xs font-bold text-gray-500">{omittedEntityCount} empty {omittedEntityCount === 1 ? "category" : "categories"} hidden</span>}
      </div>
      {detectedEntities.length ? (
        <div className="mt-3">
          <FieldList columns="sm:grid-cols-2 lg:grid-cols-3" items={detectedEntities} />
        </div>
      ) : (
        <p className="mt-3 rounded-md border border-dashed border-gray-300 bg-gray-50 p-4 text-sm font-bold text-gray-600">No named entities were extracted from this transcript.</p>
      )}
    </SectionCard>
  );
}

function ExplainableTraceCard({ dashboard }: { dashboard: Phase3Dashboard }) {
  const relevantTrace = dashboard.phase2.xai_trace.filter((item) => {
    return isFiredRuleTrace(item) || isFinalDecisionTrace(item);
  });
  const firedRules = relevantTrace.filter(isFiredRuleTrace).map((item) => ({
    ...simplifyFiredRule(item),
    source: item,
  }));
  const finalDecision = relevantTrace
    .find(isFinalDecisionTrace)
    ?.replace(/^\s*Final Decision\s*:\s*/i, "");

  return (
    <SectionCard title="Matched KP Rules" icon={Route} tone="blue">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-gray-600">Only the rules used for this routing result are shown.</p>
        {firedRules.length > 0 && <StatusBadge label={`${firedRules.length} matched`} tone="green" />}
      </div>
      {firedRules.length > 0 ? (
        <ul className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {firedRules.map((rule) => (
            <li className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-950" key={rule.source}>
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />
              <div>
                <p className="font-black">{rule.title}</p>
                <p className="mt-1 text-sm leading-5 text-emerald-900">{rule.description}</p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-600">
          No matched KP rule is available yet.
        </p>
      )}
      {finalDecision && (
        <div className="mt-4 flex items-start gap-3 rounded-lg border-2 border-blue-300 bg-blue-50 px-4 py-3 text-blue-950">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-blue-700" />
          <div>
            <p className="text-xs font-black uppercase tracking-wide text-blue-700">Routing Decision</p>
            <p className="mt-1 text-sm font-bold leading-5">{finalDecision}</p>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function Phase4FormsPanel({ caseId }: { caseId: string }) {
  const [recommendation, setRecommendation] = useState<Phase4Recommendation | null>(null);
  const [packets, setPackets] = useState<Phase4Packet[]>([]);
  const [selectedForms, setSelectedForms] = useState<Record<string, boolean>>({});
  const [fieldOverrides, setFieldOverrides] = useState<Record<string, string>>({});
  const [generatedBy, setGeneratedBy] = useState("Barangay Official");
  const [approvedBy, setApprovedBy] = useState("");
  const [message, setMessage] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  const allForms = useMemo(() => {
    if (!recommendation) {
      return [];
    }
    return [...recommendation.recommended_forms, ...recommendation.optional_forms];
  }, [recommendation]);

  const missingFields = useMemo(() => {
    if (!recommendation) {
      return [];
    }
    return Array.from(new Set(Object.values(recommendation.missing_fields).flat()));
  }, [recommendation]);

  const loadPhase4 = async () => {
    const [recommendationResponse, packetsResponse] = await Promise.all([
      axios.get<Phase4Recommendation>(`${API_BASE_URL}/api/phase4/recommendations/${caseId}`),
      axios.get<Phase4Packet[]>(`${API_BASE_URL}/api/phase4/packets/${caseId}`),
    ]);
    setRecommendation(recommendationResponse.data);
    setPackets(packetsResponse.data);
    setSelectedForms((current) => {
      if (Object.keys(current).length) {
        return current;
      }
      return Object.fromEntries(recommendationResponse.data.recommended_forms.map((form) => [form.form_id, true]));
    });
  };

  const toggleForm = (formId: string) => {
    setSelectedForms((current) => ({ ...current, [formId]: !current[formId] }));
  };

  const generatePacket = async () => {
    const form_ids = Object.entries(selectedForms).filter(([, selected]) => selected).map(([formId]) => formId);
    if (!form_ids.length) {
      setMessage("Choose at least one KP form.");
      return;
    }
    setIsGenerating(true);
    setMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/phase4/generate-packet/${caseId}`, {
        form_ids,
        generated_by: generatedBy,
        approved_by: approvedBy,
        field_overrides: fieldOverrides,
      });
      setMessage("Phase 4 document packet generated.");
      await loadPhase4();
    } catch (error) {
      setMessage(formatApiError(error, "Unable to generate Phase 4 packet."));
    } finally {
      setIsGenerating(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadPhase4().catch((error) => setMessage(formatApiError(error, "Run Phase 3 processing before generating Phase 4 forms.")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  return (
    <SectionCard title="Phase 4 KP Forms Packet" icon={ClipboardList} tone="blue">
      <p className="mb-4 text-sm font-bold text-gray-600">Downloads contain the original blank KP forms. Print and fill them in manually. Case data completeness does not mean the PDF fields are filled.</p>
      {!recommendation ? (
        <p className="text-sm font-bold text-gray-600">No Phase 4 recommendation loaded.</p>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={recommendation.final_recommended_action} tone="blue" />
            <StatusBadge label={`${recommendation.form_accuracy_pct}% case data complete`} tone={recommendation.validation_status === "ready" ? "green" : "yellow"} />
            <StatusBadge label={recommendation.validation_status === "ready" ? "Ready" : "Needs review"} tone={recommendation.validation_status === "ready" ? "green" : "yellow"} />
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {allForms.map((form) => {
              const missing = recommendation.missing_fields[form.form_id] || [];
              return (
                <label className="block rounded-md border border-gray-200 bg-gray-50 p-4" key={form.form_id}>
                  <div className="flex items-start gap-3">
                    <input className="mt-1 size-4 accent-blue-600" checked={Boolean(selectedForms[form.form_id])} onChange={() => toggleForm(form.form_id)} type="checkbox" />
                    <div className="min-w-0">
                      <p className="font-black text-gray-950">{form.title}</p>
                      <p className="mt-1 text-xs font-bold uppercase tracking-wide text-gray-500">{form.stage}</p>
                      <p className="mt-2 text-sm leading-5 text-gray-700">{form.purpose}</p>
                      <p className="mt-2 text-xs font-bold text-amber-700">Missing: {missing.join(", ") || "None"}</p>
                    </div>
                  </div>
                </label>
              );
            })}
          </div>

          {missingFields.length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-black text-amber-800">Missing Field Overrides</p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {missingFields.map((field) => (
                  <label className="text-sm font-bold text-gray-700" key={field}>
                    {field.replaceAll("_", " ")}
                    <input className="mt-2 h-10 w-full rounded-md border border-amber-200 bg-white px-3" onChange={(event) => setFieldOverrides({ ...fieldOverrides, [field]: event.target.value })} value={fieldOverrides[field] || ""} />
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm font-bold text-gray-700">
              Generated By
              <input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" onChange={(event) => setGeneratedBy(event.target.value)} value={generatedBy} />
            </label>
            <label className="text-sm font-bold text-gray-700">
              Approved By
              <input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" onChange={(event) => setApprovedBy(event.target.value)} value={approvedBy} />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button className="inline-flex h-10 items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-500" disabled={isGenerating} onClick={generatePacket} type="button">
              <FileCheck2 size={16} />
              {isGenerating ? "Generating..." : "Generate Packet"}
            </button>
            {message && <p className="text-sm font-bold text-gray-600">{message}</p>}
          </div>

          <div className="space-y-3">
            <p className="text-sm font-black text-gray-950">Generated Packets</p>
            {!packets.length && <p className="text-sm font-bold text-gray-600">No Phase 4 packets generated yet.</p>}
            {packets.map((packet) => (
              <article className="rounded-md border border-gray-200 bg-white p-4" key={packet.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-black text-gray-950">Packet #{packet.id}</p>
                    <p className="mt-1 text-xs font-bold text-gray-500">
                      {packet.generated_form_count} blank forms, {packet.form_accuracy_pct}% case data complete, generated {formatPhilippineDateTime(packet.created_at)}
                    </p>
                  </div>
                  <StatusBadge label={packet.validation_status === "ready" ? "Ready" : "Needs review"} tone={packet.validation_status === "ready" ? "green" : "yellow"} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {packet.generated_forms.map((form) => (
                    <a className="inline-flex h-9 items-center gap-2 rounded-md border border-blue-200 px-3 text-xs font-black text-blue-700 hover:bg-blue-50" href={`${API_BASE_URL}${form.download_url}`} key={form.id} rel="noreferrer" target="_blank">
                      <Download size={14} />
                      {form.title}
                    </a>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

export default function Phase3DashboardPage({
  embedded = false,
  initialCaseId = "",
  onReferralWorkflowAction,
  view = "all",
}: {
  embedded?: boolean;
  initialCaseId?: string;
  onReferralWorkflowAction?: ReferralWorkflowActionHandler;
  view?: Phase3DashboardView;
}) {
  const [cases, setCases] = useState<CaseAnalysisSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState(initialCaseId);
  const [dashboard, setDashboard] = useState<Phase3Dashboard | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState("");

  const selectedCase = useMemo(() => cases.find((item) => item.case_id === selectedCaseId), [cases, selectedCaseId]);

  const loadCases = async () => {
    const response = await axios.get<CaseAnalysisSummary[]>(`${API_BASE_URL}/case-analyses`);
    setCases(response.data);
    if (initialCaseId && response.data.some((item) => item.case_id === initialCaseId)) {
      setSelectedCaseId(initialCaseId);
      return;
    }
    if (!selectedCaseId && response.data[0]?.case_id) {
      setSelectedCaseId(response.data[0].case_id);
    }
  };

  const loadDashboard = async (caseId = selectedCaseId) => {
    if (!caseId) {
      return;
    }
    setIsLoading(true);
    setMessage("");
    try {
      const response = await axios.get<Phase3Dashboard>(`${API_BASE_URL}/api/phase3/dashboard/${caseId}`);
      setDashboard(response.data);
    } catch {
      setDashboard(null);
      setMessage("Phase 2 case is saved. Click Run Phase 3 to generate the decision dashboard.");
    } finally {
      setIsLoading(false);
    }
  };

  const processCase = async () => {
    if (!selectedCaseId) {
      setMessage("Save a Phase 2 case analysis before running Phase 3.");
      return;
    }
    setIsLoading(true);
    setMessage("");
    try {
      const response = await axios.post<Phase3Dashboard>(`${API_BASE_URL}/api/phase3/process-case/${selectedCaseId}`);
      setDashboard(response.data);
      setMessage("Phase 3 processing completed.");
    } catch (error) {
      setMessage(formatApiError(error, "Phase 3 processing failed."));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCases().catch(() => setMessage("Unable to load saved Phase 2 case analyses."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialCaseId]);

  useEffect(() => {
    if (selectedCaseId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadDashboard(selectedCaseId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId]);

  const viewCopy = {
    all: ["Decision Support", "Workflow Outputs", "Sensitive routing, mediation, evidence, hearings, and generated KP forms connected to the saved case."],
    preparation: ["Workflow Stage 2 of 4", "Summons & Proof", "Schedule the hearing and attach supporting evidence to this case."],
    analysis: ["Analysis & Routing", "NER & Emotion Results", "Review named entities, legal keywords, emotion, and tension indicators."],
    routing: ["Analysis & Routing", "Decision Routing", "Review the applied rules, protected-case route, mediation eligibility, and referral record."],
    mediation: ["Resolution & Forms", "Mediation Guidance", "Review mediation suggestions before generating the official KP forms."],
  } satisfies Record<Phase3DashboardView, [string, string, string]>;
  const [eyebrow, title, description] = viewCopy[view];
  const showViewHeader = !embedded || view === "all" || view === "preparation";
  const containerSpacing = embedded && !showViewHeader ? "space-y-4" : "space-y-6";

  return (
    <div className={`${embedded ? containerSpacing : "page-enter mx-auto max-w-7xl space-y-6"}`}>
      {showViewHeader && (
      <section className={`rounded-lg border border-gray-200 bg-white shadow-sm ${embedded && view === "preparation" ? "p-4 sm:p-5" : "p-5 sm:p-6"}`}>
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="text-sm font-black uppercase tracking-wide text-blue-700">{eyebrow}</p>
            <h1 className="mt-1 text-2xl font-black text-gray-950">{title}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
              {description}
            </p>
          </div>
          {view === "all" && <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <select className="h-11 min-w-64 rounded-md border border-gray-300 bg-white px-3 text-sm font-bold" onChange={(event) => setSelectedCaseId(event.target.value)} value={selectedCaseId}>
              <option value="">Select saved Phase 2 case</option>
              {cases.map((item) => (
                <option key={item.id} value={item.case_id}>
                  {item.case_id} - {item.barangay_name || "No barangay"}
                </option>
              ))}
            </select>
            <button className="inline-flex h-11 items-center justify-center gap-2 rounded-md border border-gray-300 px-4 text-sm font-black text-gray-900 hover:bg-gray-50" onClick={() => loadDashboard()} type="button">
              <RefreshCw size={16} />
              Refresh
            </button>
            <button className="inline-flex h-11 items-center justify-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-black text-white hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-500" disabled={!selectedCaseId || isLoading} onClick={processCase} type="button">
              <Brain size={16} />
              {isLoading ? "Processing..." : "Run Phase 3"}
            </button>
          </div>}
        </div>
        {message && <p className="mt-4 rounded-md border border-blue-100 bg-blue-50 p-3 text-sm font-bold text-blue-800">{message}</p>}
        {selectedCase && (
          <p className="mt-4 text-xs font-bold text-gray-500">
            Case source: Analysis #{selectedCase.id} · Jurisdiction: {formatDisplayLabel(selectedCase.jurisdiction_decision) || "Not Available"} · Saved {formatPhilippineDateTime(selectedCase.created_at)}
          </p>
        )}
      </section>
      )}

      {!dashboard ? (
        <section className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center shadow-sm">
          <Eye className="mx-auto text-gray-400" size={34} />
          <h2 className="mt-4 text-lg font-black text-gray-950">No Phase 3 dashboard loaded</h2>
          <p className="mt-2 text-sm leading-6 text-gray-600">Select a saved Phase 2 case analysis, then run Phase 3 processing.</p>
        </section>
      ) : (
        <>
          {(view === "all" || view === "analysis") && <div className="space-y-4">
            <PreprocessingNerCard dashboard={dashboard} />
            <EmotionTensionCard emotion={dashboard.phase3.emotion_analysis} />
          </div>}
          {(view === "all" || view === "routing") && <>
            <ExplainableTraceCard dashboard={dashboard} />
            <div className="grid gap-5 xl:grid-cols-2">
              <SensitiveRoutingCard route={dashboard.phase3.sensitive_routing} />
              <MediationEligibilityCard eligibility={dashboard.phase3.mediation_eligibility} />
            </div>
            <ReferralPanel
              officialDecision={dashboard.phase3.official_decision}
              onRefresh={() => loadDashboard(dashboard.case_id)}
              onWorkflowAction={onReferralWorkflowAction}
              referrals={dashboard.phase3.referrals}
            />
          </>}
          {(view === "all" || view === "preparation") && <div className="space-y-4">
            <SectionCard title="Hearing Schedule" icon={CalendarDays} tone="blue">
              <HearingScheduler caseId={dashboard.case_id} onRefresh={() => loadDashboard(dashboard.case_id)} />
              <div className="mt-4">
                <HearingTimeline hearings={dashboard.phase3.hearings} onRefresh={() => loadDashboard(dashboard.case_id)} />
              </div>
            </SectionCard>
            <SectionCard title="Proof and Evidence Upload" icon={UploadCloud} tone="blue">
              <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
                <EvidenceUploadPanel caseId={dashboard.case_id} onRefresh={() => loadDashboard(dashboard.case_id)} />
                <EvidenceFileList evidence={dashboard.phase3.evidence} />
              </div>
            </SectionCard>
          </div>}
          {(view === "all" || view === "mediation") && <MediationSuggestionsPanel suggestions={dashboard.phase3.mediation_suggestions} />}
          {view === "all" && <Phase4FormsPanel caseId={dashboard.case_id} />}
          {dashboard.phase3.sensitive_routing?.blocking_mediation && (() => {
            const latestReferral = dashboard.phase3.referrals[0];
            if (latestReferral?.status === "completed") {
              return (
                <div className="flex items-start gap-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-emerald-900" role="status">
                  <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-700" size={20} />
                  <div>
                    <p className="text-sm font-black">Referral Completed</p>
                    <p className="mt-1 text-sm font-bold leading-6">The referral path has been resolved. Ordinary mediation remains inapplicable; continue with the referral forms and final escalation outcome.</p>
                  </div>
                </div>
              );
            }
            if (latestReferral?.status === "cancelled") {
              return (
                <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-amber-900" role="status">
                  <AlertTriangle className="mt-0.5 shrink-0 text-amber-700" size={20} />
                  <div>
                    <p className="text-sm font-black">Referral Cancelled — Ready for Final Documentation</p>
                    <p className="mt-1 text-sm font-bold leading-6">The cancellation resolves this referral action. Ordinary mediation remains blocked; continue to Outcome &amp; Forms to preserve the KP analysis and finalize the official case record.</p>
                  </div>
                </div>
              );
            }
            return (
              <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
                <AlertTriangle className="mt-0.5 shrink-0" size={20} />
                <p className="text-sm font-bold leading-6">Mediation is blocked until the pending referral or manual-review path is resolved by officials.</p>
              </div>
            );
          })()}
        </>
      )}
    </div>
  );
}
