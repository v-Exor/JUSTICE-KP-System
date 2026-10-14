"use client";

import axios from "axios";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Brain,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  ClipboardList,
  CloudDownload,
  Database,
  Download,
  Eye,
  EyeOff,
  FileArchive,
  FileBarChart,
  FileCheck2,
  FileClock,
  FileCog,
  FileText,
  FolderKanban,
  Lock,
  LoaderCircle,
  LogOut,
  Mic,
  Pause,
  Play,
  Plus,
  Power,
  Printer,
  RefreshCw,
  Route,
  Save,
  Scale,
  Search,
  Settings,
  Shield,
  SlidersHorizontal,
  Square,
  Trash2,
  UploadCloud,
  UserRound,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { jsPDF } from "jspdf";
import {
  defaultCaseInformation,
  toApiCaseInformation,
  type AnalyzeCaseResponse,
  type CaseInformation,
} from "./CaseAnalysis";
import CaseInfoForm from "./CaseInfoForm";
import { formatDisplayLabel, formatDisplayList, humanizeDisplayText } from "./displayText";
import JurisdictionResult from "./JurisdictionResult";
import Phase3DashboardPage from "./Phase3DashboardPage";
import { formatPhilippineDateTime } from "./philippineTime";
import CaseSummaryPage, { type CompletedCaseSummary } from "./management/CaseSummary";
import CasesTable, { type ManagementCaseRecord } from "./management/CasesTable";
import FormsSearch from "./management/FormsSearch";
import ManagementSearchInput from "./management/ManagementSearchInput";
import Pagination from "./management/Pagination";
import SavedDraftPicker from "./management/SavedDraftPicker";
import TranscriptNavigator from "./management/TranscriptNavigator";

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

type TabId = "dashboard" | "workflow" | "cases" | "transcripts" | "forms" | "reports" | "validation" | "settings";

type WorkflowNavigationGuard = {
  hasUnsavedChanges: () => boolean;
  saveDraft: () => Promise<boolean>;
  draftLabel: () => string;
};

type WorkflowStage = {
  id: number;
  label: string;
  shortLabel: string;
  description: string;
  panelIds: number[];
};

type WorkflowState = {
  consentComplainant: boolean;
  consentRespondent: boolean;
  consentFiles: ConsentFileRecord[];
  recordingType: "blotter_case" | "blotter_hearing";
  transcript: string;
  transcriptId: number | null;
  transcriptDirty: boolean;
  transcriptSegments: TranscriptSegment[];
  rawTranscript: string;
  rawTranscriptSegments: TranscriptSegment[];
  caseInformation: CaseInformation;
  decisionAction: "record" | "summons";
  hearingDate: string;
  hearingTime: string;
  venue: string;
  evidenceUploaded: boolean;
  hearingRecorded: boolean;
  hearingTranscript: string;
  hearingTranscriptId: number | null;
  hearingTranscriptSegments: TranscriptSegment[];
  rawHearingTranscript: string;
  rawHearingTranscriptSegments: TranscriptSegment[];
  blotterAudioFilename: string;
  blotterDurationSeconds: number;
  hearingNotes: string;
  hearingSavedAt: string;
  analysisConfirmed: boolean;
  phase2Analysis: AnalyzeCaseResponse | null;
  phase2AnalysisId: number | null;
  phase2CaseId: string;
  skippedPanelIds: number[];
  phase3Processed: boolean;
  phase3ReferralRequired: boolean;
  phase3RecommendedRoute: string;
  symbolicConfirmed: boolean;
  phase4PacketId: number | null;
  outcome: string;
  finalizedAt: string;
  completed: boolean;
  caseCancelled: boolean;
  cancellationReason: string;
  cancelledAt: string;
  cancelledBy: string;
  officialDecision: string;
  referralResolution: {
    referralId: number;
    status: "completed" | "cancelled";
    destination: string;
    officialDecision: string;
    resolvedAt: string;
    resolvedBy: string;
    cancellationReason?: string;
  } | null;
};

type CaseRecord = ManagementCaseRecord & {
  route?: "mediation" | "referral" | "vawc_referral" | "cancelled";
  phase4_packet_id?: number | null;
  privacy_label: string;
};

type CasePage = {
  items: CaseRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

type ReportDefinition = {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  tone: "blue" | "green" | "purple" | "amber";
  rows: string[];
};

type KPFormDefinition = {
  id: string;
  formNumber: string;
  title: string;
  description: string;
  status: string;
  tone: "blue" | "green" | "amber" | "gray";
  stage: "Complaint" | "Notice" | "Pangkat" | "Settlement" | "Certification" | "Execution";
};

type SettingsState = {
  fullName: string;
  role: string;
  darkMode: boolean;
  hearingReminders: boolean;
  aiAlerts: boolean;
};

type PdfRequest = {
  title: string;
  subtitle: string;
  rows: string[];
  filename: string;
};

type TranscriptSegment = {
  speaker: string;
  start: number;
  end: number;
  text: string;
  confidence?: number | null;
};

type UploadResponse = {
  filename?: string;
  playback_filename?: string;
  provider?: string;
  recording_type?: string;
  expected_speakers?: number;
  asr_confidence?: number | null;
  diarization_quality?: number | null;
  detected_speakers?: number;
  audio_duration_seconds?: number | null;
  accuracy_metrics?: Record<string, unknown>;
  transcript: TranscriptSegment[];
  warnings?: string[];
};

type SaveTranscriptResponse = {
  id: number;
  learned_corrections?: number;
  created_at?: string;
  accuracy_metrics?: Record<string, unknown>;
  warning?: string;
  operation?: "created" | "updated";
  workflow_id?: string | null;
  case_id?: string | null;
  save_context?: "intake" | "hearing" | "standalone";
  workflow_revision?: number | null;
};

type ConsentFileRecord = {
  id: string;
  file_name: string;
  party_type: string;
  size_bytes: number;
  uploaded_by: string;
  uploaded_at: string;
};

type WorkflowDraftRecord = {
  workflow_id: string;
  owner_user_id: number;
  status: "active" | "completed" | string;
  active_step: number;
  max_unlocked_step: number;
  case_id: string;
  transcript_id: number | null;
  case_analysis_id: number | null;
  payload: Partial<WorkflowState> & Record<string, unknown>;
  revision: number;
  created_at: string;
  updated_at: string;
  current_stage: {
    id: number;
    label: string;
    short_label: string;
  };
  completion_percentage: number;
  owner: {
    id: number;
    username: string;
    full_name: string;
  } | null;
  phase4_packet?: WorkflowFormPacket;
};

type WorkflowDraftPage = {
  items: WorkflowDraftRecord[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

// The API clamps oversized page requests to the actual last page.  Using a
// fixed sentinel keeps "newest draft" navigation correct without coupling the
// client to a total that may have changed in another tab.
const LAST_DRAFT_PAGE = 2_147_483_647;

type WorkflowGeneratedForm = {
  id: number;
  form_id: string;
  title: string;
  download_url: string;
  missing_fields: string[];
  validation_status: "ready" | "needs_review";
};

type WorkflowFormPacket = {
  id: number;
  case_id: string;
  source_phase3_action: string;
  validation_status: "ready" | "needs_review";
  form_accuracy_pct: number;
  generated_forms: WorkflowGeneratedForm[];
};

type WorkflowFinalizeResponse = WorkflowDraftRecord & {
  phase4_packet: WorkflowFormPacket;
};

type WorkflowPhase3Response = {
  phase3: {
    sensitive_routing: {
      recommended_route: string;
      blocking_mediation: boolean;
    } | null;
    referrals: Array<{ status: "pending" | "completed" | "cancelled" }>;
    final_recommended_action: string;
  };
};

type WorkflowReferralActionResponse = WorkflowDraftRecord & {
  message: string;
  referral: {
    id: number;
    status: "completed" | "cancelled";
    destination: string;
  };
  official_decision: {
    official_decision: string;
    official_notes: string;
    approved_by: string;
    approved_at: string;
  } | null;
};

type CurrentUser = {
  id: number;
  username: string;
  full_name: string;
  role_name: string;
  permissions: string[];
  csrf_token?: string;
};

type AdminUser = {
  id: number;
  username: string;
  full_name: string;
  role_name: string;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

type BackupRecord = {
  backup_id: string;
  backup_type: string;
  status: string;
  created_by: string;
  created_at: string;
  verified_at: string | null;
  manifest: {
    database_size_bytes?: number;
    file_count?: number;
    file_size_bytes?: number;
    encryption_algorithm?: string;
  };
};

type Phase5ImportableWorkflow = {
  workflow_id: string;
  case_id: string;
  analysis_id: number | null;
  revision: number;
  status: string;
  outcome: string;
  finalized_at: string | null;
  route: string;
  phase4_packet_id: number | null;
  packet_ready: boolean;
  referral_required: boolean;
  referral_ready: boolean;
  official_decision_ready: boolean;
  already_imported: boolean;
  eligible: boolean;
  ineligibility_reasons: string[];
};

type Phase5FinalizedWorkflowImportResponse = {
  validation_case: Phase5ValidationCase;
  source_workflow: Phase5ImportableWorkflow;
};

type SavedTranscriptSummary = {
  id: number;
  workflow_id?: string | null;
  case_id?: string | null;
  save_context?: "intake" | "hearing" | "standalone";
  asr_provider: string;
  asr_confidence: number | null;
  diarization_quality: number | null;
  manual_correction_rate: number | null;
  recording_type?: string;
  expected_speakers?: number | null;
  detected_speakers?: number | null;
  segment_count: number;
  correction_count: number;
  created_at: string;
  updated_at?: string | null;
};

type SavedTranscript = SavedTranscriptSummary & {
  content: string;
  raw_content: string;
  segments: TranscriptSegment[];
  raw_segments: TranscriptSegment[];
  corrections: Array<{ wrong: string; corrected: string }>;
  accuracy_metrics: Record<string, unknown>;
};

type SavedTranscriptPage = {
  items: SavedTranscriptSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

type Phase5GroundTruth = {
  expected_covered_under_kp?: boolean | null;
  expected_jurisdiction_decision: string;
  expected_exclusion_ground: string;
  expected_sensitive_case?: boolean | null;
  expected_referral_route: string;
  expected_mediation_eligible?: boolean | null;
  expected_form_ids: string[];
  expected_keywords: string[];
  expected_speaker_count?: number | null;
  reference_transcript: string;
  reviewer_name: string;
};

type Phase5ComplianceReview = {
  consent_confirmed: boolean;
  transcript_anonymized: boolean;
  official_decision_saved: boolean;
  generated_forms_reviewed: boolean;
  audit_trail_complete: boolean;
  sensitive_case_referred: boolean;
  reviewer_name: string;
  notes: string;
  compliance_score?: number;
};

type Phase5ValidationCase = {
  id: number;
  case_id: string;
  audio_id: string | null;
  dataset_split: string;
  speaker_count: number | null;
  speaker_gender_mix: string;
  audio_quality: string;
  manual_processing_time_min: number | null;
  system_processing_time_min: number | null;
  notes: string;
  case_information: Record<string, unknown>;
  system_outputs: {
    jurisdiction_decision: string;
    exclusion_ground: string;
    sensitive_case: boolean;
    referral_route: string;
    mediation_eligible: boolean | null;
    generated_form_ids: string[];
    recommended_form_ids: string[];
    detected_keywords: string[];
    detected_speaker_count: number | null;
    xai_trace_length: number;
    form_accuracy_pct: number | null;
    final_recommended_action: string;
  };
  ground_truth: (Phase5GroundTruth & Record<string, unknown>) | null;
  compliance_review: (Phase5ComplianceReview & Record<string, unknown>) | null;
  latest_evaluation: Record<string, unknown> | null;
  review_status: "needs_ground_truth" | "ready_for_evaluation" | "evaluated";
  ground_truth_ready: boolean;
  ground_truth_missing_fields: string[];
  can_delete: boolean;
};

type Phase5Metrics = {
  case_count: number;
  evaluated_count: number;
  overall_accuracy_pct: number | null;
  jurisdiction_accuracy_pct: number | null;
  sensitive_accuracy_pct: number | null;
  referral_accuracy_pct: number | null;
  mediation_accuracy_pct: number | null;
  forms_accuracy_pct: number | null;
  average_form_accuracy_pct: number | null;
  average_compliance_score_pct: number | null;
  average_manual_time_min: number | null;
  average_system_time_min: number | null;
  average_time_saved_min: number | null;
  average_time_saved_pct: number | null;
  by_dispute_category: Array<{ group: string; case_count: number; overall_accuracy_pct: number | null; jurisdiction_accuracy_pct: number | null }>;
  by_speaker_gender_mix: Array<{ group: string; case_count: number; overall_accuracy_pct: number | null; jurisdiction_accuracy_pct: number | null }>;
  error_cases: Array<{ case_id: string; errors: string[]; evaluated_at: string }>;
};

type DashboardSummary = {
  metrics: {
    resolution_rate_pct: number | null;
    average_processing_days: number | null;
    settlement_ratio: string;
    mediation_success_pct: number | null;
    total_cases: number;
    pending_cases: number;
    referred_cases: number;
    generated_forms: number;
  };
  monthly_trend: Array<{ label: string; count: number }>;
  settlement_referral_trend: {
    settled: number;
    referred: number;
  };
  category_breakdown: Array<{ label: string; count: number; percentage: number }>;
  kp_distribution: {
    covered: number;
    referred: number;
    covered_pct: number | null;
  };
  activity_heatmap: number[];
  recent_routings: Array<{ case_id: string; text: string; status: string; tone: "amber" | "green" | "red" | "blue" }>;
  system_logs: Array<{ label: string; time: string }>;
  generated_at: string;
};

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
const LOGIN_TIMEOUT_MS = 15_000;
axios.defaults.withCredentials = true;

function setCsrfToken(token?: string) {
  if (!token) {
    return;
  }
  localStorage.setItem("justice_kp_csrf", token);
  axios.defaults.headers.common["X-CSRF-Token"] = token;
}

function clearCsrfToken() {
  localStorage.removeItem("justice_kp_csrf");
  delete axios.defaults.headers.common["X-CSRF-Token"];
}

function hasPermission(user: CurrentUser | null, permission: string) {
  return Boolean(user?.permissions.includes(permission));
}

const tabs: Array<{ id: TabId; label: string; icon: LucideIcon }> = [
  { id: "dashboard", label: "Dashboard", icon: BarChart3 },
  { id: "workflow", label: "Workflow", icon: Route },
  { id: "cases", label: "Cases & Records", icon: FolderKanban },
  { id: "transcripts", label: "Saved Transcripts", icon: FileClock },
  { id: "forms", label: "KP Forms", icon: ClipboardList },
  { id: "reports", label: "Reports", icon: FileBarChart },
  { id: "validation", label: "Validation", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings },
];

const workflowStages: WorkflowStage[] = [
  { id: 1, label: "Intake & Case Assessment", shortLabel: "Intake", description: "Consent, transcript, case facts, and backend decision", panelIds: [1, 2] },
  { id: 2, label: "Summons & Hearing", shortLabel: "Hearing", description: "Case preparation, notices, evidence, and hearing transcript", panelIds: [3, 4] },
  { id: 3, label: "Analysis & Routing", shortLabel: "Review", description: "NER, emotion analysis, KP rules, and routing confirmation", panelIds: [5, 6] },
  { id: 4, label: "Resolution & Forms", shortLabel: "Outcome", description: "Mediation or referral outcome and official KP forms", panelIds: [7] },
];

const workflowTaskLabels: Record<number, string> = {
  1: "Consent & Transcript",
  2: "Case Facts & Decision",
  3: "Summons & Proof",
  4: "Hearing Transcript",
  5: "NER & Emotion",
  6: "Decision Routing",
  7: "Outcome & Forms",
};

function workflowStageForPanel(panelId: number) {
  return workflowStages.find((stage) => stage.panelIds.includes(panelId)) ?? workflowStages[0];
}

const reports: ReportDefinition[] = [
  {
    id: "monthly",
    title: "Monthly Case Report",
    description: "Comprehensive overview of all blotters, hearings, and settlements processed within the selected month.",
    icon: CalendarDays,
    tone: "blue",
    rows: ["Total cases: 1,248", "Pending cases: 156", "Resolution rate: 82.4%", "Referred cases: 155"],
  },
  {
    id: "settlement",
    title: "Settlement Performance Report",
    description: "Analytics on successful mediations, conciliations, and arbitration awards vs repudiations.",
    icon: Activity,
    tone: "green",
    rows: ["Settled via KP: 78%", "Settlement ratio: 3.5 : 1", "Average processing time: 12 days"],
  },
  {
    id: "mediation",
    title: "Mediation Success Report",
    description: "Specific performance metrics for individual mediators and the Lupon Tagapamayapa as a whole.",
    icon: UsersRound,
    tone: "purple",
    rows: ["Mediation success: 78%", "High agitation cases: 12", "Cooling-off recommendations: 8"],
  },
  {
    id: "hearing",
    title: "Hearing Schedule Report",
    description: "Upcoming and historical hearing logs, attendance records, and rescheduling requests.",
    icon: FileClock,
    tone: "amber",
    rows: ["Hearings this month: 42", "Rescheduled: 6", "Completed hearings: 36"],
  },
  {
    id: "statistics",
    title: "Barangay Statistics Report",
    description: "High-level demographic data of complainants and respondents, mapped to case categories.",
    icon: FileBarChart,
    tone: "blue",
    rows: ["Property disputes: 25%", "Debt collection: 45%", "Physical injury: 15%", "Slander/rumor: 10%"],
  },
];

const kpForms: KPFormDefinition[] = [
  { id: "kp-form-7", formNumber: "7", title: "KP Form 7", description: "Complaint/summons case template for initiating the barangay case record.", status: "Official PDF ready", tone: "blue", stage: "Complaint" },
  { id: "kp-form-8", formNumber: "8", title: "KP Form 8", description: "Notice of hearing for mediation proceedings.", status: "Official PDF ready", tone: "blue", stage: "Notice" },
  { id: "kp-form-9", formNumber: "9", title: "KP Form 9", description: "Case notice template for respondent or party appearance.", status: "Official PDF ready", tone: "blue", stage: "Notice" },
  { id: "kp-form-10", formNumber: "10", title: "KP Form 10", description: "Notice for the constitution of the Pangkat Tagapagkasundo.", status: "Official PDF ready", tone: "amber", stage: "Pangkat" },
  { id: "kp-form-11", formNumber: "11", title: "KP Form 11", description: "Pangkat-related case record template.", status: "Official PDF ready", tone: "amber", stage: "Pangkat" },
  { id: "kp-form-12", formNumber: "12", title: "KP Form 12", description: "Notice of hearing for conciliation proceedings.", status: "Official PDF ready", tone: "amber", stage: "Notice" },
  { id: "kp-form-13", formNumber: "13", title: "KP Form 13", description: "Pangkat proceeding form template.", status: "Official PDF ready", tone: "amber", stage: "Pangkat" },
  { id: "kp-form-14", formNumber: "14", title: "KP Form 14", description: "Pangkat action or hearing documentation template.", status: "Official PDF ready", tone: "amber", stage: "Pangkat" },
  { id: "kp-form-15", formNumber: "15", title: "KP Form 15", description: "Pangkat proceeding documentation template.", status: "Official PDF ready", tone: "amber", stage: "Pangkat" },
  { id: "kp-form-16", formNumber: "16", title: "KP Form 16", description: "Kasunduang Pag-aayos or amicable settlement agreement.", status: "Official PDF ready", tone: "green", stage: "Settlement" },
  { id: "kp-form-17", formNumber: "17", title: "KP Form 17", description: "Settlement or award follow-through documentation template.", status: "Official PDF ready", tone: "green", stage: "Settlement" },
  { id: "kp-form-18", formNumber: "18", title: "KP Form 18", description: "Settlement-related case action template.", status: "Official PDF ready", tone: "green", stage: "Settlement" },
  { id: "kp-form-19", formNumber: "19", title: "KP Form 19", description: "Post-mediation case documentation template.", status: "Official PDF ready", tone: "green", stage: "Settlement" },
  { id: "kp-form-20", formNumber: "20", title: "KP Form 20", description: "Certificate to file action or unresolved case certification template.", status: "Official PDF ready", tone: "gray", stage: "Certification" },
  { id: "kp-form-20-a", formNumber: "20-A", title: "KP Form 20-A", description: "Supplemental certification template for unresolved or referred action.", status: "Official PDF ready", tone: "gray", stage: "Certification" },
  { id: "kp-form-20-b", formNumber: "20-B", title: "KP Form 20-B", description: "Supplemental certification template for subsequent action.", status: "Official PDF ready", tone: "gray", stage: "Certification" },
  { id: "kp-form-21", formNumber: "21", title: "KP Form 21", description: "Post-settlement or execution-related barangay case form.", status: "Official PDF ready", tone: "gray", stage: "Execution" },
  { id: "kp-form-22", formNumber: "22", title: "KP Form 22", description: "Execution or follow-through documentation template.", status: "Official PDF ready", tone: "gray", stage: "Execution" },
  { id: "kp-form-23", formNumber: "23", title: "KP Form 23", description: "Execution or compliance documentation template.", status: "Official PDF ready", tone: "gray", stage: "Execution" },
  { id: "kp-form-24", formNumber: "24", title: "KP Form 24", description: "Execution-stage barangay case documentation template.", status: "Official PDF ready", tone: "gray", stage: "Execution" },
  { id: "kp-form-25", formNumber: "25", title: "KP Form 25", description: "Final execution or compliance documentation template.", status: "Official PDF ready", tone: "gray", stage: "Execution" },
];

function kpFormDownloadUrl(formId: string) {
  return `${API_BASE_URL}/api/kp-forms/${formId}/download`;
}

function kpFormViewUrl(formId: string) {
  return `${kpFormDownloadUrl(formId)}?disposition=inline`;
}

function kpFormFilename(form: KPFormDefinition) {
  return `KP Form ${form.formNumber}.pdf`;
}

async function openKpForm(form: KPFormDefinition) {
  const previewWindow = window.open(kpFormViewUrl(form.id), "_blank", "noopener,noreferrer");
  if (!previewWindow) {
    window.alert("Allow pop-ups for this site to preview the KP form.");
  }
}

async function downloadKpForm(form: KPFormDefinition) {
  try {
    const response = await axios.get<Blob>(kpFormDownloadUrl(form.id), { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([response.data], { type: "application/pdf" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = kpFormFilename(form);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch {
    window.alert("Please sign in again before downloading this KP form.");
  }
}

const initialWorkflow: WorkflowState = {
  consentComplainant: false,
  consentRespondent: false,
  consentFiles: [],
  recordingType: "blotter_case",
  transcript: "",
  transcriptId: null,
  transcriptDirty: false,
  transcriptSegments: [],
  rawTranscript: "",
  rawTranscriptSegments: [],
  caseInformation: defaultCaseInformation,
  decisionAction: "summons",
  hearingDate: "",
  hearingTime: "09:00",
  venue: "Barangay Hall",
  evidenceUploaded: false,
  hearingRecorded: false,
  hearingTranscript: "",
  hearingTranscriptId: null,
  hearingTranscriptSegments: [],
  rawHearingTranscript: "",
  rawHearingTranscriptSegments: [],
  blotterAudioFilename: "",
  blotterDurationSeconds: 0,
  hearingNotes: "",
  hearingSavedAt: "",
  analysisConfirmed: false,
  phase2Analysis: null,
  phase2AnalysisId: null,
  phase2CaseId: "",
  skippedPanelIds: [],
  phase3Processed: false,
  phase3ReferralRequired: false,
  phase3RecommendedRoute: "",
  symbolicConfirmed: false,
  phase4PacketId: null,
  outcome: "Amicable Settlement Reached",
  finalizedAt: "",
  completed: false,
  caseCancelled: false,
  cancellationReason: "",
  cancelledAt: "",
  cancelledBy: "",
  officialDecision: "",
  referralResolution: null,
};

function downloadPdf({ title, subtitle, rows, filename }: PdfRequest) {
  const doc = new jsPDF();
  const generatedAt = formatPhilippineDateTime(new Date(), {
    dateStyle: "medium",
    timeStyle: "short",
  });

  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.text("JUSTICE-KP 2.0", 18, 18);
  doc.setFontSize(13);
  doc.text(title, 18, 32);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.text(subtitle, 18, 42, { maxWidth: 174 });
  doc.text(`Generated: ${generatedAt}`, 18, 54);
  doc.line(18, 62, 192, 62);

  let y = 74;
  rows.forEach((row, index) => {
    doc.text(`${index + 1}. ${row}`, 22, y, { maxWidth: 166 });
    y += 11;
  });

  doc.setFontSize(9);
  doc.text("Generated for frontend demo. Official templates will be uploaded in a later phase.", 18, 282);
  doc.save(filename);
}

const VAWC_TRIGGER_KEYWORDS = [
  "sinaktan", "binugbog", "pinagbubugbog", "sinuntok", "sinipa", "sinampal", "kinurot",
  "tinadyakan", "hinampas", "pinukpok", "sinakal", "tinulak", "kinaladkad", "pinaso",
  "pinahirapan", "binato", "pinalo", "hinataw", "sugatan", "nasaktan", "nasugatan",
  "dumugo", "nabalian", "napuruhan", "banta", "binantaan", "pananakit", "violence",
  "abuse", "threatened", "hurt", "injured",
] as const;

function detectVawcKeywords(transcript: string) {
  const normalized = transcript.toLowerCase();
  return VAWC_TRIGGER_KEYWORDS.filter((keyword) => {
    const pattern = new RegExp(`(^|[^a-z0-9_])${escapeRegExp(keyword)}([^a-z0-9_]|$)`, "i");
    return pattern.test(normalized);
  });
}

function isVawcAnalysis(analysis: AnalyzeCaseResponse | null) {
  return Boolean(analysis?.detected_keywords.vawc_trigger);
}

function requiresReferralPath(analysis: AnalyzeCaseResponse | null) {
  return Boolean(analysis && analysis.jurisdiction_decision !== "within_kp");
}

function isReferralRecommendation(route: string) {
  const normalized = route.trim().toLowerCase();
  return Boolean(normalized && normalized !== "proceed to mediation" && normalized !== "awaiting evidence");
}

const CANCELLED_REFERRAL_OUTCOME = "Referral Cancelled - Case Closed After Official Review";

function workflowOutcomeOptions(
  isReferralPath: boolean,
  isVawcPath: boolean,
  referralStatus?: "completed" | "cancelled",
) {
  if (referralStatus === "cancelled") {
    return [CANCELLED_REFERRAL_OUTCOME];
  }
  if (isVawcPath) {
    return ["Referred to WCPD / PNP", "Referred to MSWDO / PNP", "Emergency Protection Assistance Initiated"];
  }
  if (isReferralPath) {
    return ["Referred to Court / Proper Authority", "Referred for Manual Review", "Referral Packet Issued"];
  }
  return ["Amicable Settlement Reached", "No Settlement - Certificate to File Action", "Repudiated Settlement"];
}

function skippedPanelsForAnalysis(analysis: AnalyzeCaseResponse | null) {
  if (isVawcAnalysis(analysis)) {
    return [3, 4, 5, 6];
  }
  return requiresReferralPath(analysis) ? [3, 4] : [];
}

function cleanWorkflowPayload(workflow: WorkflowState): WorkflowState {
  return {
    ...workflow,
    skippedPanelIds: skippedPanelsForAnalysis(workflow.phase2Analysis),
  };
}

function workflowDraftFingerprint(workflow: WorkflowState, activeStep: number, maxUnlockedStep: number) {
  return JSON.stringify({
    activeStep,
    maxUnlockedStep,
    payload: cleanWorkflowPayload(workflow),
  });
}

function formatTranscript(segments: TranscriptSegment[]) {
  return segments.map((segment) => `${segment.speaker}: ${segment.text}`).join("\n\n");
}

function speakerRoleClassName(speaker: string) {
  const normalized = speaker.trim().toLowerCase();
  if (normalized.includes("respondent")) {
    return "speaker-role-respondent";
  }
  if (normalized.includes("complainant")) {
    return "speaker-role-complainant";
  }
  if (
    normalized.includes("mediator")
    || normalized.includes("barangay secretary")
    || normalized.includes("punong barangay")
  ) {
    return "speaker-role-mediator";
  }
  return "speaker-role-neutral";
}

function transcriptToSegments(transcript: string): TranscriptSegment[] {
  const blocks = transcript
    .split(/\n\s*\n|\n(?=[^\n:]{1,60}:\s*)/)
    .map((block) => block.trim())
    .filter(Boolean);

  return blocks.map((block, index) => {
    const separator = block.indexOf(":");
    const speaker = separator > 0 ? block.slice(0, separator).trim() : `Speaker ${index + 1}`;
    const text = separator > 0 ? block.slice(separator + 1).trim() : block;
    return {
      speaker,
      start: index * 5,
      end: index * 5 + 5,
      text,
      confidence: null,
    };
  });
}

function formatElapsedTime(totalSeconds: number) {
  const safeSeconds = Number.isFinite(totalSeconds) && totalSeconds >= 0 ? Math.floor(totalSeconds) : 0;
  const minutes = Math.floor(safeSeconds / 60).toString().padStart(2, "0");
  const seconds = (safeSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function formatFileSize(sizeBytes: number) {
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getAudioRecorderOptions(): MediaRecorderOptions {
  if (typeof MediaRecorder === "undefined") {
    return {};
  }

  const supportedMimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"].find(
    (mimeType) => MediaRecorder.isTypeSupported(mimeType)
  );

  return supportedMimeType
    ? {
        audioBitsPerSecond: 128000,
        mimeType: supportedMimeType,
      }
    : {
        audioBitsPerSecond: 128000,
    };
}

function LoginScreen({ onLogin }: { onLogin: (user: CurrentUser) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStoppingProgram, setIsStoppingProgram] = useState(false);
  const [shutdownMessage, setShutdownMessage] = useState("");

  const stopLocalProgram = async () => {
    const confirmed = window.confirm(
      "Stop JUSTICE-KP completely? This will close the local frontend and backend servers. Any unsaved screen changes will be lost.",
    );
    if (!confirmed) {
      return;
    }

    setIsStoppingProgram(true);
    setShutdownMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/system/shutdown`, {}, { timeout: 5000 });
      setShutdownMessage("JUSTICE-KP is stopping. You may close this browser tab.");
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setShutdownMessage(detail ?? "The program could not be stopped. Close the development terminals manually.");
      setIsStoppingProgram(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage("");
    try {
      const response = await axios.post<CurrentUser>(
        `${API_BASE_URL}/api/auth/login`,
        {
          username: username.trim(),
          password,
        },
        { timeout: LOGIN_TIMEOUT_MS },
      );
      setCsrfToken(response.data.csrf_token);
      onLogin(response.data);
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        setErrorMessage("Invalid username or password.");
      } else if (axios.isAxiosError(error) && error.code === "ECONNABORTED") {
        setErrorMessage("Sign-in timed out because the backend is busy or unavailable. Please try again.");
      } else {
        setErrorMessage("Could not reach the backend. Check that the server is running, then try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="justice-login-bg flex min-h-screen items-center justify-center overflow-hidden px-4 py-8 text-gray-950">
      <section className="login-card grid w-full max-w-[895px] overflow-hidden rounded-lg border border-white/30 bg-white shadow-2xl lg:grid-cols-2">
        <div className="login-brand-panel flex min-h-[420px] flex-col justify-center bg-blue-800 px-8 py-10 text-white sm:px-12">
          <div className="brand-mark flex items-center gap-4">
            <Scale aria-hidden="true" className="text-blue-100" size={44} strokeWidth={2.4} />
            <h1 className="text-2xl font-extrabold sm:text-3xl">JUSTICE-KP 2.0</h1>
          </div>

          <div className="mt-8 max-w-[320px]">
            <h2 className="text-lg font-bold leading-7 text-blue-50">
              Justice Katarungang Pambarangay Management System
            </h2>
            <p className="mt-9 text-sm leading-6 text-blue-50/95">
              Empowering local barangays with neuro-symbolic AI for efficient, fair, and transparent dispute
              resolution.
            </p>
            <p className="mt-5 text-sm font-semibold leading-6 text-blue-100">
              Republic of the Philippines
              <br />
              Province of Laguna
            </p>
          </div>
        </div>

        <form
          className="login-form-panel flex min-h-[420px] flex-col justify-center bg-white px-8 py-10 sm:px-12"
          onSubmit={handleSubmit}
        >
          <div>
            <h2 className="text-2xl font-extrabold text-gray-950">Barangay Secretary Login</h2>
            <p className="mt-3 text-sm leading-6 text-gray-500">Please enter your credentials to access the system.</p>
          </div>

          <div className="mt-8 space-y-5">
            <label className="block">
              <span className="text-sm font-bold text-gray-700">Username</span>
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="login-input mt-2 h-11 w-full rounded-md border border-gray-300 bg-white px-4 text-sm outline-none transition"
                placeholder="Enter your username"
              />
            </label>

            <label className="block">
              <span className="text-sm font-bold text-gray-700">Password</span>
              <div className="relative mt-2">
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="login-input h-11 w-full rounded-md border border-gray-300 bg-white px-4 pr-11 text-sm outline-none transition"
                  placeholder="Enter your password"
                  type={showPassword ? "text" : "password"}
                />
                <button
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-3 top-1/2 inline-flex size-7 -translate-y-1/2 items-center justify-center rounded-md text-gray-400 transition hover:bg-gray-100 hover:text-gray-700"
                  onClick={() => setShowPassword((current) => !current)}
                  type="button"
                >
                  {showPassword ? <Eye aria-hidden="true" size={18} /> : <EyeOff aria-hidden="true" size={18} />}
                </button>
              </div>
            </label>
          </div>

          <div className="mt-5 flex items-center justify-between gap-4 text-sm">
            <label className="flex items-center gap-3 font-semibold text-gray-600">
              <input className="size-4 rounded border-gray-300 accent-blue-700" type="checkbox" />
              Remember Me
            </label>
            <button className="font-semibold text-blue-700 transition hover:text-blue-900" type="button">
              Forgot Password?
            </button>
          </div>

          <button
            className="login-submit mt-6 inline-flex h-12 w-full items-center justify-center rounded-md bg-blue-700 px-4 text-base font-bold text-white shadow-lg shadow-blue-700/25 transition"
            disabled={isSubmitting}
            type="submit"
          >
            {isSubmitting ? "Signing In..." : "Sign In"}
          </button>
          {errorMessage && (
            <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700">{errorMessage}</p>
          )}

          <p className="mt-8 text-center text-xs font-semibold leading-5 text-slate-700">
            &copy; 2026 Laguna State Polytechnic University
            <br />
            College of Computer Studies
          </p>
        </form>
      </section>
      {process.env.NODE_ENV !== "production" && (
        <div className="fixed bottom-5 left-5 z-30 flex max-w-sm flex-col items-start gap-2">
          {shutdownMessage && (
            <p className="rounded-md border border-red-300 bg-white px-3 py-2 text-xs font-bold text-red-800 shadow-lg">
              {shutdownMessage}
            </p>
          )}
          <button
            className="inline-flex min-h-11 items-center gap-2 rounded-md border border-red-400 bg-red-700 px-4 text-sm font-black text-white shadow-lg shadow-black/25 transition hover:bg-red-800 focus:outline-none focus:ring-4 focus:ring-red-300 disabled:cursor-wait disabled:bg-red-400"
            disabled={isStoppingProgram}
            onClick={() => stopLocalProgram().catch(() => undefined)}
            type="button"
          >
            <Power aria-hidden="true" size={18} />
            {isStoppingProgram ? "Stopping Program..." : "Stop Program"}
          </button>
        </div>
      )}
    </main>
  );
}

function StatusPill({ tone, label }: { tone: CaseRecord["tone"] | "gray"; label: string }) {
  const styles = {
    amber: "border-amber-200 bg-amber-100 text-amber-800",
    blue: "border-blue-200 bg-blue-50 text-blue-700",
    gray: "border-gray-200 bg-gray-100 text-gray-600",
    green: "border-emerald-200 bg-emerald-100 text-emerald-700",
    red: "border-red-200 bg-red-50 text-red-700",
  };

  return <span className={`status-pill status-pill-${tone} inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-bold ${styles[tone]}`}>{humanizeDisplayText(label)}</span>;
}

function ToneIcon({ icon: Icon, tone }: { icon: LucideIcon; tone: "blue" | "green" | "purple" | "amber" | "red" | "gray" }) {
  const styles = {
    amber: "border-amber-200 bg-amber-50 text-amber-600",
    blue: "border-blue-100 bg-blue-50 text-blue-700",
    gray: "border-gray-200 bg-gray-50 text-gray-600",
    green: "border-emerald-200 bg-emerald-50 text-emerald-700",
    purple: "border-purple-200 bg-purple-50 text-purple-700",
    red: "border-red-200 bg-red-50 text-red-600",
  };

  return (
    <div className={`flex size-11 shrink-0 items-center justify-center rounded-lg border ${styles[tone]}`}>
      <Icon aria-hidden="true" size={21} />
    </div>
  );
}

function AppButton({
  children,
  tone = "secondary",
  disabled = false,
  onClick,
  type = "button",
}: {
  children: React.ReactNode;
  tone?: "primary" | "secondary" | "danger" | "success";
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  const styles = {
    danger: "border-red-600 bg-red-600 text-white hover:bg-red-700",
    primary: "border-blue-600 bg-blue-600 text-white hover:bg-blue-700",
    secondary: "border-gray-300 bg-white text-gray-900 hover:bg-gray-50",
    success: "border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-700",
  };

  return (
    <button
      className={`app-button app-button-${tone} inline-flex min-h-10 items-center justify-center gap-2 rounded-md border px-4 text-sm font-bold shadow-sm transition ${styles[tone]} disabled:cursor-not-allowed disabled:border-gray-200 disabled:bg-gray-100 disabled:text-gray-400 disabled:shadow-none`}
      disabled={disabled}
      onClick={onClick}
      type={type}
    >
      {children}
    </button>
  );
}

function normalizeSearchQuery(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function matchesSearchQuery(
  query: string,
  values: Array<string | number | null | undefined>,
) {
  const normalizedQuery = normalizeSearchQuery(query);
  if (!normalizedQuery) {
    return true;
  }
  return values.some((value) => normalizeSearchQuery(String(value ?? "")).includes(normalizedQuery));
}

function ModalPortal({ children, onDismiss }: { children: React.ReactNode; onDismiss: () => void }) {
  const onDismissRef = useRef(onDismiss);

  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    const previousBodyOverflow = document.body.style.overflow;
    const previousDocumentOverflow = document.documentElement.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onDismissRef.current();
      }
    };

    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousDocumentOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  if (typeof document === "undefined") {
    return null;
  }

  return createPortal(children, document.body);
}

function DashboardPanel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <article className={`dashboard-panel rounded-lg border border-white/10 bg-slate-950/78 p-5 shadow-sm shadow-slate-950/20 ${className}`}>
      {children}
    </article>
  );
}

function buildChartPath(values: number[], width: number, height: number, padding = 18) {
  const maxValue = Math.max(...values, 1);
  const step = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0;
  const points = values.map((value, index) => {
    const x = padding + index * step;
    const y = height - padding - (value / maxValue) * (height - padding * 2);
    return { x, y };
  });
  const line = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const area = points.length ? `${line} L ${points[points.length - 1].x.toFixed(1)} ${height - padding} L ${points[0].x.toFixed(1)} ${height - padding} Z` : "";

  return { area, line, points };
}

function AnimatedLineChart({ items }: { items: DashboardSummary["monthly_trend"] }) {
  const values = items.map((item) => item.count);
  const { area, line, points } = buildChartPath(values.length ? values : [0], 640, 250);
  const maxValue = Math.max(...values, 1);

  return (
    <div className="relative mt-6 min-h-72 overflow-hidden rounded-lg border border-white/10 bg-slate-950/55 p-4">
      <div className="absolute inset-x-5 top-8 bottom-10 grid grid-rows-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <span className="border-t border-white/10" key={index} />
        ))}
      </div>
      <svg className="relative h-60 w-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 640 250">
        <defs>
          <linearGradient id="monthlyArea" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.46" />
            <stop offset="62%" stopColor="#2563eb" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#020617" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="monthlyStroke" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="48%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <path className="chart-area" d={area} fill="url(#monthlyArea)" />
        <path className="chart-line" d={line} fill="none" stroke="url(#monthlyStroke)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" vectorEffect="non-scaling-stroke" />
        {points.map((point, index) => (
          <circle className="chart-dot" cx={point.x} cy={point.y} fill="#e0f2fe" key={`${point.x}-${index}`} r="4" style={{ animationDelay: `${index * 80 + 420}ms` }} />
        ))}
      </svg>
      <div className="relative grid grid-cols-6 gap-2 text-xs font-bold text-slate-400">
        {items.map((item) => (
          <span className="truncate" key={item.label}>{item.label}</span>
        ))}
      </div>
      <div className="absolute right-5 top-5 rounded-md border border-sky-300/20 bg-slate-950/80 px-3 py-2 text-xs font-black text-sky-100">
        Peak {maxValue}
      </div>
    </div>
  );
}

function AnimatedBarChart({ items, maxValue }: { items: DashboardSummary["monthly_trend"]; maxValue: number }) {
  return (
    <div className="mt-6 flex h-72 items-end gap-3 border-b border-white/10 px-2 pb-3">
      {items.map((item, index) => (
        <div className="flex flex-1 flex-col items-center justify-end gap-3" key={item.label}>
          <span className="text-xs font-black text-slate-300">{item.count}</span>
          <div
            className="animated-bar w-full max-w-16 rounded-t-md bg-gradient-to-t from-blue-700 via-sky-500 to-cyan-300 shadow-lg shadow-blue-950/30 transition hover:brightness-125"
            style={{ "--bar-height": `${Math.max(8, (item.count / maxValue) * 100)}%`, animationDelay: `${index * 80}ms` } as React.CSSProperties}
          />
          <span className="text-xs font-bold text-slate-500">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function DashboardTab({ onSwitchTab }: { onSwitchTab: (tab: TabId) => void }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const loadSummary = async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const response = await axios.get<DashboardSummary>(`${API_BASE_URL}/api/dashboard/summary`);
      setSummary(response.data);
    } catch {
      setErrorMessage("Dashboard data is unavailable. Check that the backend is running and your session is active.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSummary();
  }, []);

  const formatNumber = (value: number) => new Intl.NumberFormat("en-PH").format(value);
  const formatPercent = (value: number | null) => (value === null ? "N/A" : `${value}%`);
  const maxMonthly = Math.max(...(summary?.monthly_trend.map((item) => item.count) ?? [0]), 1);
  const totalCategories = summary?.category_breakdown.reduce((total, item) => total + item.count, 0) ?? 0;
  const totalDistribution = (summary?.kp_distribution.covered ?? 0) + (summary?.kp_distribution.referred ?? 0);
  const coveredDegrees = totalDistribution ? Math.round(((summary?.kp_distribution.covered ?? 0) / totalDistribution) * 360) : 0;
  const settlementTotal = (summary?.settlement_referral_trend.settled ?? 0) + (summary?.settlement_referral_trend.referred ?? 0);
  const settledWidth = settlementTotal ? Math.max(4, Math.round(((summary?.settlement_referral_trend.settled ?? 0) / settlementTotal) * 100)) : 0;
  const referredWidth = settlementTotal ? Math.max(4, 100 - settledWidth) : 0;

  const metricCards = summary
    ? [
        { label: "Resolution Rate", value: formatPercent(summary.metrics.resolution_rate_pct), note: "Official decisions saved", icon: Activity, tone: "green" as const },
        {
          label: "Avg Processing Time",
          value: summary.metrics.average_processing_days === null ? "N/A" : `${summary.metrics.average_processing_days} Days`,
          note: "Case saved to final decision",
          icon: CalendarDays,
          tone: "blue" as const,
        },
        { label: "Settlement Ratio", value: summary.metrics.settlement_ratio, note: "Settled vs referred records", icon: Scale, tone: "purple" as const },
        { label: "Mediation Success", value: formatPercent(summary.metrics.mediation_success_pct), note: "Eligible mediation outcomes", icon: UsersRound, tone: "green" as const },
        { label: "Total Cases", value: formatNumber(summary.metrics.total_cases), note: "Saved Phase 2 analyses", icon: FileText, tone: "blue" as const },
        { label: "Pending Cases", value: formatNumber(summary.metrics.pending_cases), note: "No final decision yet", icon: Activity, tone: "amber" as const },
        { label: "Referred Cases", value: formatNumber(summary.metrics.referred_cases), note: "Outside KP or authority route", icon: CheckCircle2, tone: "red" as const },
        { label: "KP Forms Gen.", value: formatNumber(summary.metrics.generated_forms), note: "Generated Phase 4 forms", icon: ClipboardList, tone: "purple" as const },
      ]
    : [];

  const exportRows = metricCards.map((metric) => `${metric.label}: ${metric.value} (${metric.note})`);

  return (
    <div className="page-enter dashboard-surface space-y-6 text-slate-100">
      <section className="relative overflow-hidden rounded-lg border border-white/10 bg-slate-950/82 p-5 shadow-sm shadow-slate-950/25 sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.26em] text-sky-300">JUSTICE-KP Operations</p>
            <h1 className="mt-2 text-3xl font-black text-white sm:text-4xl">Executive Dashboard</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">Live operational summary from saved cases, routing, hearings, decisions, forms, and audit activity.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <AppButton tone="primary" onClick={() => onSwitchTab("workflow")}>
              <Plus aria-hidden="true" size={18} />
              New Blotter
            </AppButton>
            <AppButton disabled={isLoading} onClick={loadSummary}>
              <RefreshCw aria-hidden="true" className={isLoading ? "animate-spin" : ""} size={17} />
              Refresh
            </AppButton>
            <AppButton onClick={() => window.print()}>
              <Printer aria-hidden="true" size={17} />
              Print Report
            </AppButton>
            <AppButton
              onClick={() =>
                downloadPdf({
                  title: "Executive Dashboard Report",
                  subtitle: `Live dashboard export${summary?.generated_at ? ` generated ${formatPhilippineDateTime(summary.generated_at)}` : ""}.`,
                  rows: exportRows.length ? exportRows : ["No dashboard data loaded."],
                  filename: "justice-kp-dashboard-report.pdf",
                })
              }
            >
              <CloudDownload aria-hidden="true" size={17} />
              Export PDF
            </AppButton>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3 text-xs font-bold text-slate-400">
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">Phase 2 cases: {summary ? formatNumber(summary.metrics.total_cases) : "..."}</span>
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">Forms generated: {summary ? formatNumber(summary.metrics.generated_forms) : "..."}</span>
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5">{summary?.generated_at && !errorMessage ? `Last refreshed ${formatPhilippineDateTime(summary.generated_at)}` : "Waiting for live summary"}</span>
        </div>
        {errorMessage && <p className="dashboard-error mt-4 rounded-md border border-red-400/30 bg-red-500/10 p-3 text-sm font-bold text-red-100">{errorMessage}</p>}
      </section>

      {isLoading ? (
        <section className="rounded-lg border border-white/10 bg-slate-950/78 p-8 text-center shadow-sm shadow-slate-950/20">
          <p className="text-sm font-black text-slate-300">Loading dashboard summary...</p>
        </section>
      ) : (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metricCards.map((metric, index) => (
            <article className="dashboard-card stat-card rounded-lg border border-white/10 bg-slate-950/78 p-5 shadow-sm shadow-slate-950/20" key={metric.label} style={{ animationDelay: `${index * 45}ms` }}>
              <div className="flex items-start justify-between gap-3">
                <ToneIcon icon={metric.icon} tone={metric.tone} />
                <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[11px] font-black text-slate-400">Live</span>
              </div>
              <p className="mt-5 text-3xl font-black text-white">{metric.value}</p>
              <p className="mt-1 text-sm font-bold text-slate-300">{metric.label}</p>
              <span className="mt-3 inline-flex rounded-md bg-white/5 px-2.5 py-1 text-xs font-bold text-slate-500">{metric.note}</span>
            </article>
          ))}
        </section>
      )}

      <section className="grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <DashboardPanel>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-black text-white">Cases per Month</h2>
              <p className="mt-1 text-xs font-bold text-slate-500">Monthly trend with smooth line motion</p>
            </div>
            <div className="flex rounded-full border border-white/10 bg-white/5 p-1 text-xs font-black text-slate-400">
              <span className="rounded-full bg-sky-500 px-3 py-1 text-white">6M</span>
              <span className="px-3 py-1">YTD</span>
            </div>
          </div>
          {summary?.monthly_trend.length ? <AnimatedLineChart items={summary.monthly_trend} /> : <p className="mt-6 text-sm font-bold text-slate-500">No saved cases yet.</p>}
        </DashboardPanel>

        <DashboardPanel>
          <h2 className="text-lg font-black text-white">Settlement vs Referrals</h2>
          <p className="mt-1 text-xs font-bold text-slate-500">Operational routing health</p>
          <div className="mt-7 flex h-72 flex-col justify-center gap-7 rounded-lg border border-white/10 bg-slate-950/55 p-5">
            <div>
              <div className="flex items-center justify-between text-sm font-bold text-slate-300">
                <span>Settled or mediation path</span>
                <span>{summary?.settlement_referral_trend.settled ?? 0}</span>
              </div>
              <div className="mt-3 h-4 overflow-hidden rounded-full bg-white/10">
                <div className="animated-progress h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-300" style={{ "--progress-width": `${settledWidth}%` } as React.CSSProperties} />
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between text-sm font-bold text-slate-300">
                <span>Referral records</span>
                <span>{summary?.settlement_referral_trend.referred ?? 0}</span>
              </div>
              <div className="mt-3 h-4 overflow-hidden rounded-full bg-white/10">
                <div className="animated-progress h-full rounded-full bg-gradient-to-r from-rose-500 to-amber-300" style={{ "--progress-width": `${referredWidth}%`, animationDelay: "120ms" } as React.CSSProperties} />
              </div>
            </div>
            <div className="flex gap-4 text-xs font-semibold">
              <span className="text-emerald-300">Settled via KP</span>
              <span className="text-rose-300">Referred Outside</span>
            </div>
          </div>
        </DashboardPanel>
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <DashboardPanel>
          <h2 className="text-lg font-black text-white">Case Category Breakdown</h2>
          <p className="mt-1 text-xs font-bold text-slate-500">NLP classified records</p>
          <div className="mt-7 min-h-64 space-y-4">
            {(summary?.category_breakdown ?? []).map((item, index) => (
              <div key={item.label}>
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-bold text-slate-300">{item.label}</span>
                  <span className="font-black text-sky-300">{item.count}</span>
                </div>
                <div className="mt-2 h-3 overflow-hidden rounded-full bg-white/10">
                  <div
                    className={`animated-progress h-full rounded-full ${["bg-sky-500", "bg-blue-500", "bg-cyan-400", "bg-violet-400", "bg-slate-400"][index]}`}
                    style={{ "--progress-width": `${totalCategories ? (item.count / totalCategories) * 100 : 0}%`, animationDelay: `${index * 90}ms` } as React.CSSProperties}
                  />
                </div>
              </div>
            ))}
            {!summary?.category_breakdown.length && <p className="text-sm font-bold text-slate-500">No case categories available yet.</p>}
          </div>
        </DashboardPanel>

        <DashboardPanel>
          <h2 className="text-lg font-black text-white">KP Eligibility Distribution</h2>
          <p className="mt-1 text-xs font-bold text-slate-500">Rule engine coverage</p>
          <div className="mt-7 flex min-h-64 flex-col items-center justify-center">
            <div className="donut-chart size-52 rounded-full p-10 shadow-sm shadow-blue-950/30" style={{ "--donut-angle": `${coveredDegrees}deg` } as React.CSSProperties}>
              <div className="grid size-full place-items-center rounded-full bg-slate-950 text-center">
                <span className="text-2xl font-black text-white">{formatPercent(summary?.kp_distribution.covered_pct ?? null)}</span>
              </div>
            </div>
            <div className="mt-5 flex gap-4 text-xs font-semibold">
              <span className="text-emerald-300">Covered: {summary?.kp_distribution.covered ?? 0}</span>
              <span className="text-rose-300">Not Covered: {summary?.kp_distribution.referred ?? 0}</span>
            </div>
          </div>
        </DashboardPanel>

        <DashboardPanel>
          <h2 className="text-lg font-black text-white">Monthly Volume</h2>
          <p className="mt-1 text-xs font-bold text-slate-500">Bar chart rhythm from live case saves</p>
          {summary?.monthly_trend.length ? <AnimatedBarChart items={summary.monthly_trend} maxValue={maxMonthly} /> : <p className="mt-6 text-sm font-bold text-slate-500">No saved cases yet.</p>}
        </DashboardPanel>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1fr_1fr]">
        <DashboardPanel>
          <h2 className="flex items-center gap-2 text-lg font-black text-white">
            <Activity className="text-sky-300" size={20} />
            Activity Heatmap
          </h2>
          <div className="mt-16 flex justify-center">
            <div className="grid grid-cols-7 gap-2">
              {(summary?.activity_heatmap ?? []).map((level, index) => (
                <span className={`heat-cell size-6 rounded-md ${["bg-slate-800", "bg-blue-900", "bg-blue-700", "bg-sky-500", "bg-cyan-300"][level - 1]}`} key={index} style={{ animationDelay: `${index * 20}ms` }} />
              ))}
            </div>
          </div>
          <p className="mt-5 text-center text-xs text-slate-500">Last 35 days of saved case activity, normalized by busiest day.</p>
        </DashboardPanel>

        <DashboardPanel>
          <h2 className="flex items-center gap-2 text-lg font-black text-white">
            <Route className="text-violet-300" size={20} />
            Recent AI Routings
          </h2>
          <div className="mt-4 space-y-3">
            {(summary?.recent_routings ?? []).map((routing, index) => (
              <div className="rounded-lg border border-white/10 bg-white/[0.04] p-4 transition hover:-translate-y-0.5 hover:border-sky-300/30" key={`${routing.case_id}-${routing.status}-${index}`}>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-black text-slate-500">{routing.case_id}</p>
                  <StatusPill label={routing.status} tone={routing.tone} />
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-300">{routing.text}</p>
              </div>
            ))}
            {!summary?.recent_routings.length && <p className="rounded-lg border border-dashed border-white/10 p-4 text-sm font-bold text-slate-500">No Phase 3 routings yet.</p>}
          </div>
        </DashboardPanel>

        <DashboardPanel>
          <h2 className="flex items-center gap-2 text-lg font-black text-white">
            <Activity className="text-slate-400" size={20} />
            System Logs
          </h2>
          <div className="mt-4 space-y-4">
            {(summary?.system_logs ?? []).map((log, index) => (
              <div className="flex gap-3" key={`${log.label}-${log.time}-${index}`}>
                <span className="log-check flex size-8 shrink-0 items-center justify-center rounded-full border border-emerald-300/30 bg-emerald-400/10 text-emerald-200">
                  <Check size={15} />
                </span>
                <div>
                  <p className="text-sm font-bold text-slate-100">{log.label}</p>
                  <p className="mt-1 text-xs text-slate-500">{log.time}</p>
                </div>
              </div>
            ))}
            {!summary?.system_logs.length && <p className="text-sm font-bold text-slate-500">No audit activity yet.</p>}
          </div>
        </DashboardPanel>
      </section>
    </div>
  );
}

function Stepper({
  activeStep,
  maxUnlockedStep,
  skippedPanelIds,
  setActiveStep,
}: {
  activeStep: number;
  maxUnlockedStep: number;
  skippedPanelIds: number[];
  setActiveStep: (step: number) => void;
}) {
  const activeStage = workflowStageForPanel(activeStep);

  return (
    <div className="workflow-stage-nav border-b border-gray-200 pb-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {workflowStages.map((stage) => {
          const availablePanels = stage.panelIds.filter((panelId) => panelId <= maxUnlockedStep && !skippedPanelIds.includes(panelId));
          const skipped = stage.panelIds.every((panelId) => skippedPanelIds.includes(panelId));
          const locked = availablePanels.length === 0;
          const active = stage.id === activeStage.id;
          const complete = !active && stage.panelIds.every((panelId) => skippedPanelIds.includes(panelId) || panelId < activeStep);
          const targetPanel = availablePanels.at(-1);

          return (
            <button
              className={`workflow-stage-button min-h-24 rounded-lg border p-4 text-left transition ${
                active
                  ? "border-blue-600 bg-blue-600 text-white shadow-md shadow-blue-600/20"
                  : locked
                    ? "border-gray-200 bg-gray-50 text-gray-400"
                    : complete
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700 hover:border-emerald-300"
                      : "border-gray-300 bg-white text-gray-900 hover:border-blue-200 hover:bg-blue-50"
              }`}
              disabled={locked}
              key={stage.id}
              onClick={() => targetPanel && setActiveStep(targetPanel)}
              type="button"
            >
              <span className="flex items-center gap-2 text-xs font-black uppercase tracking-wide">
                {locked && <Lock aria-hidden="true" size={13} />}
                {complete && <CheckCircle2 aria-hidden="true" size={15} />}
                Stage {stage.id} of {workflowStages.length}
                {skipped && <span className="ml-auto">Skipped</span>}
              </span>
              <span className="mt-2 block text-sm font-black">{stage.label}</span>
              <span className={`mt-1 block text-xs leading-5 ${active ? "text-blue-100" : complete ? "text-emerald-700" : "text-gray-500"}`}>{stage.description}</span>
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex flex-col gap-3 rounded-lg border border-gray-200 bg-gray-50 p-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-wide text-blue-700">Current stage</p>
          <p className="mt-1 text-sm font-black text-gray-950">{activeStage.label}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {activeStage.panelIds.map((panelId, index) => {
            const skipped = skippedPanelIds.includes(panelId);
            const locked = panelId > maxUnlockedStep || skipped;
            const active = panelId === activeStep;
            return (
              <button
                className={`inline-flex min-h-9 items-center gap-2 rounded-md border px-3 text-xs font-black transition ${active ? "border-blue-600 bg-blue-600 text-white" : locked ? "border-gray-200 bg-white text-gray-400" : "border-gray-300 bg-white text-gray-700 hover:border-blue-300 hover:text-blue-700"}`}
                disabled={locked}
                key={panelId}
                onClick={() => setActiveStep(panelId)}
                type="button"
              >
                {locked ? <Lock size={12} /> : active ? <span className="size-2 rounded-full bg-white" /> : <span className="text-gray-400">{index + 1}</span>}
                {workflowTaskLabels[panelId]}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function WorkflowRecordingPanel({
  transcript,
  segments,
  rawSegments = [],
  recordingType,
  onRecordingTypeChange,
  onTranscriptChange,
  onSegmentsChange,
  onRawTranscriptReady,
  onTranscriptSaved,
  onRecordingStarted,
  savedTranscriptId = null,
  hasUnsavedChanges = true,
  workflowId = "",
  caseId = "",
  mode = "blotter",
  sourceTranscript = "",
  sourceSegments = [],
  audioFilename = "",
  durationSeconds = 0,
  onAudioReady,
  onBusyChange,
  partiesConsented = false,
}: {
  transcript: string;
  segments: TranscriptSegment[];
  rawSegments?: TranscriptSegment[];
  recordingType: "blotter_case" | "blotter_hearing";
  onRecordingTypeChange: (recordingType: "blotter_case" | "blotter_hearing") => void;
  onTranscriptChange: (transcript: string) => void;
  onSegmentsChange: (segments: TranscriptSegment[]) => void;
  onRawTranscriptReady?: (content: string, segments: TranscriptSegment[]) => void;
  onTranscriptSaved: (result: SaveTranscriptResponse, content: string, segments: TranscriptSegment[]) => void | Promise<void>;
  onRecordingStarted?: () => void;
  savedTranscriptId?: number | null;
  hasUnsavedChanges?: boolean;
  workflowId?: string;
  caseId?: string;
  mode?: "blotter" | "hearing";
  sourceTranscript?: string;
  sourceSegments?: TranscriptSegment[];
  audioFilename?: string;
  durationSeconds?: number;
  onAudioReady?: (filename: string, durationSeconds: number) => void;
  onBusyChange?: (busy: boolean) => void;
  partiesConsented?: boolean;
}) {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const processingTimerRef = useRef<number | null>(null);
  const processingStartedAtRef = useRef(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const audioFileInputRef = useRef<HTMLInputElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const hearingTranscriptInitializedRef = useRef(false);
  const elapsedSecondsRef = useRef(durationSeconds);
  const hearingAudioRef = useRef<HTMLAudioElement | null>(null);
  const componentActiveRef = useRef(true);

  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [processingStage, setProcessingStage] = useState<"idle" | "preparing" | "uploading" | "transcribing" | "complete">("idle");
  const [processingProgress, setProcessingProgress] = useState(0);
  const [processingElapsedSeconds, setProcessingElapsedSeconds] = useState(0);
  const [processingFileName, setProcessingFileName] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [statusMessage, setStatusMessage] = useState("Ready to record.");
  const [errorMessage, setErrorMessage] = useState("");
  const [warningMessage, setWarningMessage] = useState("");
  const [playbackSeconds, setPlaybackSeconds] = useState(0);
  const [isPlaybackActive, setIsPlaybackActive] = useState(false);
  const [playbackError, setPlaybackError] = useState("");
  const [uploadMetrics, setUploadMetrics] = useState<Pick<
    UploadResponse,
    "provider" | "recording_type" | "expected_speakers" | "asr_confidence" | "diarization_quality" | "detected_speakers" | "accuracy_metrics"
  > | null>(null);
  const recorderBusy = isRecording || isProcessing || isSaving;
  const recordingLocked = Boolean(audioFilename) || processingStage === "complete";
  const matchedVawcKeywords = detectVawcKeywords(transcript);
  const isVawcTranscript = matchedVawcKeywords.length > 0;
  const expectedSpeakerRoles = recordingType === "blotter_case"
    ? ["Barangay Secretary/Mediator", "Complainant"]
    : ["Barangay Secretary/Mediator", "Complainant", "Respondent"];

  useEffect(() => {
    if (mode !== "hearing" || hearingTranscriptInitializedRef.current) {
      return;
    }
    if (transcript.trim()) {
      hearingTranscriptInitializedRef.current = true;
      return;
    }
    if (!sourceTranscript.trim()) {
      return;
    }

    hearingTranscriptInitializedRef.current = true;
    const copiedSegments = (sourceSegments.length ? sourceSegments : transcriptToSegments(sourceTranscript)).map((segment) => ({ ...segment }));
    onSegmentsChange(copiedSegments);
    onTranscriptChange(formatTranscript(copiedSegments));
  }, [mode, onSegmentsChange, onTranscriptChange, sourceSegments, sourceTranscript, transcript]);

  const stopTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const stopProcessingTimer = () => {
    if (processingTimerRef.current !== null) {
      window.clearInterval(processingTimerRef.current);
      processingTimerRef.current = null;
    }
  };

  const startProcessingTimer = () => {
    stopProcessingTimer();
    processingStartedAtRef.current = Date.now();
    setProcessingElapsedSeconds(0);
    setProcessingProgress(20);
    processingTimerRef.current = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - processingStartedAtRef.current) / 1000);
      // Progress advances by 10% per minute: 30% at 1 minute, 40% at
      // 2 minutes, and so on. It stops below 100% until ASR truly finishes.
      const timedProgress = Math.min(95, 20 + Math.floor(seconds / 6));
      setProcessingElapsedSeconds(seconds);
      setProcessingProgress(timedProgress);
    }, 1000);
  };

  const releaseMicrophone = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  const stopAudioVisualizer = () => {
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    analyserRef.current = null;
  };

  const drawAudioVisualizer = () => {
    const analyser = analyserRef.current;
    const canvas = waveformCanvasRef.current;
    const audioContext = audioContextRef.current;
    if (!analyser || !canvas || !audioContext) {
      return;
    }

    const canvasContext = canvas.getContext("2d");
    if (!canvasContext) {
      return;
    }

    const width = canvas.width;
    const height = canvas.height;
    const byteData = new Uint8Array(analyser.fftSize);
    const floatData = new Float32Array(analyser.fftSize);

    analyser.getByteTimeDomainData(byteData);
    analyser.getFloatTimeDomainData(floatData);

    let peak = 0;
    for (const sample of floatData) {
      peak = Math.max(peak, Math.abs(sample));
    }

    canvasContext.clearRect(0, 0, width, height);
    canvasContext.fillStyle = "#030712";
    canvasContext.fillRect(0, 0, width, height);

    canvasContext.lineWidth = 3;
    canvasContext.strokeStyle = peak > 0.08 ? "#60a5fa" : "#64748b";
    canvasContext.beginPath();

    const sliceWidth = width / byteData.length;
    let x = 0;

    for (let index = 0; index < byteData.length; index += 1) {
      const y = (byteData[index] / 128) * (height / 2);
      if (index === 0) {
        canvasContext.moveTo(x, y);
      } else {
        canvasContext.lineTo(x, y);
      }
      x += sliceWidth;
    }

    canvasContext.lineTo(width, height / 2);
    canvasContext.stroke();

    animationFrameRef.current = window.requestAnimationFrame(drawAudioVisualizer);
  };

  const startAudioVisualizer = async (stream: MediaStream) => {
    stopAudioVisualizer();
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      setWarningMessage("Live waveform is not supported in this browser, but recording can still continue.");
      return;
    }

    const audioContext = new AudioContextClass();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.82;

    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    audioContextRef.current = audioContext;
    analyserRef.current = analyser;
    drawAudioVisualizer();
  };

  useEffect(() => {
    componentActiveRef.current = true;
    return () => {
      // Upload/transcription and transcript-save requests may finish after the
      // user opens another workflow.  The backend request remains bound to its
      // original workflow_id, while this guard prevents its late response from
      // mutating the newly opened draft in React.
      componentActiveRef.current = false;
      stopTimer();
      stopProcessingTimer();
      stopAudioVisualizer();
      releaseMicrophone();
    };
  }, []);

  useEffect(() => {
    onBusyChange?.(recorderBusy);
  }, [onBusyChange, recorderBusy]);

  useEffect(() => () => onBusyChange?.(false), [onBusyChange]);

  const startRecording = async () => {
    setErrorMessage("");
    setWarningMessage("");

    if (recordingLocked) {
      setErrorMessage("This workflow already has an audio record. A new recording cannot replace it.");
      return;
    }
    if (mode === "blotter" && !workflowId) {
      setErrorMessage("Create or select a workflow draft before recording audio.");
      return;
    }
    setElapsedSeconds(0);
    elapsedSecondsRef.current = 0;
    setProcessingStage("idle");
    setProcessingProgress(0);
    setProcessingElapsedSeconds(0);
    setProcessingFileName("");

    if (!navigator.mediaDevices?.getUserMedia) {
      setErrorMessage("Microphone recording is not supported in this browser or context. Open the app through localhost or HTTPS.");
      setStatusMessage("Ready to record.");
      return;
    }

    if (typeof MediaRecorder === "undefined") {
      setErrorMessage("MediaRecorder is not supported in this browser. Use a recent Chrome, Edge, or Firefox browser.");
      setStatusMessage("Ready to record.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: { ideal: 1 },
          echoCancellation: true,
          noiseSuppression: false,
          autoGainControl: true,
          sampleRate: { ideal: 48000 },
          sampleSize: { ideal: 16 },
        },
      });

      streamRef.current = stream;
      audioChunksRef.current = [];
      await startAudioVisualizer(stream);

      const recorder = new MediaRecorder(stream, getAudioRecorderOptions());

      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      recorder.onerror = (event) => {
        setErrorMessage(`Recording failed: ${event.error?.message ?? "The browser stopped microphone capture."}`);
        setStatusMessage("Ready to record.");
        setIsRecording(false);
        setIsProcessing(false);
        stopTimer();
        stopAudioVisualizer();
        releaseMicrophone();
      };
      recorder.onstop = handleRecordingStop;
      recorder.start(1000);

      onRecordingStarted?.();
      setIsRecording(true);
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((current) => {
          const next = current + 1;
          elapsedSecondsRef.current = next;
          return next;
        });
      }, 1000);
      setStatusMessage("Recording blotter audio...");
    } catch (error) {
      const message = error instanceof DOMException ? error.message : "Microphone access was denied or unavailable.";
      setErrorMessage(`Microphone access failed. ${message}`);
      setStatusMessage("Ready to record.");
      stopTimer();
      stopAudioVisualizer();
      releaseMicrophone();
    }
  };

  const stopRecording = () => {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
      return;
    }

    mediaRecorderRef.current.stop();
    setIsRecording(false);
    setIsProcessing(true);
    setProcessingStage("preparing");
    setProcessingProgress(10);
    setStatusMessage("Uploading audio and generating transcript...");
    stopTimer();
  };

  const processAudioFile = async (audioFile: Blob, fileName: string, knownDurationSeconds = 0) => {
    const formData = new FormData();
    formData.append("file", audioFile, fileName);
    formData.append("recording_type", recordingType);
    if (workflowId) {
      formData.append("workflow_id", workflowId);
    }
    setProcessingFileName(fileName);

    if (!audioFile.size) {
      setErrorMessage("The selected audio file is empty.");
      setStatusMessage("Ready to record.");
      setIsProcessing(false);
      setProcessingStage("idle");
      setProcessingProgress(0);
      return;
    }

    try {
      setProcessingStage("uploading");
      startProcessingTimer();
      const response = await axios.post<UploadResponse>(`${API_BASE_URL}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (event) => {
          if (!event.total || event.loaded >= event.total) {
            setProcessingStage("transcribing");
          }
        },
      });

      if (!componentActiveRef.current) {
        return;
      }

      stopProcessingTimer();
      setProcessingStage("complete");
      setProcessingProgress(100);
      setProcessingFileName(response.data.filename ?? fileName);
      setStatusMessage("Transcription complete. Preparing the editable transcript...");
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      if (!componentActiveRef.current) {
        return;
      }
      const playbackFilename = response.data.playback_filename ?? response.data.filename;
      const resolvedDuration = response.data.audio_duration_seconds ?? knownDurationSeconds;
      if (playbackFilename) {
        onAudioReady?.(playbackFilename, resolvedDuration);
      }
      const generatedTranscript = formatTranscript(response.data.transcript);
      onRawTranscriptReady?.(generatedTranscript, response.data.transcript.map((segment) => ({ ...segment })));
      onSegmentsChange(response.data.transcript.map((segment) => ({ ...segment })));
      onTranscriptChange(generatedTranscript);
      setUploadMetrics({
        provider: response.data.provider,
        recording_type: response.data.recording_type,
        expected_speakers: response.data.expected_speakers,
        asr_confidence: response.data.asr_confidence,
        diarization_quality: response.data.diarization_quality,
        detected_speakers: response.data.detected_speakers,
        accuracy_metrics: response.data.accuracy_metrics,
      });
      setWarningMessage(response.data.warnings?.join(" ") ?? "");
      if (response.data.transcript.length) {
        setStatusMessage("Transcript ready for review. Edit it, then select Save Transcript to store the raw and corrected versions together.");
      } else {
        setStatusMessage("No speech was detected. The audio record is retained and locked; add transcript segments manually if needed.");
      }
    } catch (error) {
      if (!componentActiveRef.current) {
        return;
      }
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setErrorMessage(detail ?? "Transcription failed. Check that the FastAPI backend is running.");
      setStatusMessage("Ready to record.");
      stopProcessingTimer();
      setProcessingStage("idle");
      setProcessingProgress(0);
    } finally {
      if (componentActiveRef.current) {
        setIsProcessing(false);
      }
    }
  };

  const handleRecordingStop = async () => {
    stopTimer();
    stopAudioVisualizer();
    releaseMicrophone();
    const recordedType = mediaRecorderRef.current?.mimeType || "audio/webm";
    const audioBlob = new Blob(audioChunksRef.current, { type: recordedType });
    const extension = recordedType.includes("ogg") ? "ogg" : "webm";
    const recordingFileName = `justice-kp-${Date.now()}.${extension}`;
    try {
      await processAudioFile(audioBlob, recordingFileName, elapsedSecondsRef.current);
    } finally {
      audioChunksRef.current = [];
      mediaRecorderRef.current = null;
    }
  };

  const chooseAudioFile = () => {
    setErrorMessage("");
    setWarningMessage("");
    if (recordingLocked) {
      setErrorMessage("This workflow already has an audio record. A new upload cannot replace it.");
      return;
    }
    if (mode === "blotter" && !workflowId) {
      setErrorMessage("Create or select a workflow draft before uploading audio.");
      return;
    }
    audioFileInputRef.current?.click();
  };

  const handleAudioFileSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    event.target.value = "";
    if (!selectedFile) {
      return;
    }
    if (recordingLocked) {
      setErrorMessage("This workflow already has an audio record. A new upload cannot replace it.");
      return;
    }

    setErrorMessage("");
    setWarningMessage("");
    setElapsedSeconds(0);
    elapsedSecondsRef.current = 0;
    setIsProcessing(true);
    setProcessingStage("preparing");
    setProcessingProgress(10);
    setProcessingElapsedSeconds(0);
    setStatusMessage("Preparing uploaded audio for transcription...");
    await processAudioFile(selectedFile, selectedFile.name);
  };

  const segmentsFromCurrentTranscript = () => {
    const parsedSegments = transcriptToSegments(transcript);
    return parsedSegments.map((parsedSegment, index) => {
      const existingSegment = segments[index];
      const parsedSpeaker = /^Speaker \d+$/i.test(parsedSegment.speaker)
        ? expectedSpeakerRoles[index % expectedSpeakerRoles.length]
        : parsedSegment.speaker;
      return existingSegment
        ? { ...existingSegment, speaker: parsedSpeaker, text: parsedSegment.text }
        : { ...parsedSegment, speaker: parsedSpeaker };
    });
  };

  const saveTranscript = async () => {
    if (!transcript.trim()) {
      setErrorMessage("Transcript is empty. Record or enter transcript text first.");
      return;
    }

    setIsSaving(true);
    setErrorMessage("");
    const formattedSegments = formatTranscript(segments);
    const savedSegments = formattedSegments.trim() === transcript.trim() ? segments : segmentsFromCurrentTranscript();
    const savedContent = formatTranscript(savedSegments);

    if (savedSegments !== segments) {
      onSegmentsChange(savedSegments);
      onTranscriptChange(savedContent);
    }

    const savePayload = {
      content: savedContent,
      // Both workflow panels address one canonical transcript. The backend
      // preserves its original ASR data when a hearing replaces the edited
      // version, so Saved Transcripts never receives a duplicate case row.
      transcript_id: savedTranscriptId ?? undefined,
      workflow_id: workflowId || undefined,
      case_id: caseId || undefined,
      save_context: mode === "hearing" ? "hearing" : "intake",
      segments: rawSegments.length ? rawSegments : savedSegments,
      edited_segments: savedSegments,
      provider: uploadMetrics?.provider ?? "",
      recording_type: uploadMetrics?.recording_type ?? recordingType,
      expected_speakers: uploadMetrics?.expected_speakers ?? (recordingType === "blotter_case" ? 2 : 3),
      asr_confidence: uploadMetrics?.asr_confidence,
      diarization_quality: uploadMetrics?.diarization_quality,
      accuracy_metrics: uploadMetrics?.accuracy_metrics ?? {},
    };
    const sendSaveRequest = () =>
      axios.post<SaveTranscriptResponse>(`${API_BASE_URL}/save-transcript`, savePayload);

    try {
      let response;
      try {
        response = await sendSaveRequest();
      } catch (error) {
        if (axios.isAxiosError(error) && error.response?.status === 403) {
          const session = await axios.get<CurrentUser>(`${API_BASE_URL}/api/auth/me`);
          setCsrfToken(session.data.csrf_token);
          response = await sendSaveRequest();
        } else {
          throw error;
        }
      }
      if (!Number.isInteger(response.data.id) || response.data.id <= 0) {
        throw new Error("The backend saved no valid transcript ID.");
      }
      if (!componentActiveRef.current) {
        return;
      }
      await onTranscriptSaved(response.data, savedContent, savedSegments);
      if (!componentActiveRef.current) {
        return;
      }
      const learnedCount = response.data.learned_corrections ?? 0;
      const updatedExisting = response.data.operation === "updated" || Boolean(savedTranscriptId);
      setStatusMessage(
        response.data.warning
          ? `Transcript #${response.data.id} saved. ${response.data.warning}`
          : learnedCount
          ? `${updatedExisting ? "Transcript updated" : "Transcript saved"}. Learned ${learnedCount} correction${learnedCount === 1 ? "" : "s"} for future recordings.`
          : mode === "hearing"
            ? `Hearing changes replaced the edited version of transcript #${response.data.id}. No duplicate transcript was created.`
            : updatedExisting
              ? `Transcript #${response.data.id} updated for this case.`
              : `Transcript #${response.data.id} saved and linked to this case.`
      );
    } catch (error) {
      if (!componentActiveRef.current) {
        return;
      }
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === "string" && detail.trim()) {
          setErrorMessage(`Saving failed: ${detail}`);
        } else if (error.response?.status) {
          setErrorMessage(`Saving failed (HTTP ${error.response.status}). Please try again.`);
        } else {
          const diagnostic = [error.code, error.message].filter(Boolean).join(": ");
          setErrorMessage(`Saving failed before the browser received a response${diagnostic ? ` (${diagnostic})` : ""}.`);
        }
      } else if (error instanceof Error && error.message) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Saving failed due to an unexpected browser error.");
      }
    } finally {
      if (componentActiveRef.current) {
        setIsSaving(false);
      }
    }
  };

  const commitSegments = (nextSegments: TranscriptSegment[]) => {
    onSegmentsChange(nextSegments);
    onTranscriptChange(formatTranscript(nextSegments));
  };

  const updateSegment = (index: number, changes: Partial<TranscriptSegment>) => {
    commitSegments(segments.map((segment, segmentIndex) => segmentIndex === index ? { ...segment, ...changes } : segment));
  };

  const addSegment = () => {
    const start = segments.length ? Math.max(...segments.map((segment) => segment.end)) : 0;
    const usedSpeakers = new Set(segments.map((segment) => segment.speaker));
    const nextSpeaker = expectedSpeakerRoles.find((speaker) => !usedSpeakers.has(speaker))
      ?? expectedSpeakerRoles[segments.length % expectedSpeakerRoles.length];
    commitSegments([
      ...segments,
      { speaker: nextSpeaker, start, end: start + 5, text: "", confidence: null },
    ]);
  };

  const usePanelOneTranscript = () => {
    const copiedSegments = (sourceSegments.length ? sourceSegments : transcriptToSegments(sourceTranscript)).map((segment) => ({ ...segment }));
    commitSegments(copiedSegments);
  };

  const resolvedAudioFilename = audioFilename || (processingStage === "complete" ? processingFileName : "");
  const playPanelOneRecording = async () => {
    if (!resolvedAudioFilename || !hearingAudioRef.current) {
      setPlaybackError("No intake audio is linked to this workflow draft.");
      return;
    }
    setPlaybackError("");
    try {
      await hearingAudioRef.current.play();
    } catch {
      setPlaybackError("The intake recording could not be played. Sign in again or return to Consent & Transcript and save the recording.");
    }
  };

  const stopPanelOneRecording = () => {
    if (!hearingAudioRef.current) {
      return;
    }
    hearingAudioRef.current.pause();
    try {
      hearingAudioRef.current.currentTime = 0;
    } catch {
      // Some browsers reject seeking until media metadata has loaded.
    }
    setPlaybackSeconds(0);
    setIsPlaybackActive(false);
    setPlaybackError("");
  };

  const durationCandidates = [
    durationSeconds,
    elapsedSeconds,
    ...segments.map((segment) => Number(segment.end)),
  ].filter((value) => Number.isFinite(value) && value >= 0);
  const totalDurationSeconds = Math.ceil(Math.max(0, ...durationCandidates));

  if (mode === "hearing") {
    return (
      <div className="hearing-recording-workspace">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-xl font-black text-gray-950">Hearing Recording</h2>
            <p className="mt-2 text-sm text-gray-600">Replay the intake recording, review its speaker timeline, and prepare an editable hearing transcript without recording again.</p>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 px-4 py-2 text-right">
            <p className="text-[11px] font-black uppercase tracking-wide text-gray-500">Intake recording time</p>
            <p className="mt-1 font-mono text-xl font-black text-gray-950">{formatElapsedTime(totalDurationSeconds)}</p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-md border border-gray-200 bg-gray-50 px-4 py-3">
          <div className="flex flex-wrap items-center gap-4 text-xs font-black">
            <span className={resolvedAudioFilename ? "text-emerald-700" : "text-amber-700"}>{resolvedAudioFilename ? "Intake recording loaded" : "Intake recording unavailable"}</span>
            <span className={partiesConsented ? "text-emerald-700" : "text-amber-700"}>{partiesConsented ? "Parties consented to recording" : "Recording consent required"}</span>
            <span className="text-blue-700">Speaker diarization: {segments.length ? "active" : "waiting"}</span>
            <span className="text-gray-600">{segments.length} segment{segments.length === 1 ? "" : "s"}</span>
          </div>
          <StatusPill label={transcript.trim() ? "Editable" : "Waiting"} tone={transcript.trim() ? "green" : "gray"} />
        </div>

        <div className="mt-5 grid gap-5 xl:grid-cols-[300px_1fr]">
          <aside className="space-y-5">
            <section className="rounded-lg border border-gray-200 bg-gray-50 p-4">
              <div className="rounded-md bg-gray-950 p-5 text-center text-white">
                <button
                  aria-label="Play intake recording"
                  className="mx-auto flex size-14 items-center justify-center rounded-full border border-white/15 bg-white/10 text-white transition hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={!resolvedAudioFilename}
                  onClick={() => playPanelOneRecording().catch(() => undefined)}
                  title={resolvedAudioFilename ? "Play intake recording" : "Intake recording unavailable"}
                  type="button"
                >
                  <Play size={25} />
                </button>
                <p className="mt-4 text-xs font-bold text-gray-300">Intake workflow recording</p>
                <p className="mt-2 font-mono text-3xl font-black text-white">{formatElapsedTime(totalDurationSeconds)}</p>
                <div className="mt-4 flex h-20 items-center gap-1 overflow-hidden rounded-md border border-white/10 bg-gray-900 px-4" aria-label="Recorded audio waveform">
                  {[30, 48, 36, 62, 42, 70, 52, 34, 58, 76, 46, 64, 38, 54, 32, 44].map((height, index) => (
                    <span className="flex-1 rounded-full bg-blue-400/70" key={index} style={{ height: `${height}%` }} />
                  ))}
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-blue-600 px-3 text-sm font-black text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!resolvedAudioFilename}
                    onClick={() => playPanelOneRecording().catch(() => undefined)}
                    type="button"
                  >
                    <Play size={15} />{isPlaybackActive ? "Playing" : "Play"}
                  </button>
                  <button
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-3 text-sm font-black text-gray-900 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!resolvedAudioFilename}
                    onClick={stopPanelOneRecording}
                    type="button"
                  >
                    <Square size={14} />Stop
                  </button>
                </div>
              </div>
              <p className="mt-3 text-xs font-bold leading-5 text-gray-600">
                {resolvedAudioFilename
                  ? "This is the audio captured during intake. Hearing review does not request microphone access."
                  : "No intake audio is linked to this draft. Return to Consent & Transcript and complete a blotter recording to enable replay."}
              </p>
            </section>

            <section className="rounded-lg border border-gray-200 bg-white p-4">
              <h3 className="text-sm font-black text-gray-950">Replay Intake Recording</h3>
              {resolvedAudioFilename ? (
                <audio
                  className="mt-3 w-full"
                  controls
                  crossOrigin="use-credentials"
                  onLoadedMetadata={(event) => {
                    const mediaDuration = event.currentTarget.duration;
                    if (Number.isFinite(mediaDuration) && mediaDuration > 0 && resolvedAudioFilename) {
                      onAudioReady?.(resolvedAudioFilename, Math.ceil(mediaDuration));
                    }
                  }}
                  preload="metadata"
                  ref={hearingAudioRef}
                  src={`${API_BASE_URL}/api/audio/${encodeURIComponent(resolvedAudioFilename)}`}
                  onEnded={() => setIsPlaybackActive(false)}
                  onError={() => {
                    setIsPlaybackActive(false);
                    setPlaybackError("The saved intake recording could not be loaded. Refresh the session and try again.");
                  }}
                  onPause={() => setIsPlaybackActive(false)}
                  onPlay={() => setIsPlaybackActive(true)}
                  onTimeUpdate={(event) => setPlaybackSeconds(event.currentTarget.currentTime)}
                />
              ) : <p className="mt-2 text-xs font-bold leading-5 text-gray-500">Replay becomes available after the intake recording is uploaded.</p>}
              {playbackError && <p className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-xs font-bold leading-5 text-red-700">{playbackError}</p>}
            </section>

            <section className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-black text-gray-950">Speaker Timeline</h3>
                <span className="text-xs font-bold text-gray-500">{formatElapsedTime(Math.floor(playbackSeconds))} / {formatElapsedTime(totalDurationSeconds)}</span>
              </div>
              <div className="mt-4 space-y-3">
                {!segments.length && <p className="text-xs font-bold leading-5 text-gray-500">Speaker turns will appear after transcription or when segments are added.</p>}
                {segments.map((segment, index) => (
                  <button
                    className={`speaker-role-card ${speakerRoleClassName(segment.speaker)} block w-full rounded-md border p-3 text-left transition ${playbackSeconds >= segment.start && playbackSeconds < segment.end ? "ring-2 ring-blue-500" : "hover:brightness-95"}`}
                    key={`${index}-${segment.start}-${segment.speaker}`}
                    onClick={() => {
                      if (!hearingAudioRef.current) return;
                      hearingAudioRef.current.currentTime = segment.start;
                      hearingAudioRef.current.play().catch(() => undefined);
                    }}
                    title="Play from this speaker turn"
                    type="button"
                  >
                    <span className="flex items-center justify-between gap-2 text-xs font-black"><span className="truncate">{segment.speaker}</span><span>{formatElapsedTime(Math.floor(segment.start))}</span></span>
                    <span className="mt-2 block h-1.5 rounded-full bg-current opacity-60" style={{ width: `${Math.max(18, Math.min(100, totalDurationSeconds ? ((segment.end - segment.start) / totalDurationSeconds) * 100 : 20))}%` }} />
                  </button>
                ))}
              </div>
            </section>
          </aside>

          <div className="min-w-0 xl:relative xl:min-h-0">
          <section className="flex min-h-[640px] flex-col rounded-lg border border-gray-200 bg-white xl:absolute xl:inset-0 xl:min-h-0">
            <div className="flex flex-col gap-3 border-b border-gray-200 p-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h3 className="font-black text-gray-950">Editable Hearing Transcript</h3>
                <p className="mt-1 text-xs font-bold text-gray-500">
                  {savedTranscriptId
                    ? `Save Hearing updates transcript #${savedTranscriptId} for this case; it does not create another saved transcript.`
                    : "Edit speakers and timestamps, add or remove segments, or reuse the intake transcript."}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <AppButton disabled={!sourceTranscript.trim()} onClick={usePanelOneTranscript}><FileClock size={16} />Use Intake Transcript</AppButton>
                <AppButton onClick={addSegment}><Plus size={16} />Add Segment</AppButton>
                <AppButton disabled={isSaving || isProcessing || !transcript.trim() || (Boolean(savedTranscriptId) && !hasUnsavedChanges)} onClick={saveTranscript} tone="primary">
                  <Save size={16} />
                  {isSaving ? "Saving..." : savedTranscriptId && !hasUnsavedChanges ? `Hearing Saved to #${savedTranscriptId}` : savedTranscriptId ? "Save Hearing Changes" : "Save Hearing"}
                </AppButton>
              </div>
            </div>

            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {!segments.length && <p className="rounded-md border border-dashed border-gray-300 bg-gray-50 p-6 text-center text-sm font-bold text-gray-500">Use the intake transcript or add the first speaker segment.</p>}
              {segments.map((segment, index) => (
                <article className={`speaker-role-card ${speakerRoleClassName(segment.speaker)} rounded-md border p-4`} key={`${index}-${segment.start}`}>
                  <div className="grid gap-3 sm:grid-cols-[1fr_110px_110px_40px]">
                    <label className="text-xs font-black">Speaker<input className="mt-1 h-9 w-full rounded-md border border-current/20 bg-white px-3 text-sm text-gray-950" onChange={(event) => updateSegment(index, { speaker: event.target.value })} value={segment.speaker} /></label>
                    <label className="text-xs font-black">Start (sec)<input className="mt-1 h-9 w-full rounded-md border border-current/20 bg-white px-3 text-sm text-gray-950" min="0" onChange={(event) => updateSegment(index, { start: Number(event.target.value) })} step="0.1" type="number" value={segment.start} /></label>
                    <label className="text-xs font-black">End (sec)<input className="mt-1 h-9 w-full rounded-md border border-current/20 bg-white px-3 text-sm text-gray-950" min={segment.start} onChange={(event) => updateSegment(index, { end: Number(event.target.value) })} step="0.1" type="number" value={segment.end} /></label>
                    <button aria-label={`Delete segment ${index + 1}`} className="mt-5 grid size-9 place-items-center rounded-md border border-red-200 bg-white text-red-600 hover:bg-red-50" onClick={() => commitSegments(segments.filter((_, segmentIndex) => segmentIndex !== index))} title="Delete segment" type="button"><Trash2 size={16} /></button>
                  </div>
                  <label className="mt-3 block text-xs font-black">Statement<textarea className="mt-1 min-h-24 w-full rounded-md border border-current/20 bg-white p-3 text-sm leading-6 text-gray-950" onChange={(event) => updateSegment(index, { text: event.target.value })} value={segment.text} /></label>
                </article>
              ))}
            </div>

          </section>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-black text-gray-950">Blotter Narrative & Transcript</h2>
      <p className="mt-2 text-sm text-gray-600">
        Record live audio or upload an existing audio file for automatic transcription. The first accepted audio record is permanent for this workflow; its generated speaker segments remain editable.
      </p>

      <div className="mt-6 grid items-start gap-5 xl:grid-cols-[320px_minmax(0,1fr)] xl:items-stretch">
        <aside className="rounded-lg border border-gray-200 bg-gray-50 p-5">
          <div className="rounded-lg bg-gray-950 p-6 text-center text-white">
            <div className="mx-auto flex size-16 items-center justify-center rounded-full bg-white/10">
              <Mic aria-hidden="true" size={28} />
            </div>
            <p className="mt-6 text-sm font-bold text-gray-200">{isRecording ? "Recording in progress" : isProcessing ? "Processing audio" : recordingLocked ? "Audio record saved" : "Recorder ready"}</p>
            <p className={`mt-3 font-mono text-3xl font-black ${isRecording ? "text-red-300" : "text-white"}`}>
              {formatElapsedTime(elapsedSeconds)}
            </p>
            <p className="mt-2 text-xs leading-5 text-gray-400">Choose live microphone capture or upload WebM, WAV, MP3, M4A, or OGG audio.</p>
            <div className="mt-5 overflow-hidden rounded-md border border-white/10 bg-gray-900">
              <canvas
                aria-label="Live microphone waveform"
                className="block h-24 w-full"
                height={96}
                ref={waveformCanvasRef}
                width={520}
              />
            </div>
            {isRecording && (
              <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/10">
                <div className="h-full w-2/3 animate-pulse rounded-full bg-red-500" />
              </div>
            )}
          </div>

          <div className="mt-5 space-y-4">
            {mode === "blotter" && <div className="grid grid-cols-2 gap-2 rounded-lg border border-gray-200 bg-white p-2">
              {[
                { id: "blotter_case", label: "Blotter Recording", note: "2 speakers" },
                { id: "blotter_hearing", label: "Blotter Hearing", note: "3 speakers" },
              ].map((option) => {
                const active = recordingType === option.id;
                return (
                  <button
                    className={`rounded-md px-3 py-2 text-left text-xs font-black transition ${
                      active ? "bg-blue-600 text-white shadow-sm" : "text-gray-700 hover:bg-gray-50"
                    }`}
                    disabled={isRecording || isProcessing || isSaving || recordingLocked}
                    key={option.id}
                    onClick={() => onRecordingTypeChange(option.id as "blotter_case" | "blotter_hearing")}
                    type="button"
                  >
                    <span className="block">{option.label}</span>
                    <span className={`mt-1 block text-[11px] ${active ? "text-blue-100" : "text-gray-400"}`}>{option.note}</span>
                  </button>
                );
              })}
            </div>}

            <div className="grid grid-cols-2 gap-3">
              <AppButton
                disabled={isProcessing || isSaving || recordingLocked || (!isRecording && !workflowId)}
                onClick={isRecording ? stopRecording : startRecording}
                tone={isRecording ? "primary" : "danger"}
              >
                {isRecording ? <Pause aria-hidden="true" size={16} /> : <Play aria-hidden="true" size={16} />}
                {isRecording ? "Stop & Transcribe" : "Record Live"}
              </AppButton>
              <AppButton disabled={isRecording || isProcessing || isSaving || recordingLocked || !workflowId} onClick={chooseAudioFile}>
                <UploadCloud aria-hidden="true" size={16} />
                Upload Audio
              </AppButton>
              <input
                accept="audio/*,.webm,.wav,.mp3,.m4a,.ogg"
                aria-label="Choose a recorded audio file"
                hidden
                onChange={handleAudioFileSelected}
                ref={audioFileInputRef}
                type="file"
              />
            </div>
            {recordingLocked && (
              <p className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs font-bold leading-5 text-emerald-800">
                <Lock aria-hidden="true" className="mt-0.5 shrink-0" size={15} />
                Audio already exists for this workflow. Live recording and file upload are disabled to protect the saved record.
              </p>
            )}

            <p aria-live="polite" className="sr-only">
              {isProcessing ? "Processing audio. This can take a few minutes for longer recordings." : statusMessage}
            </p>

            {processingStage !== "idle" && (
              <div className="overflow-hidden rounded-lg border border-blue-100 bg-white shadow-sm">
                <div className="border-b border-gray-100 bg-gray-50 p-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-blue-600 text-white">
                      <FileText size={18} />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-xs font-black text-gray-950" title={processingFileName || "Recorded audio"}>
                        {processingFileName || "Recorded audio"}
                      </p>
                      <p className="mt-1 text-[11px] font-bold leading-4 text-gray-500">
                        {recordingType === "blotter_case" ? "Detecting 2 speakers" : "Detecting 3 speakers"}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    <StatusPill
                      label={processingStage === "complete" ? "Transcript Ready" : "Processing"}
                      tone={processingStage === "complete" ? "green" : "blue"}
                    />
                    {processingStage !== "complete" && <LoaderCircle className="animate-spin text-blue-600" size={17} />}
                  </div>
                </div>
                <div className="p-3">
                  <div className="flex items-center justify-between gap-3 text-[11px] font-black uppercase tracking-wide">
                    <span className={processingStage === "complete" ? "text-emerald-700" : "text-blue-700"}>
                      {processingStage === "preparing" && "Preparing recording"}
                      {processingStage === "uploading" && "Uploading audio"}
                      {processingStage === "transcribing" && "Generating transcript"}
                      {processingStage === "complete" && "Transcript generated"}
                    </span>
                    <span className="text-gray-500">{processingProgress}%</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-200">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${processingStage === "complete" ? "bg-emerald-500" : "bg-blue-600"}`}
                      style={{ width: `${processingProgress}%` }}
                    />
                  </div>
                  <p className="mt-2 text-[11px] font-bold leading-4 text-gray-500">
                    {processingStage === "complete"
                      ? "Completed — the transcript is ready to edit."
                      : `Processing time ${formatElapsedTime(processingElapsedSeconds)}`}
                  </p>
                  <div className="mt-3 space-y-2 text-[11px] font-bold text-gray-600">
                    <p className="flex items-center justify-between gap-3">
                      <span>Audio upload</span>
                      <span className={processingStage === "transcribing" || processingStage === "complete" ? "text-emerald-600" : "text-blue-600"}>
                        {processingStage === "transcribing" || processingStage === "complete" ? "Done" : "In progress"}
                      </span>
                    </p>
                    <p className="flex items-center justify-between gap-3">
                      <span>Transcript generation</span>
                      <span className={processingStage === "complete" ? "text-emerald-600" : "text-blue-600"}>
                        {processingStage === "complete" ? "Done" : processingStage === "transcribing" ? "In progress" : "Waiting"}
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            )}

            {errorMessage && <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{errorMessage}</p>}
            {warningMessage && <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{warningMessage}</p>}
          </div>
        </aside>

        <div className="min-w-0 xl:relative xl:min-h-0">
        <section className="flex min-h-[560px] flex-col rounded-lg border border-gray-200 bg-white xl:absolute xl:inset-0 xl:min-h-0">
          <div className="flex flex-col gap-3 border-b border-gray-200 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="font-black text-gray-950">Editable Transcript</h3>
              <p className="mt-1 text-xs font-bold text-gray-500">
                {segments.length
                  ? `${segments.length} color-coded segment${segments.length === 1 ? "" : "s"} · ${expectedSpeakerRoles.length}-speaker ${recordingType === "blotter_case" ? "blotter recording" : "blotter hearing"}`
                  : "Transcript segments will appear after recording"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <AppButton disabled={isProcessing || isSaving} onClick={addSegment}>
                <Plus aria-hidden="true" size={16} />
                Add Segment
              </AppButton>
              <AppButton disabled={isSaving || isProcessing || !transcript.trim() || (Boolean(savedTranscriptId) && !hasUnsavedChanges)} onClick={saveTranscript} tone="primary">
                <Save aria-hidden="true" size={16} />
                {isSaving ? "Saving..." : savedTranscriptId && !hasUnsavedChanges ? `Transcript #${savedTranscriptId} Saved` : savedTranscriptId ? "Save Transcript Changes" : "Save Transcript"}
              </AppButton>
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {!segments.length && (
              <p className="rounded-md border border-dashed border-gray-300 bg-gray-50 p-6 text-center text-sm font-bold text-gray-500">
                Record the blotter or add the first speaker segment to begin editing.
              </p>
            )}
            {segments.map((segment, index) => (
              <article className={`speaker-role-card ${speakerRoleClassName(segment.speaker)} rounded-md border p-4`} key={`${index}-${segment.start}`}>
                <div className="grid gap-3 sm:grid-cols-[minmax(180px,1fr)_110px_110px_40px]">
                  <label className="text-xs font-black">
                    Speaker
                    <select
                      className="mt-1 h-9 w-full rounded-md border border-current/20 bg-white px-3 text-sm text-gray-950"
                      disabled={isSaving}
                      onChange={(event) => updateSegment(index, { speaker: event.target.value })}
                      value={segment.speaker}
                    >
                      {!expectedSpeakerRoles.includes(segment.speaker) && <option value={segment.speaker}>{segment.speaker}</option>}
                      {expectedSpeakerRoles.map((speaker) => <option key={speaker} value={speaker}>{speaker}</option>)}
                    </select>
                  </label>
                  <label className="text-xs font-black">
                    Start (sec)
                    <input className="mt-1 h-9 w-full rounded-md border border-current/20 bg-white px-3 text-sm text-gray-950" disabled={isSaving} min="0" onChange={(event) => updateSegment(index, { start: Number(event.target.value) })} step="0.1" type="number" value={segment.start} />
                  </label>
                  <label className="text-xs font-black">
                    End (sec)
                    <input className="mt-1 h-9 w-full rounded-md border border-current/20 bg-white px-3 text-sm text-gray-950" disabled={isSaving} min={segment.start} onChange={(event) => updateSegment(index, { end: Number(event.target.value) })} step="0.1" type="number" value={segment.end} />
                  </label>
                  <button aria-label={`Delete segment ${index + 1}`} className="mt-5 grid size-9 place-items-center rounded-md border border-red-200 bg-white text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50" disabled={isSaving} onClick={() => commitSegments(segments.filter((_, segmentIndex) => segmentIndex !== index))} title="Delete segment" type="button">
                    <Trash2 size={16} />
                  </button>
                </div>
                <label className="mt-3 block text-xs font-black">
                  Statement
                  <textarea className="mt-1 min-h-24 w-full rounded-md border border-current/20 bg-white p-3 text-sm leading-6 text-gray-950" disabled={isSaving} onChange={(event) => updateSegment(index, { text: event.target.value })} value={segment.text} />
                </label>
              </article>
            ))}
          </div>

          {isVawcTranscript ? (
            <div className="mx-4 mb-4 flex items-start gap-3 rounded-lg border border-red-300 bg-red-50 p-4 text-red-950" role="alert">
              <AlertTriangle className="mt-0.5 shrink-0 text-red-600" size={21} />
              <div>
                <p className="font-black">VAWC or child-abuse warning detected</p>
                <p className="mt-1 text-sm font-bold leading-6">
                  Trigger {matchedVawcKeywords.length === 1 ? "word" : "words"}: {matchedVawcKeywords.join(", ")}. Case Facts & Decision requires an authorized official to confirm the protected-case indicator. Normal mediation must not continue automatically.
                </p>
              </div>
            </div>
          ) : (
            <p className="px-4 pb-4 text-xs font-bold text-amber-600">Case Facts & Decision will classify the case from this transcript.</p>
          )}
        </section>
        </div>
      </div>
    </div>
  );
}

function WorkflowTab({
  currentUser,
  navigationGuardRef,
  onOpenCases,
}: {
  currentUser: CurrentUser;
  navigationGuardRef: React.MutableRefObject<WorkflowNavigationGuard | null>;
  onOpenCases: () => void;
}) {
  const [activeStep, setActiveStep] = useState(1);
  const [maxUnlockedStep, setMaxUnlockedStep] = useState(1);
  const [workflow, setWorkflow] = useState<WorkflowState>(initialWorkflow);
  const [consentFile, setConsentFile] = useState<File | null>(null);
  const [consentPartyType, setConsentPartyType] = useState("general");
  const [consentUploadMessage, setConsentUploadMessage] = useState("");
  const [isConsentUploading, setIsConsentUploading] = useState(false);
  const [workflowId, setWorkflowId] = useState("");
  const [, setDraftRevision] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<WorkflowDraftRecord[]>([]);
  const [draftSearchInput, setDraftSearchInput] = useState("");
  const [draftQuery, setDraftQuery] = useState("");
  const [draftPage, setDraftPage] = useState(1);
  const [draftGoToInput, setDraftGoToInput] = useState("");
  const [draftTotal, setDraftTotal] = useState(0);
  const [draftTotalPages, setDraftTotalPages] = useState(0);
  const [isLoadingDrafts, setIsLoadingDrafts] = useState(false);
  const [draftMessage, setDraftMessage] = useState("");
  const [isCreatingDraft, setIsCreatingDraft] = useState(false);
  const [isDraftMutating, setIsDraftMutating] = useState(false);
  const [isDeletingDraft, setIsDeletingDraft] = useState(false);
  const [isSwitchingDraft, setIsSwitchingDraft] = useState(false);
  const [pendingDraftSwitchId, setPendingDraftSwitchId] = useState("");
  const [draftSwitchMessage, setDraftSwitchMessage] = useState("");
  const [isRunningPanel3, setIsRunningPanel3] = useState(false);
  const [isAdvancing, setIsAdvancing] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isSavingOutcome, setIsSavingOutcome] = useState(false);
  const [isProcessingPhase3, setIsProcessingPhase3] = useState(false);
  const [isRecorderBusy, setIsRecorderBusy] = useState(false);
  const [phase3Message, setPhase3Message] = useState("");
  const [finalizeMessage, setFinalizeMessage] = useState("");
  const [finalizeMessageTone, setFinalizeMessageTone] = useState<"blue" | "green" | "red">("blue");
  const [generatedPacket, setGeneratedPacket] = useState<WorkflowFormPacket | null>(null);
  const [finalizedCaseConfirmation, setFinalizedCaseConfirmation] = useState<{
    caseId: string;
    outcome: string;
  } | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState("");
  const [savedDraftFingerprint, setSavedDraftFingerprint] = useState("");
  const workflowIdRef = useRef("");
  const draftRevisionRef = useRef<number | null>(null);
  const draftMutationTailRef = useRef<Promise<void>>(Promise.resolve());
  const pendingDraftMutationCountRef = useRef(0);
  const draftListInitializedRef = useRef(false);
  const workflowSelectionVersionRef = useRef(0);
  const draftOpenRequestIdRef = useRef(0);
  const preliminaryVawcKeywords = detectVawcKeywords(workflow.transcript);
  const preliminaryVawcWarning = preliminaryVawcKeywords.length > 0;
  const confirmedVawcPath = isVawcAnalysis(workflow.phase2Analysis);
  const referralPath = requiresReferralPath(workflow.phase2Analysis)
    || workflow.phase3ReferralRequired
    || isReferralRecommendation(workflow.phase3RecommendedRoute)
    || Boolean(workflow.referralResolution);
  const skippedPanelIds = workflow.skippedPanelIds.length ? workflow.skippedPanelIds : skippedPanelsForAnalysis(workflow.phase2Analysis);
  const allowedOutcomeOptions = useMemo(
    () => workflowOutcomeOptions(referralPath, confirmedVawcPath, workflow.referralResolution?.status),
    [confirmedVawcPath, referralPath, workflow.referralResolution?.status],
  );
  const isWorkflowOperationBusy = isDraftMutating
    || isAdvancing
    || isConsentUploading
    || isRunningPanel3
    || isFinalizing
    || isSavingOutcome
    || isProcessingPhase3
    || isRecorderBusy;
  const isDraftNavigationDisabled = isLoadingDrafts || isSwitchingDraft || isWorkflowOperationBusy;
  const draftPageItems = useMemo<Array<number | "start-ellipsis" | "end-ellipsis">>(() => {
    if (draftTotalPages <= 7) {
      return Array.from({ length: draftTotalPages }, (_, index) => index + 1);
    }
    if (draftPage <= 4) {
      return [1, 2, 3, 4, 5, "end-ellipsis", draftTotalPages];
    }
    if (draftPage >= draftTotalPages - 3) {
      return [1, "start-ellipsis", ...Array.from({ length: 5 }, (_, index) => draftTotalPages - 4 + index)];
    }
    return [1, "start-ellipsis", draftPage - 1, draftPage, draftPage + 1, "end-ellipsis", draftTotalPages];
  }, [draftPage, draftTotalPages]);

  useEffect(() => {
    if (!workflow.completed && !allowedOutcomeOptions.includes(workflow.outcome)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWorkflow((current) => ({ ...current, outcome: allowedOutcomeOptions[0] }));
    }
  }, [allowedOutcomeOptions, workflow.completed, workflow.outcome]);

  const applyDraftIdentity = (nextWorkflowId: string, nextRevision: number | null) => {
    workflowIdRef.current = nextWorkflowId;
    draftRevisionRef.current = nextRevision;
    setWorkflowId(nextWorkflowId);
    setDraftRevision(nextRevision);
  };

  const applyDraftRevision = (nextRevision: number) => {
    draftRevisionRef.current = nextRevision;
    setDraftRevision(nextRevision);
  };

  const queueDraftMutation = <T,>(operation: () => Promise<T>): Promise<T> => {
    pendingDraftMutationCountRef.current += 1;
    setIsDraftMutating(true);
    const queued = draftMutationTailRef.current
      .catch(() => undefined)
      .then(operation);
    draftMutationTailRef.current = queued.then(() => undefined, () => undefined);
    return queued.finally(() => {
      pendingDraftMutationCountRef.current = Math.max(0, pendingDraftMutationCountRef.current - 1);
      if (pendingDraftMutationCountRef.current === 0) {
        setIsDraftMutating(false);
      }
    });
  };

  const updateWorkflow = <K extends keyof WorkflowState>(key: K, value: WorkflowState[K]) => {
    setWorkflow((current) => ({ ...current, [key]: value }));
  };

  const updateWorkflowFromDraft = (draft: WorkflowDraftRecord) => {
    workflowSelectionVersionRef.current += 1;
    const payload = draft.payload ?? {};
    const payloadCaseInformation = (payload.caseInformation as Partial<CaseInformation> | undefined) ?? {};
    const canonicalCaseId = draft.case_id || payloadCaseInformation.case_id || "";
    const hasAnalysis = Boolean(draft.case_analysis_id || payload.phase2Analysis);
    const restoredStep = draft.status === "completed" ? 7 : Math.min(7, Math.max(1, draft.active_step || (hasAnalysis ? 2 : 1)));
    const restoredMaxStep = Math.min(7, Math.max(restoredStep, draft.max_unlocked_step));
    const restoredWorkflow: WorkflowState = {
      ...initialWorkflow,
      ...payload,
      caseInformation: {
        ...defaultCaseInformation,
        ...payloadCaseInformation,
        case_id: canonicalCaseId,
      },
      consentFiles: Array.isArray(payload.consentFiles)
        ? (payload.consentFiles as ConsentFileRecord[]).map((item) => ({ ...item }))
        : [],
      transcriptSegments: Array.isArray(payload.transcriptSegments)
        ? (payload.transcriptSegments as TranscriptSegment[]).map((item) => ({ ...item }))
        : [],
      rawTranscriptSegments: Array.isArray(payload.rawTranscriptSegments)
        ? (payload.rawTranscriptSegments as TranscriptSegment[]).map((item) => ({ ...item }))
        : [],
      hearingTranscriptSegments: Array.isArray(payload.hearingTranscriptSegments)
        ? (payload.hearingTranscriptSegments as TranscriptSegment[]).map((item) => ({ ...item }))
        : [],
      rawHearingTranscriptSegments: Array.isArray(payload.rawHearingTranscriptSegments)
        ? (payload.rawHearingTranscriptSegments as TranscriptSegment[]).map((item) => ({ ...item }))
        : [],
      phase2Analysis: (payload.phase2Analysis as AnalyzeCaseResponse | null | undefined) ?? null,
      phase2AnalysisId: draft.case_analysis_id ?? (payload.phase2AnalysisId as number | null | undefined) ?? null,
      // draft.case_id exists as soon as a blank intake draft is created.  It
      // must not masquerade as a completed Phase 2 record; only restore the
      // backend case link when analysis actually exists.
      phase2CaseId: (payload.phase2CaseId as string | undefined)
        || (draft.case_analysis_id ? draft.case_id : ""),
      transcriptId: draft.transcript_id ?? (payload.transcriptId as number | null | undefined) ?? null,
      skippedPanelIds: Array.isArray(payload.skippedPanelIds) ? (payload.skippedPanelIds as number[]) : [],
      phase3Processed: Boolean(payload.phase3Processed),
    };
    setWorkflow(restoredWorkflow);
    setConsentFile(null);
    setConsentUploadMessage("");
    setActiveStep(restoredStep);
    setMaxUnlockedStep(restoredMaxStep);
    applyDraftIdentity(draft.workflow_id, draft.revision);
    setSavedDraftFingerprint(workflowDraftFingerprint(restoredWorkflow, restoredStep, restoredMaxStep));
    setLastSavedAt(draft.updated_at);
    setGeneratedPacket((current) => {
      if (draft.phase4_packet) {
        return draft.phase4_packet;
      }
      if (!restoredWorkflow.phase4PacketId || current?.id !== restoredWorkflow.phase4PacketId) {
        return null;
      }
      return current;
    });
    setFinalizeMessage("");
    setFinalizeMessageTone("blue");
  };

  const loadDrafts = async ({
    query = draftQuery,
    page = draftPage,
  }: { query?: string; page?: number } = {}) => {
    setIsLoadingDrafts(true);
    try {
      const response = await axios.get<WorkflowDraftPage>(`${API_BASE_URL}/api/workflow/drafts`, {
        params: { status: "active", q: query, page, page_size: 1 },
      });
      setDrafts(response.data.items);
      setDraftPage(response.data.page);
      setDraftTotal(response.data.total);
      setDraftTotalPages(response.data.total_pages);
      setDraftGoToInput("");
      return response.data;
    } finally {
      setIsLoadingDrafts(false);
    }
  };

  const clearWorkflowSelection = () => {
    workflowSelectionVersionRef.current += 1;
    setWorkflow({
      ...initialWorkflow,
      caseInformation: { ...defaultCaseInformation },
      consentFiles: [],
      transcriptSegments: [],
      hearingTranscriptSegments: [],
      skippedPanelIds: [],
    });
    applyDraftIdentity("", null);
    setSavedDraftFingerprint("");
    setActiveStep(1);
    setMaxUnlockedStep(1);
    setLastSavedAt("");
    setGeneratedPacket(null);
    setFinalizeMessage("");
    setFinalizeMessageTone("blue");
  };

  const openSavedDraft = async (selectedWorkflowId: string) => {
    if (!selectedWorkflowId || selectedWorkflowId === workflowIdRef.current) {
      return;
    }
    setIsSwitchingDraft(true);
    setDraftMessage("");
    const requestId = draftOpenRequestIdRef.current + 1;
    draftOpenRequestIdRef.current = requestId;
    try {
      const response = await axios.get<WorkflowDraftRecord>(`${API_BASE_URL}/api/workflow/drafts/${selectedWorkflowId}`);
      if (draftOpenRequestIdRef.current !== requestId) {
        return;
      }
      updateWorkflowFromDraft(response.data);
      setDraftMessage("");
    } catch (error) {
      if (draftOpenRequestIdRef.current !== requestId) {
        return;
      }
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setDraftMessage(detail ?? "Unable to select this saved draft.");
    } finally {
      if (draftOpenRequestIdRef.current === requestId) {
        setIsSwitchingDraft(false);
      }
    }
  };

  const deleteDraft = async (targetWorkflowId: string, targetLabel: string) => {
    if (!targetWorkflowId) {
      setDraftMessage("Select a draft to delete.");
      return;
    }
    if (!window.confirm(`Delete ${targetLabel}? This removes the workflow draft but keeps separately saved transcripts and case records.`)) {
      return;
    }

    setIsDeletingDraft(true);
    setDraftMessage("");
    try {
      await axios.delete(`${API_BASE_URL}/api/workflow/drafts/${targetWorkflowId}`);
      let remainingPage = await loadDrafts();
      const deletedCurrentDraft = targetWorkflowId === workflowIdRef.current;

      if (deletedCurrentDraft && remainingPage.items.length === 0 && (remainingPage.total === 0 || draftQuery)) {
        setDraftSearchInput("");
        setDraftQuery("");
        remainingPage = await loadDrafts({ query: "", page: 1 });
      }

      if (deletedCurrentDraft) {
        const nextDraft = remainingPage.items[0];
        if (nextDraft) {
          updateWorkflowFromDraft(nextDraft);
          const nextDraftLabel = nextDraft.case_id || `Draft ${nextDraft.workflow_id.slice(0, 8)}`;
          setDraftMessage(`${targetLabel} deleted. ${nextDraftLabel} is now selected.`);
        } else {
          clearWorkflowSelection();
          setDraftMessage(`${targetLabel} deleted. Create a new case when you are ready.`);
        }
      } else {
        setDraftMessage(`${targetLabel} deleted. Separately saved case and transcript records were kept.`);
      }
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setDraftMessage(detail ?? "Unable to delete the selected draft.");
    } finally {
      setIsDeletingDraft(false);
    }
  };

  const createDraft = async () => {
    setIsCreatingDraft(true);
    const freshWorkflow: WorkflowState = {
      ...initialWorkflow,
      caseInformation: { ...defaultCaseInformation, case_id: "" },
      consentFiles: [],
      transcriptSegments: [],
      rawTranscriptSegments: [],
      hearingTranscriptSegments: [],
      rawHearingTranscriptSegments: [],
      skippedPanelIds: [],
    };
    try {
      const response = await axios.post<WorkflowDraftRecord>(`${API_BASE_URL}/api/workflow/drafts`, {
        active_step: 1,
        max_unlocked_step: 1,
        payload: cleanWorkflowPayload(freshWorkflow),
      });
      updateWorkflowFromDraft(response.data);
      setDraftSearchInput("");
      setDraftQuery("");
      await loadDrafts({ query: "", page: LAST_DRAFT_PAGE }).catch(() => undefined);
      setDraftMessage(`New blotter ${response.data.payload.caseInformation?.case_id ?? "draft"} created.`);
      return response.data;
    } finally {
      setIsCreatingDraft(false);
    }
  };

  const saveDraft = async (
    nextWorkflow = workflow,
    nextActiveStep = activeStep,
    nextMaxUnlockedStep = maxUnlockedStep,
    status = "active"
  ) => {
    const selectedWorkflowId = workflowIdRef.current;
    if (!selectedWorkflowId || draftRevisionRef.current === null) {
      return null;
    }
    return queueDraftMutation(async () => {
      if (workflowIdRef.current !== selectedWorkflowId) {
        return null;
      }
      const selectedRevision = draftRevisionRef.current;
      if (selectedRevision === null) {
        return null;
      }
      try {
        const payload = cleanWorkflowPayload(nextWorkflow);
        const response = await axios.patch<WorkflowDraftRecord>(`${API_BASE_URL}/api/workflow/drafts/${selectedWorkflowId}`, {
          revision: selectedRevision,
          active_step: nextActiveStep,
          max_unlocked_step: nextMaxUnlockedStep,
          status,
          case_id: payload.phase2CaseId || payload.caseInformation.case_id,
          transcript_id: payload.transcriptId,
          case_analysis_id: payload.phase2AnalysisId,
          payload,
        });
        if (workflowIdRef.current === selectedWorkflowId) {
          applyDraftRevision(response.data.revision);
          setSavedDraftFingerprint(workflowDraftFingerprint(nextWorkflow, nextActiveStep, nextMaxUnlockedStep));
          setLastSavedAt(response.data.updated_at);
        }
        setDrafts((current) => current.map((draft) => draft.workflow_id === response.data.workflow_id ? response.data : draft));
        setDraftMessage(status === "completed" ? "Workflow completed." : "Draft saved.");
        return response.data;
      } catch (error) {
        const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
        setDraftMessage(detail ?? "Draft save failed. Reload the Workflow section to restore the latest saved version.");
        return null;
      }
    });
  };

  const isDraftDirty = Boolean(
    workflowId
    && savedDraftFingerprint
    && workflowDraftFingerprint(workflow, activeStep, maxUnlockedStep) !== savedDraftFingerprint
  );

  useEffect(() => {
    if (!isDraftDirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isDraftDirty]);

  useEffect(() => {
    const guard: WorkflowNavigationGuard = {
      hasUnsavedChanges: () => isDraftDirty,
      saveDraft: async () => Boolean(await saveDraft()),
      draftLabel: () => workflow.caseInformation.case_id || `Draft ${workflowId.slice(0, 8)}`,
    };
    navigationGuardRef.current = guard;
    return () => {
      if (navigationGuardRef.current === guard) {
        navigationGuardRef.current = null;
      }
    };
  });

  const requestDraftSwitch = (selectedWorkflowId: string) => {
    if (!selectedWorkflowId || selectedWorkflowId === workflowId) {
      return;
    }
    if (isWorkflowOperationBusy || isSwitchingDraft) {
      setDraftMessage("Wait for the current workflow operation to finish before changing draft pages.");
      return;
    }
    if (isDraftDirty) {
      setPendingDraftSwitchId(selectedWorkflowId);
      setDraftSwitchMessage("");
      return;
    }
    openSavedDraft(selectedWorkflowId).catch(() => undefined);
  };

  const selectDraftPage = async ({
    query = draftQuery,
    page,
  }: { query?: string; page: number }) => {
    if (isWorkflowOperationBusy || isSwitchingDraft || isLoadingDrafts) {
      setDraftMessage("Wait for the current workflow operation to finish before changing draft pages.");
      return null;
    }
    const selectedPage = await loadDrafts({ query, page });
    const selectedDraft = selectedPage.items[0];
    if (selectedDraft) {
      requestDraftSwitch(selectedDraft.workflow_id);
    }
    return selectedPage;
  };

  const goToDraftPage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const requestedPage = Number(draftGoToInput);
    if (!Number.isInteger(requestedPage) || requestedPage < 1 || requestedPage > draftTotalPages) {
      setDraftMessage(`Enter a page number from 1 to ${Math.max(1, draftTotalPages)}.`);
      return;
    }
    selectDraftPage({ page: requestedPage }).catch(() => setDraftMessage(`Unable to load drafts page ${requestedPage}.`));
  };

  const switchDraftWithoutSaving = () => {
    const selectedWorkflowId = pendingDraftSwitchId;
    setPendingDraftSwitchId("");
    setDraftSwitchMessage("");
    openSavedDraft(selectedWorkflowId).catch(() => undefined);
  };

  const saveAndSwitchDraft = async () => {
    const selectedWorkflowId = pendingDraftSwitchId;
    setDraftSwitchMessage("");
    const saved = await saveDraft();
    if (!saved) {
      setDraftSwitchMessage("The current draft could not be saved. Stay here and try again.");
      return;
    }
    setPendingDraftSwitchId("");
    await openSavedDraft(selectedWorkflowId);
  };

  const linkIntakeTranscriptToDraft = async (
    result: SaveTranscriptResponse,
    savedContent: string,
    savedSegments: TranscriptSegment[],
  ) => {
    const transcriptId = result.id;
    if (!transcriptId) {
      setDraftMessage("The transcript was saved without an ID, so it could not be linked to this workflow.");
      throw new Error("The transcript was saved without an ID, so it could not be linked to this workflow.");
    }

    const nextWorkflow = {
      ...workflow,
      transcript: savedContent,
      transcriptId,
      transcriptDirty: false,
      transcriptSegments: savedSegments,
    };
    setWorkflow(nextWorkflow);
    const savedDraft = await saveDraft(nextWorkflow, activeStep, maxUnlockedStep);
    if (!savedDraft) {
      throw new Error(`Transcript #${transcriptId} was saved, but the workflow link failed. Select Continue to retry the workflow link.`);
    }
    setDraftMessage(
      result.operation === "updated"
        ? `Transcript #${transcriptId} updated for this workflow. Saved Transcripts will show the latest edited version.`
        : `Transcript #${transcriptId} saved and linked to this workflow.`,
    );
  };

  const linkHearingTranscriptToDraft = async (
    result: SaveTranscriptResponse,
    savedContent: string,
    savedSegments: TranscriptSegment[],
  ) => {
    const transcriptId = result.id;
    if (!transcriptId || transcriptId !== workflow.transcriptId) {
      throw new Error("The hearing did not update this workflow's canonical transcript. Refresh the draft and try again.");
    }

    const hearingSavedAt = new Date().toISOString();
    const nextWorkflow: WorkflowState = {
      ...workflow,
      // The hearing becomes the latest human-reviewed version used by later
      // NER/routing stages, while rawTranscript/rawTranscriptSegments remain
      // the immutable Stage 1 ASR reference.
      transcript: savedContent,
      transcriptId,
      transcriptDirty: false,
      transcriptSegments: savedSegments,
      hearingTranscript: savedContent,
      hearingTranscriptId: transcriptId,
      hearingTranscriptSegments: savedSegments,
      hearingRecorded: true,
      hearingSavedAt,
      phase3Processed: false,
      phase3ReferralRequired: false,
      phase3RecommendedRoute: "",
      symbolicConfirmed: false,
      phase4PacketId: null,
      referralResolution: null,
    };
    setWorkflow(nextWorkflow);
    const savedDraft = await saveDraft(nextWorkflow, activeStep, maxUnlockedStep);
    if (!savedDraft) {
      throw new Error(`Transcript #${transcriptId} was updated, but the hearing workflow state could not be saved. Refresh the draft before continuing.`);
    }
    setDraftMessage(`Hearing saved to transcript #${transcriptId}. The existing edited transcript was replaced; no duplicate was created.`);
  };

  const invalidatePhase2 = (changes: Partial<WorkflowState>) => {
    setWorkflow((current) => ({
      ...current,
      ...changes,
      analysisConfirmed: false,
      phase2Analysis: null,
      phase2AnalysisId: null,
      phase2CaseId: "",
      skippedPanelIds: [],
      phase3Processed: false,
      phase3ReferralRequired: false,
      phase3RecommendedRoute: "",
      symbolicConfirmed: false,
      phase4PacketId: null,
      outcome: "Amicable Settlement Reached",
      finalizedAt: "",
      completed: false,
      caseCancelled: false,
      cancellationReason: "",
      cancelledAt: "",
      cancelledBy: "",
      officialDecision: "",
      referralResolution: null,
    }));
    setGeneratedPacket(null);
    setFinalizeMessage("");
    setFinalizeMessageTone("blue");
    setMaxUnlockedStep((current) => Math.min(current, 2));
  };

  useEffect(() => {
    let cancelled = false;
    const loadLatestDraft = async () => {
      const selectionVersion = workflowSelectionVersionRef.current;
      try {
        const activeDraftPage = await loadDrafts({ query: "", page: LAST_DRAFT_PAGE });
        if (cancelled || workflowSelectionVersionRef.current !== selectionVersion) return;
        draftListInitializedRef.current = true;
        if (activeDraftPage.items[0]) {
          updateWorkflowFromDraft(activeDraftPage.items[0]);
          const latestDraftLabel = activeDraftPage.items[0].case_id || `Draft ${activeDraftPage.items[0].workflow_id.slice(0, 8)}`;
          setDraftMessage(`${latestDraftLabel}, the newest created saved draft, was restored.`);
        } else {
          clearWorkflowSelection();
          setDraftMessage("No saved draft is selected. Select New Case to begin a workflow.");
        }
      } catch {
        if (!cancelled) {
          setDraftMessage("Unable to initialize workflow draft persistence.");
        }
      }
    };
    loadLatestDraft();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!draftListInitializedRef.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      const nextQuery = draftSearchInput.trim();
      setDraftQuery(nextQuery);
      selectDraftPage({ query: nextQuery, page: 1 }).catch(() => {
        setDraftMessage("Unable to search saved drafts.");
      });
    }, 300);
    return () => window.clearTimeout(timer);
    // selectDraftPage intentionally reads the latest picker state through explicit arguments.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftSearchInput]);

  useEffect(() => {
    if (!workflow.phase2CaseId || !workflow.phase4PacketId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setGeneratedPacket(null);
      return;
    }
    axios
      .get<WorkflowFormPacket[]>(`${API_BASE_URL}/api/phase4/packets/${workflow.phase2CaseId}`)
      .then((response) => {
        setGeneratedPacket(response.data.find((packet) => packet.id === workflow.phase4PacketId) ?? null);
      })
      .catch(() => setGeneratedPacket(null));
  }, [workflow.phase2CaseId, workflow.phase4PacketId]);

  const uploadConsentFile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!consentFile) {
      setConsentUploadMessage("Choose a consent file before uploading.");
      return;
    }

    setIsConsentUploading(true);
    setConsentUploadMessage("");
    try {
      const data = new FormData();
      data.append("file", consentFile);
      data.append("party_type", consentPartyType);
      const response = await axios.post<ConsentFileRecord>(`${API_BASE_URL}/api/workflow/consent-files`, data, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setWorkflow((current) => ({
        ...current,
        consentFiles: [response.data, ...current.consentFiles],
      }));
      setConsentFile(null);
      setConsentUploadMessage("Consent file uploaded and linked to this workflow.");
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setConsentUploadMessage(detail ?? "Unable to upload consent file.");
    } finally {
      setIsConsentUploading(false);
    }
  };

  const runPanel3Analysis = async () => {
    if (!workflowIdRef.current || draftRevisionRef.current === null) {
      setDraftMessage("Workflow draft is still initializing. Try again in a moment.");
      return;
    }
    if (!workflow.transcript.trim()) {
      setDraftMessage("Complete the intake transcript before running the backend decision.");
      return;
    }
    if (!workflow.caseInformation.dispute_category) {
      setDraftMessage("Select a dispute category before running the backend decision.");
      return;
    }
    if (preliminaryVawcWarning && !workflow.caseInformation.has_vawc_or_child_abuse_indicators) {
      setDraftMessage("Confirm the VAWC or child-abuse indicator before running the protected decision branch.");
      return;
    }

    setIsRunningPanel3(true);
    setDraftMessage("");
    try {
      const response = await queueDraftMutation(async () => {
        const selectedWorkflowId = workflowIdRef.current;
        const selectedRevision = draftRevisionRef.current;
        if (!selectedWorkflowId || selectedRevision === null) {
          throw new Error("Workflow draft is not ready.");
        }
        const result = await axios.post<WorkflowDraftRecord & { analysis: AnalyzeCaseResponse }>(
          `${API_BASE_URL}/api/workflow/drafts/${selectedWorkflowId}/phase2-analysis`,
          {
            revision: selectedRevision,
            transcript_id: workflow.transcriptId,
            transcript_text: workflow.transcript,
            case_information: toApiCaseInformation(workflow.caseInformation),
          }
        );
        applyDraftRevision(result.data.revision);
        return result;
      });
      const analysis = response.data.analysis;
      const savedCaseId = response.data.case_id || analysis.case_information.case_id;
      updateWorkflowFromDraft(response.data);
      setWorkflow((current) => ({
        ...current,
        outcome: isVawcAnalysis(analysis)
          ? "Referred to WCPD / PNP"
          : current.outcome.startsWith("Referred to") || current.outcome.startsWith("Emergency Protection")
            ? "Amicable Settlement Reached"
            : current.outcome,
      }));
      setDrafts((current) => current.map((draft) => draft.workflow_id === response.data.workflow_id ? response.data : draft));
      setDraftMessage(
        savedCaseId
          ? `Backend Phase 2 decision saved and connected to case ${savedCaseId}.`
          : "Backend Phase 2 decision saved to this draft."
      );
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setDraftMessage(detail ?? "Backend Phase 2 analysis failed.");
    } finally {
      setIsRunningPanel3(false);
    }
  };

  const ensureTranscriptSaved = async () => {
    if (workflow.transcriptId && !workflow.transcriptDirty) {
      return { transcriptId: workflow.transcriptId, nextWorkflow: workflow };
    }
    const savedSegments = workflow.transcriptSegments.length
      ? workflow.transcriptSegments
      : transcriptToSegments(workflow.transcript);
    const savedContent = formatTranscript(savedSegments) || workflow.transcript;
    const response = await axios.post<SaveTranscriptResponse>(`${API_BASE_URL}/save-transcript`, {
      content: savedContent,
      transcript_id: workflow.transcriptId ?? undefined,
      workflow_id: workflowIdRef.current || undefined,
      case_id: workflow.phase2CaseId || workflow.caseInformation.case_id || undefined,
      save_context: "intake",
      segments: workflow.rawTranscriptSegments.length ? workflow.rawTranscriptSegments : workflow.transcriptSegments,
      edited_segments: savedSegments,
      recording_type: workflow.recordingType,
    });
    if (!response.data.id) {
      throw new Error("The backend did not return a transcript ID.");
    }
    await linkIntakeTranscriptToDraft(response.data, savedContent, savedSegments);
    return {
      transcriptId: response.data.id,
      nextWorkflow: {
        ...workflow,
        transcript: savedContent,
        transcriptId: response.data.id,
        transcriptDirty: false,
        transcriptSegments: savedSegments,
      },
    };
  };

  const generateForms = async () => {
    if (!workflowIdRef.current || draftRevisionRef.current === null || !workflow.phase2CaseId) {
      setFinalizeMessage("Run the requirements and XAI decision before generating forms.");
      setFinalizeMessageTone("red");
      return;
    }
    setIsFinalizing(true);
    setFinalizeMessage("");
    setFinalizeMessageTone("blue");
    try {
      const response = await queueDraftMutation(async () => {
        const selectedWorkflowId = workflowIdRef.current;
        const selectedRevision = draftRevisionRef.current;
        if (!selectedWorkflowId || selectedRevision === null) {
          throw new Error("Workflow draft is not ready.");
        }
        const result = await axios.post<WorkflowFinalizeResponse>(
          `${API_BASE_URL}/api/workflow/drafts/${selectedWorkflowId}/generate-forms`,
          {
            revision: selectedRevision,
            generated_by: "Barangay Official",
            regenerate: Boolean(generatedPacket),
          }
        );
        applyDraftRevision(result.data.revision);
        return result;
      });
      updateWorkflowFromDraft(response.data);
      setGeneratedPacket(response.data.phase4_packet);
      setFinalizeMessage("The required KP forms were generated. Review the packet, select the final outcome, then save and finalize the case.");
      setFinalizeMessageTone("green");
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setFinalizeMessage(detail ?? "Unable to finish the blotter and generate KP forms.");
      setFinalizeMessageTone("red");
    } finally {
      setIsFinalizing(false);
    }
  };

  const finalizeOutcome = async () => {
    if (!workflowIdRef.current || draftRevisionRef.current === null || !generatedPacket) {
      setFinalizeMessage("Generate the required KP forms before finalizing the case.");
      setFinalizeMessageTone("red");
      return;
    }
    setIsSavingOutcome(true);
    setFinalizeMessage("");
    setFinalizeMessageTone("blue");
    try {
      const response = await queueDraftMutation(async () => {
        const selectedWorkflowId = workflowIdRef.current;
        const selectedRevision = draftRevisionRef.current;
        if (!selectedWorkflowId || selectedRevision === null) {
          throw new Error("Workflow draft is not ready.");
        }
        const result = await axios.post<WorkflowFinalizeResponse>(
          `${API_BASE_URL}/api/workflow/drafts/${selectedWorkflowId}/finalize-outcome`,
          {
            revision: selectedRevision,
            outcome: workflow.outcome,
          },
        );
        applyDraftRevision(result.data.revision);
        return result;
      });
      const finalizedCaseId = response.data.case_id;
      const finalizedOutcome = workflow.outcome;
      setFinalizeMessage(`Case ${response.data.case_id} was finalized as “${workflow.outcome}” and saved to Cases & Records.`);
      setFinalizeMessageTone("green");
      await loadDrafts().catch(() => undefined);
      clearWorkflowSelection();
      setDraftMessage("The finalized case has been closed. Create a new case or view an existing record when you are ready.");
      setFinalizedCaseConfirmation({
        caseId: finalizedCaseId,
        outcome: finalizedOutcome,
      });
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setFinalizeMessage(detail ?? "Unable to save the final case outcome.");
      setFinalizeMessageTone("red");
    } finally {
      setIsSavingOutcome(false);
    }
  };

  const runPhase3Processing = async () => {
    if (!workflow.phase2CaseId) {
      setPhase3Message("Complete Case Facts & Decision before running analysis.");
      return;
    }
    setIsProcessingPhase3(true);
    setPhase3Message("");
    try {
      const response = await axios.post<WorkflowPhase3Response>(`${API_BASE_URL}/api/phase3/process-case/${workflow.phase2CaseId}`);
      const recommendedRoute = response.data.phase3.sensitive_routing?.recommended_route
        || response.data.phase3.final_recommended_action
        || "";
      const hasReferralRecord = response.data.phase3.referrals.some((referral) => referral.status !== "cancelled");
      const nextWorkflow = {
        ...workflow,
        phase3Processed: true,
        phase3ReferralRequired: hasReferralRecord || isReferralRecommendation(recommendedRoute),
        phase3RecommendedRoute: recommendedRoute,
        symbolicConfirmed: false,
      };
      setWorkflow(nextWorkflow);
      const saved = await saveDraft(nextWorkflow, 5, Math.max(maxUnlockedStep, 5));
      if (!saved) {
        throw new Error("Analysis finished, but the workflow draft could not be saved.");
      }
      setPhase3Message("");
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setPhase3Message(detail ?? "Unable to run preprocessing and Phase 3 analysis.");
    } finally {
      setIsProcessingPhase3(false);
    }
  };

  const resolveReferralWorkflow = async (
    referralId: number,
    action: "complete_and_advance" | "cancel_referral",
    reason = "",
  ) => {
    try {
      const response = await queueDraftMutation(async () => {
        const selectedWorkflowId = workflowIdRef.current;
        const selectedRevision = draftRevisionRef.current;
        if (!selectedWorkflowId || selectedRevision === null) {
          throw new Error("Workflow draft is not ready.");
        }
        return axios.post<WorkflowReferralActionResponse>(
          `${API_BASE_URL}/api/workflow/drafts/${selectedWorkflowId}/referrals/${referralId}/resolve`,
          {
            revision: selectedRevision,
            action,
            reason: action === "cancel_referral" && !reason.trim()
              ? "Referral record cancelled by the Barangay Secretary."
              : reason,
          },
        );
      });

      updateWorkflowFromDraft(response.data);
      setDrafts((current) => current.map((draft) => draft.workflow_id === response.data.workflow_id ? response.data : draft));
      setDraftMessage(response.data.message);
      if (action === "complete_and_advance") {
        setFinalizeMessage("Referral confirmed. Generate and review the official referral packet before finalizing the outcome.");
        setFinalizeMessageTone("green");
      } else {
        setFinalizeMessage("Referral cancellation recorded. Continue to Outcome & Forms to document and finalize the case; ordinary mediation remains blocked.");
        setFinalizeMessageTone("blue");
      }
      await loadDrafts().catch(() => undefined);
      return { message: response.data.message };
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      const message = detail ?? (action === "cancel_referral"
        ? "The referral record could not be cancelled."
        : "The referral could not be completed.");
      setDraftMessage(message);
      throw new Error(message);
    }
  };

  const currentStepComplete = useMemo(() => {
    if (workflow.caseCancelled) return false;
    if (activeStep === 1) return workflow.consentComplainant && workflow.consentRespondent && workflow.transcript.trim().length >= 12 && Boolean(workflow.transcriptId) && !workflow.transcriptDirty;
    if (activeStep === 2) return Boolean(workflow.phase2Analysis && workflow.phase2CaseId);
    if (activeStep === 3) return Boolean(workflow.phase2CaseId);
    if (activeStep === 4) return workflow.hearingRecorded && Boolean(workflow.transcriptId) && workflow.hearingTranscriptId === workflow.transcriptId;
    if (activeStep === 5) return workflow.phase3Processed;
    if (activeStep === 6) {
      const referralResolved = workflow.referralResolution?.status === "completed"
        || workflow.referralResolution?.status === "cancelled";
      return referralPath ? referralResolved : workflow.symbolicConfirmed;
    }
    return Boolean(workflow.phase2Analysis && workflow.phase2CaseId);
  }, [activeStep, referralPath, workflow]);

  const currentStepRequirement = useMemo(() => {
    if (workflow.caseCancelled) return `Case cancelled: ${workflow.cancellationReason || "No further workflow action is allowed."}`;
    if (currentStepComplete) return "";
    if (activeStep === 1) {
      if (!workflow.consentComplainant || !workflow.consentRespondent) return "Confirm consent for both parties to continue.";
      if (workflow.transcript.trim().length < 12) return "Record live audio and review the generated transcript to continue.";
      if (!workflow.transcriptId) return "Select Save Transcript after reviewing the text to continue.";
      if (workflow.transcriptDirty) return `Select Save Transcript Changes to update transcript #${workflow.transcriptId} before continuing.`;
    }
    if (activeStep === 2) return "Run and save the Backend Decision to continue.";
    if (activeStep === 4) return "Prepare and save the Hearing transcript to continue.";
    if (activeStep === 5) return "Run Pre-processing & Analysis to continue.";
    if (activeStep === 6) {
      if (referralPath && !["completed", "cancelled"].includes(workflow.referralResolution?.status ?? "")) {
        return "Mark the referral completed to advance, or cancel only the referral record.";
      }
      return "Confirm the symbolic routing decision to continue.";
    }
    return "Complete the required actions in this panel to continue.";
  }, [activeStep, currentStepComplete, referralPath, workflow]);

  const proceed = async () => {
    if (!currentStepComplete) return;
    setIsAdvancing(true);
    setDraftMessage("");
    try {
      let nextWorkflow = workflow;
      if (activeStep === 1) {
        const ensuredTranscript = await ensureTranscriptSaved();
        nextWorkflow = ensuredTranscript.nextWorkflow;
        setWorkflow(nextWorkflow);
      }
      const nextStep = activeStep === 2 && confirmedVawcPath
        ? 7
        : activeStep === 2 && referralPath
          ? 5
          : Math.min(activeStep + 1, 7);
      const saved = await saveDraft(nextWorkflow, nextStep, Math.max(maxUnlockedStep, nextStep));
      if (!saved) {
        setDraftMessage((current) => current || "Unable to save this workflow step. Refresh the draft and try again.");
        return;
      }
      setActiveStep(nextStep);
      setMaxUnlockedStep((current) => Math.max(current, nextStep));
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setDraftMessage(detail ?? "Unable to save this step. Check the backend and try again.");
    } finally {
      setIsAdvancing(false);
    }
  };

  return (
    <div className="page-enter mx-auto max-w-6xl space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h1 className="text-2xl font-black text-gray-950">JUSTICE-KP 2.0 Workflow</h1>
            <p className="mt-2 text-sm text-gray-600">Complete the case through four guided stages: intake, hearing preparation, decision review, and final forms.</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-bold">
              {activeStep !== 1 && workflowId && <StatusPill label={`Draft ${workflowId.slice(0, 8)}`} tone="blue" />}
              {activeStep !== 1 && lastSavedAt && <span className="text-gray-500">Saved {formatPhilippineDateTime(lastSavedAt)}</span>}
              {isDraftDirty && <span className="text-amber-700">Unsaved changes</span>}
              {isDraftMutating && <span className="text-blue-700">Saving workflow...</span>}
              {workflow.phase2CaseId && (
                <span className="text-emerald-700">
                  Connected saved case: {workflow.phase2CaseId}
                  {workflow.phase2AnalysisId ? ` / analysis #${workflow.phase2AnalysisId}` : ""}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center xl:flex-nowrap">
            <AppButton disabled={isCreatingDraft || isDeletingDraft || isSwitchingDraft || isWorkflowOperationBusy || isDraftDirty} onClick={() => createDraft().catch(() => setDraftMessage("Unable to create a new blotter."))} tone="primary">
              <Plus size={16} />
              {isCreatingDraft ? "Creating..." : "New Case"}
            </AppButton>
            <AppButton disabled={isCreatingDraft || isDeletingDraft || isSwitchingDraft || isWorkflowOperationBusy || !workflowId} onClick={() => saveDraft()} tone="primary">
              <Save size={16} />
              Save Draft
            </AppButton>
          </div>
        </div>
        {draftMessage && <p className="mt-4 rounded-md border border-blue-100 bg-blue-50 p-3 text-sm font-bold text-blue-800">{draftMessage}</p>}
        <SavedDraftPicker>
          <div className="flex flex-col gap-3 border-b border-gray-200 bg-white p-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="font-black text-gray-950" id="saved-drafts-title">Saved Drafts</h2>
              <p className="mt-1 text-xs font-bold text-gray-500">{draftTotal} active {draftTotal === 1 ? "draft" : "drafts"}</p>
            </div>
            <label className="relative block w-full md:max-w-sm">
              <span className="sr-only">Search drafts by case ID or workflow stage</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={17} />
              <input
                className="h-10 w-full rounded-md border border-gray-300 bg-white pl-10 pr-9 text-sm font-semibold text-gray-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                disabled={isDraftNavigationDisabled}
                onChange={(event) => setDraftSearchInput(event.target.value)}
                placeholder="Search case ID or stage"
                type="search"
                value={draftSearchInput}
              />
              {isLoadingDrafts && <LoaderCircle className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-blue-600" size={17} />}
            </label>
          </div>

          {drafts.length > 0 ? (
            <div className="bg-gradient-to-br from-blue-50/70 via-white to-sky-50/60 p-3 sm:p-4">
              {drafts.map((draft) => {
                const payloadCaseId = (draft.payload.caseInformation as Partial<CaseInformation> | undefined)?.case_id;
                const draftLabel = draft.case_id || payloadCaseId || `Draft ${draft.workflow_id.slice(0, 8)}`;
                const isCurrent = draft.workflow_id === workflowId;
                return (
                  <article
                    aria-label={`${draftLabel}, page ${draftPage} of ${draftTotalPages}`}
                    className={`saved-draft-card grid gap-5 rounded-lg border border-blue-100 p-5 shadow-sm lg:grid-cols-[minmax(150px,1.1fr)_minmax(155px,1.25fr)_minmax(150px,1fr)_minmax(140px,1fr)_auto] lg:items-center ${isCurrent ? "bg-gradient-to-r from-blue-100 via-blue-50 to-white" : "bg-gradient-to-br from-white via-white to-blue-50/60"}`}
                    key={draft.workflow_id}
                  >
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-black text-gray-950">{draftLabel}</p>
                      </div>
                      {hasPermission(currentUser, "users.manage") && draft.owner && (
                        <p className="mt-1 flex items-center gap-1 text-xs font-bold text-gray-500"><UserRound size={13} />{draft.owner.full_name}</p>
                      )}
                    </div>
                    <div>
                      <p className="text-sm font-black text-gray-900">Stage {draft.current_stage.id}: {draft.current_stage.short_label}</p>
                      <p className="mt-1 text-xs font-semibold text-gray-500">{draft.current_stage.label}</p>
                    </div>
                    <div>
                      <p className="text-xs font-black uppercase tracking-wide text-gray-400">Last updated</p>
                      <p className="mt-1 text-sm font-bold text-gray-700">{formatPhilippineDateTime(draft.updated_at)}</p>
                    </div>
                    <div>
                      <div className="flex items-center justify-between text-xs font-bold text-gray-600">
                        <span>Step {Math.min(7, Math.max(1, draft.active_step))} of 7</span>
                        <span>{draft.completion_percentage}%</span>
                      </div>
                      <div aria-label={`${draft.completion_percentage}% complete`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={draft.completion_percentage} className="mt-2 h-2 overflow-hidden rounded-full bg-blue-100" role="progressbar">
                        <div className="h-full rounded-full bg-gradient-to-r from-blue-700 to-sky-400 transition-[width] duration-500" style={{ width: `${draft.completion_percentage}%` }} />
                      </div>
                    </div>
                    <div className="flex items-center gap-2 lg:justify-end">
                      <button
                        aria-label={`Delete ${draftLabel}`}
                        className="inline-flex size-9 items-center justify-center rounded-md border border-red-200 bg-white text-red-600 shadow-sm transition hover:-translate-y-0.5 hover:bg-red-50 hover:shadow disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={isCreatingDraft || isDeletingDraft || isSwitchingDraft || isWorkflowOperationBusy}
                        onClick={() => deleteDraft(draft.workflow_id, draftLabel).catch(() => undefined)}
                        title={`Delete ${draftLabel}`}
                        type="button"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="bg-white px-5 py-8 text-center">
              <p className="font-black text-gray-900">{isLoadingDrafts ? "Loading saved drafts..." : draftQuery ? "No drafts match this search" : "No active drafts yet"}</p>
              {!isLoadingDrafts && draftQuery && <p className="mt-2 text-sm text-gray-500">Try a case ID, Intake, Hearing, Review, Outcome, or a stage number.</p>}
            </div>
          )}

          <div className="draft-pagination-shell flex flex-col gap-4 border-t px-4 py-4 text-sm lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="draft-pagination-heading font-black">Page {draftPage} of {Math.max(1, draftTotalPages)}</p>
              <p aria-live="polite" className="draft-pagination-summary mt-1 text-xs font-bold">
                {draftTotal ? `Showing draft ${draftPage} of ${draftTotal}` : "No drafts to show"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
              <nav aria-label="Saved drafts pages" className="flex flex-wrap items-center gap-1.5">
                <button
                  aria-label="Previous drafts page"
                  className="draft-pagination-button grid size-9 place-items-center rounded-full border font-black shadow-sm transition duration-200 hover:-translate-x-0.5 disabled:cursor-not-allowed disabled:opacity-35"
                  disabled={isDraftNavigationDisabled || draftPage <= 1}
                  onClick={() => selectDraftPage({ page: draftPage - 1 }).catch(() => setDraftMessage("Unable to load the previous drafts page."))}
                  type="button"
                >
                  <ChevronLeft size={17} />
                </button>
                {draftPageItems.map((item) => typeof item === "number" ? (
                  <button
                    aria-current={item === draftPage ? "page" : undefined}
                    aria-label={`Go to drafts page ${item}`}
                    className={`draft-pagination-button grid size-9 place-items-center rounded-lg border font-black shadow-sm transition duration-200 hover:-translate-y-0.5 ${item === draftPage ? "draft-pagination-active" : ""}`}
                    disabled={isDraftNavigationDisabled}
                    key={item}
                    onClick={() => selectDraftPage({ page: item }).catch(() => setDraftMessage(`Unable to load drafts page ${item}.`))}
                    type="button"
                  >
                    {item}
                  </button>
                ) : (
                  <span aria-hidden="true" className="draft-pagination-ellipsis px-1 font-black" key={item}>…</span>
                ))}
                <button
                  aria-label="Next drafts page"
                  className="draft-pagination-button grid size-9 place-items-center rounded-full border font-black shadow-sm transition duration-200 hover:translate-x-0.5 disabled:cursor-not-allowed disabled:opacity-35"
                  disabled={isDraftNavigationDisabled || draftPage >= draftTotalPages}
                  onClick={() => selectDraftPage({ page: draftPage + 1 }).catch(() => setDraftMessage("Unable to load the next drafts page."))}
                  type="button"
                >
                  <ChevronRight size={17} />
                </button>
              </nav>
              <span aria-label="Page size: one draft" className="draft-page-size rounded-md border px-2.5 py-2 text-xs font-black">1 draft / page</span>
              <form className="flex items-center gap-2" onSubmit={goToDraftPage}>
                <label className="draft-pagination-label text-xs font-black" htmlFor="draft-go-to-page">Go to</label>
                <input
                  aria-label={`Go to a drafts page from 1 to ${Math.max(1, draftTotalPages)}`}
                  className="draft-pagination-input h-9 w-20 rounded-md border px-2 text-sm font-bold outline-none transition focus:ring-2"
                  disabled={isDraftNavigationDisabled || !draftTotalPages}
                  id="draft-go-to-page"
                  inputMode="numeric"
                  max={Math.max(1, draftTotalPages)}
                  min={1}
                  onChange={(event) => setDraftGoToInput(event.target.value.replace(/\D/g, ""))}
                  placeholder="e.g. 16"
                  type="text"
                  value={draftGoToInput}
                />
                <button
                  className="draft-pagination-go h-9 rounded-md border px-3 text-xs font-black transition disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={isDraftNavigationDisabled || !draftGoToInput}
                  type="submit"
                >
                  Go
                </button>
              </form>
            </div>
          </div>
        </SavedDraftPicker>
        {workflowId ? (
          <div className="mt-6">
            <Stepper activeStep={activeStep} skippedPanelIds={skippedPanelIds} maxUnlockedStep={maxUnlockedStep} setActiveStep={setActiveStep} />
          </div>
        ) : (
          <div className="mt-6 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-5 py-8 text-center">
            <p className="font-black text-gray-950">No workflow draft selected</p>
            <p className="mt-2 text-sm text-gray-600">Select New Case to start a blotter workflow. No empty draft will be created automatically.</p>
          </div>
        )}
      </section>

      {workflowId && <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        {activeStep === 1 && (
          <div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-black text-gray-950">Consent Management</h2>
                <p className="mt-2 text-sm text-gray-600">Verify recording consent to proceed.</p>
              </div>
              <StatusPill label="RA 4200 Compliant" tone="green" />
            </div>
            <div className="mt-6 grid gap-6 lg:grid-cols-2">
              <div className="consent-digital-card rounded-lg border border-blue-100 bg-blue-50 p-5">
                <h3 className="text-lg font-black text-blue-900">Digital Consent Form</h3>
                <p className="mt-3 text-sm leading-6 text-blue-700">
                  By proceeding, the parties agree to have their blotter narrative audio-recorded for AI transcription and NLP processing under RA 4200.
                </p>
                <div className="mt-5 space-y-3">
                  <label className="consent-check-row flex items-center gap-3 rounded-md border border-gray-200 bg-white p-3 text-sm font-bold text-gray-900">
                    <input checked={workflow.consentComplainant} className="size-4 accent-blue-600" onChange={(event) => updateWorkflow("consentComplainant", event.target.checked)} type="checkbox" />
                    Complainant verbally agreed to recording
                  </label>
                  <label className="consent-check-row flex items-center gap-3 rounded-md border border-gray-200 bg-white p-3 text-sm font-bold text-gray-900">
                    <input checked={workflow.consentRespondent} className="size-4 accent-blue-600" onChange={(event) => updateWorkflow("consentRespondent", event.target.checked)} type="checkbox" />
                    Respondent agreed to recording
                  </label>
                </div>
              </div>
              <div>
                <h3 className="text-lg font-black text-gray-950">Upload Signed Consent (Optional)</h3>
                <form className="consent-upload-card mt-5 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4" onSubmit={uploadConsentFile}>
                  <div className="grid gap-3 sm:grid-cols-[160px_minmax(0,1fr)]">
                    <label className="block text-sm font-bold text-gray-700">
                      Party
                      <select className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm" onChange={(event) => setConsentPartyType(event.target.value)} value={consentPartyType}>
                        <option value="general">General</option>
                        <option value="complainant">Complainant</option>
                        <option value="respondent">Respondent</option>
                        <option value="guardian">Guardian / Representative</option>
                      </select>
                    </label>
                    <label className="block min-w-0 text-sm font-bold text-gray-700">
                      Signed File
                      <input
                        accept=".pdf,.png,.jpg,.jpeg,.webp,.doc,.docx"
                        className="mt-2 block min-w-0 max-w-full w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                        onChange={(event) => setConsentFile(event.target.files?.[0] ?? null)}
                        type="file"
                      />
                    </label>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <AppButton disabled={isConsentUploading} tone="primary" type="submit">
                      <UploadCloud size={16} />
                      {isConsentUploading ? "Uploading..." : "Upload Consent"}
                    </AppButton>
                    <p className="text-xs font-bold text-gray-500">Accepted: PDF, image, DOC, DOCX</p>
                  </div>
                  {consentUploadMessage && <p className="consent-upload-message mt-3 rounded-md border border-blue-100 bg-white p-3 text-sm font-bold text-blue-700">{consentUploadMessage}</p>}
                </form>
                <div className="mt-4 space-y-3">
                  {!workflow.consentFiles.length && <p className="consent-empty-state rounded-md border border-gray-200 bg-white p-3 text-sm font-bold text-gray-500">No signed consent files uploaded yet.</p>}
                  {workflow.consentFiles.map((item) => (
                    <div className="consent-file-card rounded-md border border-gray-200 bg-white p-3" key={item.id}>
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-black text-gray-950">{item.file_name}</p>
                        <StatusPill label={item.party_type.replaceAll("_", " ")} tone="blue" />
                      </div>
                      <p className="mt-2 text-xs font-bold text-gray-500">
                        {formatFileSize(item.size_bytes)} uploaded by {item.uploaded_by} on {formatPhilippineDateTime(item.uploaded_at)}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-8 border-t border-gray-200 pt-8">
              <WorkflowRecordingPanel
                key={`intake-${workflowId}`}
                audioFilename={workflow.blotterAudioFilename}
                durationSeconds={workflow.blotterDurationSeconds}
                segments={workflow.transcriptSegments}
                rawSegments={workflow.rawTranscriptSegments}
                recordingType={workflow.recordingType}
                onBusyChange={setIsRecorderBusy}
                workflowId={workflowId}
                caseId={workflow.phase2CaseId || workflow.caseInformation.case_id}
                hasUnsavedChanges={workflow.transcriptDirty}
                onAudioReady={(blotterAudioFilename, blotterDurationSeconds) => setWorkflow((current) => ({
                  ...current,
                  blotterAudioFilename,
                  blotterDurationSeconds,
                }))}
                onRecordingTypeChange={(recordingType) => setWorkflow((current) => ({
                  ...current,
                  recordingType,
                  transcriptDirty: current.transcriptDirty || Boolean(current.transcript.trim()),
                }))}
                onSegmentsChange={(segments) => updateWorkflow("transcriptSegments", segments)}
                onRawTranscriptReady={(rawTranscript, rawTranscriptSegments) => setWorkflow((current) => ({
                  ...current,
                  rawTranscript,
                  rawTranscriptSegments,
                }))}
                onTranscriptChange={(transcript) => invalidatePhase2({
                  transcript,
                  transcriptDirty: true,
                  hearingRecorded: false,
                  hearingTranscriptId: null,
                  caseInformation: {
                    ...workflow.caseInformation,
                    has_vawc_or_child_abuse_indicators: false,
                  },
                })}
                onRecordingStarted={() => invalidatePhase2({
                  transcriptDirty: true,
                  hearingRecorded: false,
                  hearingTranscriptId: null,
                })}
                onTranscriptSaved={linkIntakeTranscriptToDraft}
                savedTranscriptId={workflow.transcriptId}
                transcript={workflow.transcript}
              />
            </div>
          </div>
        )}

        {activeStep === 2 && (
          <div className="space-y-6">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h2 className="text-xl font-black text-gray-950">Case Facts & Backend Decision</h2>
                <p className="mt-2 text-sm text-gray-600">Enter the case requirements once. The backend saves the XAI jurisdiction and referral decision automatically.</p>
              </div>
              <StatusPill label={workflow.phase2Analysis ? "Backend Decision Ready" : "Needs Backend Decision"} tone={workflow.phase2Analysis ? "green" : "amber"} />
            </div>
            {preliminaryVawcWarning ? (
              <section className="rounded-lg border-2 border-red-300 bg-red-50 p-5 text-red-950">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 shrink-0 text-red-600" size={22} />
                  <div>
                    <h3 className="font-black">Protected complainant decision branch</h3>
                    <p className="mt-2 text-sm font-bold leading-6">
                      Intake transcript detected: {preliminaryVawcKeywords.join(", ")}. Review the transcript, then confirm the protected-case indicator below. Summons, hearing, and normal mediation tasks will be skipped only after the backend verifies this route.
                    </p>
                  </div>
                </div>
                <label className="mt-5 flex items-start gap-3 rounded-md border border-red-300 bg-white p-4 text-sm font-black text-red-950">
                  <input
                    checked={Boolean(workflow.caseInformation.has_vawc_or_child_abuse_indicators)}
                    className="mt-0.5 size-4 shrink-0 accent-red-600"
                    onChange={(event) => invalidatePhase2({
                      caseInformation: {
                        ...workflow.caseInformation,
                        case_type: "criminal",
                        dispute_category: "physical_injury",
                        has_vawc_or_child_abuse_indicators: event.target.checked,
                      },
                    })}
                    type="checkbox"
                  />
                  <span>
                    Has VAWC or Child Abuse Indicators
                    <span className="mt-1 block text-xs font-bold text-red-700">Official confirmation required for referral to WCPD / PNP or the proper protection authority.</span>
                  </span>
                </label>
              </section>
            ) : (
              <CaseInfoForm
                key={workflowId}
                value={workflow.caseInformation}
                onChange={(caseInformation) => invalidatePhase2({ caseInformation })}
              />
            )}
            <div className="flex flex-wrap items-center gap-3">
              <AppButton
                disabled={isRunningPanel3 || !workflow.transcript.trim() || !workflow.caseInformation.dispute_category || (preliminaryVawcWarning && !workflow.caseInformation.has_vawc_or_child_abuse_indicators)}
                onClick={runPanel3Analysis}
                tone={preliminaryVawcWarning ? "danger" : "primary"}
              >
                <Scale size={16} />
                {isRunningPanel3 ? "Running Backend Phase 2..." : preliminaryVawcWarning ? "Confirm & Run Protected Routing" : "Run Backend Decision"}
              </AppButton>
              <p className="text-xs font-bold text-gray-500">Changing case facts or transcript clears stale backend decisions.</p>
            </div>
            {workflow.phase2Analysis && (
              <div className="space-y-4">
                <JurisdictionResult analysis={workflow.phase2Analysis} />
                <div className={`rounded-lg border p-5 ${workflow.phase2Analysis.detected_keywords.vawc_trigger ? "border-pink-300 bg-pink-50" : "border-gray-200 bg-gray-50"}`}>
                  <h3 className={workflow.phase2Analysis.detected_keywords.vawc_trigger ? "font-black text-pink-950" : "font-black text-gray-950"}>Complainant Decision Branch</h3>
                  <p className="mt-3 text-sm font-bold leading-6 text-gray-700">
                    {requiresReferralPath(workflow.phase2Analysis)
                      ? "This intake will generate the appropriate referral or manual-review KP forms."
                      : "This intake is eligible for the standard KP path and can proceed directly to recommended form generation."}
                  </p>
                  <p className={`mt-2 text-xs font-bold ${workflow.phase2Analysis.detected_keywords.vawc_trigger ? "text-pink-800" : "text-blue-700"}`}>
                    {workflow.phase2Analysis.detected_keywords.vawc_trigger ? "Protected routing skips summons and hearing mediation panels." : "The normal KP path continues to summons and hearing preparation."}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {activeStep === 3 && workflow.phase2CaseId && (
          <Phase3DashboardPage embedded initialCaseId={workflow.phase2CaseId} view="preparation" />
        )}

        {activeStep === 4 && (
          <div>
            <WorkflowRecordingPanel
              key={`hearing-${workflowId}`}
              mode="hearing"
              segments={workflow.hearingTranscriptSegments}
              rawSegments={workflow.rawTranscriptSegments}
              recordingType="blotter_hearing"
              onBusyChange={setIsRecorderBusy}
              workflowId={workflowId}
              caseId={workflow.phase2CaseId || workflow.caseInformation.case_id}
              hasUnsavedChanges={!workflow.hearingRecorded || workflow.hearingTranscriptId !== workflow.transcriptId}
              onRecordingTypeChange={() => undefined}
              onSegmentsChange={(segments) => updateWorkflow("hearingTranscriptSegments", segments)}
              onRawTranscriptReady={(rawHearingTranscript, rawHearingTranscriptSegments) => setWorkflow((current) => ({
                ...current,
                rawHearingTranscript,
                rawHearingTranscriptSegments,
              }))}
              onTranscriptChange={(hearingTranscript) => setWorkflow((current) => ({ ...current, hearingTranscript, hearingTranscriptId: null, hearingRecorded: false }))}
              onRecordingStarted={() => setWorkflow((current) => ({ ...current, hearingTranscriptId: null, hearingRecorded: false }))}
              onTranscriptSaved={linkHearingTranscriptToDraft}
              savedTranscriptId={workflow.transcriptId}
              sourceTranscript={workflow.transcript}
              sourceSegments={workflow.transcriptSegments}
              audioFilename={workflow.blotterAudioFilename}
              durationSeconds={workflow.blotterDurationSeconds}
              partiesConsented={workflow.consentComplainant && workflow.consentRespondent}
              onAudioReady={(blotterAudioFilename, blotterDurationSeconds) => setWorkflow((current) => ({
                ...current,
                blotterAudioFilename,
                blotterDurationSeconds,
              }))}
              transcript={workflow.hearingTranscript}
            />
          </div>
        )}

        {activeStep === 5 && (
          <div className="space-y-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-sm font-black uppercase tracking-wide text-blue-700">Analysis & Routing</p>
                <h2 className="mt-1 text-2xl font-black text-gray-950">Pre-processing, NER & Emotion Analysis</h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
                  Process the saved transcript into named entities, legal keywords, emotion signals, and tension indicators.
                </p>
              </div>
              <StatusPill label={workflow.phase3Processed ? "Analysis Ready" : "Ready to Process"} tone={workflow.phase3Processed ? "green" : "amber"} />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <AppButton disabled={isProcessingPhase3 || !workflow.phase2CaseId} onClick={() => runPhase3Processing().catch(() => undefined)} tone="primary">
                <Brain size={16} />
                {isProcessingPhase3 ? "Processing..." : workflow.phase3Processed ? "Re-run Analysis" : "Run Pre-processing & Analysis"}
              </AppButton>
            </div>
            {phase3Message && <p className="rounded-md border border-blue-100 bg-blue-50 p-3 text-sm font-bold text-blue-800">{phase3Message}</p>}
            {workflow.phase3Processed && workflow.phase2CaseId && (
              <Phase3DashboardPage key={`analysis-${workflow.phase2CaseId}-${workflow.phase3Processed}`} embedded initialCaseId={workflow.phase2CaseId} view="analysis" />
            )}
          </div>
        )}

        {activeStep === 6 && (
          <div className="space-y-6">
            {workflow.caseCancelled ? (
              <div className="rounded-xl border-2 border-red-300 bg-red-50 p-6 text-red-950 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-black uppercase tracking-wider text-red-700">Case Status</p>
                    <h2 className="mt-1 text-2xl font-black">Cancelled</h2>
                    <p className="mt-3 max-w-3xl text-sm font-bold leading-6">{workflow.cancellationReason}</p>
                    <p className="mt-2 text-xs font-bold text-red-700">
                      Cancelled by {workflow.cancelledBy || "Barangay Official"}
                      {workflow.cancelledAt ? ` on ${formatPhilippineDateTime(workflow.cancelledAt)}` : ""}
                    </p>
                  </div>
                  <StatusPill label="Cancelled" tone="red" />
                </div>
                <p className="mt-5 rounded-md border border-red-200 bg-white px-4 py-3 text-sm font-bold">
                  The workflow is closed. The original AI/KP recommendation remains preserved, while the official cancellation decision is stored in the audit trail.
                </p>
              </div>
            ) : (
              <>
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-xl font-black text-gray-950">Symbolic Engine and Decision Routing</h2>
                <p className="mt-2 text-sm text-gray-600">Review the explainable KP rules, sensitive-case route, mediation eligibility, and referral record.</p>
              </div>
              <StatusPill label={referralPath ? "Referral or Review Required" : "Eligible for Mediation"} tone={referralPath ? "red" : "green"} />
            </div>
            <div className="mt-6 grid gap-5 lg:grid-cols-[1.4fr_0.8fr] lg:items-stretch">
              <div className="rounded-xl border-2 border-blue-300 bg-blue-50/70 p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-black uppercase tracking-wider text-blue-700">Routing Check</p>
                    <h3 className="mt-1 text-lg font-black text-gray-950">Rule Matching</h3>
                  </div>
                  <StatusPill label={referralPath ? "Review Required" : "All Clear"} tone={referralPath ? "red" : "green"} />
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {([
                  ["Saved Case", Boolean(workflow.phase2CaseId), workflow.phase2CaseId || "Save the case before routing."],
                  ["KP Jurisdiction", workflow.phase2Analysis?.jurisdiction_decision === "within_kp", workflow.phase2Analysis?.jurisdiction_decision === "within_kp" ? "The case is within the KP process." : `Result: ${formatDisplayLabel(workflow.phase2Analysis?.jurisdiction_decision ?? "unknown")}.`],
                  ["No Government Party", !workflow.caseInformation.government_party_involved, workflow.caseInformation.government_party_involved ? "A government party requires review." : "No government party is involved."],
                  ["Protected-Case Check", !workflow.phase2Analysis?.detected_keywords.vawc_trigger, workflow.phase2Analysis?.detected_keywords.vawc_trigger ? "Protected referral is required." : "No VAWC or child-abuse trigger was found."],
                ] satisfies Array<[string, boolean, string]>).map(([rule, passed, detail]) => (
                  <div className={`flex items-start gap-3 rounded-lg border bg-white p-3 text-sm ${passed ? "border-emerald-200 text-gray-900" : "border-red-200 text-red-900"}`} key={rule}>
                    {passed ? <CheckCircle2 className="mt-0.5 shrink-0 text-emerald-600" size={18} /> : <AlertTriangle className="mt-0.5 shrink-0 text-red-600" size={18} />}
                    <span><b>{rule}</b><br /><span className="text-gray-600">{detail}</span></span>
                  </div>
                ))}
                </div>
                <label className="mt-4 flex items-center gap-3 rounded-lg border border-blue-200 bg-white px-4 py-3 text-sm font-bold text-blue-950">
                  <input checked={workflow.symbolicConfirmed} className="size-4 accent-blue-600" onChange={(event) => updateWorkflow("symbolicConfirmed", event.target.checked)} type="checkbox" />
                  I reviewed and confirm this routing result
                </label>
              </div>
              <div className={`flex flex-col justify-between rounded-xl border-2 p-5 ${referralPath ? "border-red-300 bg-red-50" : "border-emerald-300 bg-emerald-50"}`}>
                <div>
                  <p className={`text-xs font-black uppercase tracking-wider ${referralPath ? "text-red-700" : "text-emerald-700"}`}>Routing Result</p>
                  <div className="mt-4 flex items-start gap-3">
                    {referralPath ? <AlertTriangle className="shrink-0 text-red-700" size={28} /> : <CheckCircle2 className="shrink-0 text-emerald-700" size={28} />}
                    <div>
                      <h3 className={`text-xl font-black ${referralPath ? "text-red-950" : "text-emerald-950"}`}>
                        {referralPath ? "Refer or Review" : "Proceed to Mediation"}
                      </h3>
                      <p className={`mt-2 text-sm leading-6 ${referralPath ? "text-red-900" : "text-emerald-900"}`}>
                        {referralPath
                          ? "A matched rule requires referral or an official manual review."
                          : "The saved case facts satisfy the current KP routing checks."}
                      </p>
                    </div>
                  </div>
                </div>
                <div className={`mt-5 rounded-lg border bg-white/80 p-3 text-sm font-bold ${referralPath ? "border-red-200 text-red-900" : "border-emerald-200 text-emerald-900"}`}>
                  {workflow.phase2Analysis?.recommended_next_action ?? (referralPath ? "Review the referral route." : "Continue to mediation.")}
                </div>
              </div>
            </div>
            {workflow.phase2CaseId && (
              <Phase3DashboardPage
                embedded
                initialCaseId={workflow.phase2CaseId}
                onReferralWorkflowAction={resolveReferralWorkflow}
                view="routing"
              />
            )}
              </>
            )}
          </div>
        )}

        {activeStep === 7 && (
          <div className="space-y-6">
            {!referralPath && workflow.phase2CaseId && <Phase3DashboardPage embedded initialCaseId={workflow.phase2CaseId} view="mediation" />}
            <WorkflowOutputs
              finalizeMessage={finalizeMessage}
              finalizeMessageTone={finalizeMessageTone}
              generatedPacket={generatedPacket}
              isFinalizing={isFinalizing}
              isSavingOutcome={isSavingOutcome}
              isReferralPath={referralPath}
              referralStatus={workflow.referralResolution?.status}
              isVawcPath={confirmedVawcPath}
              isCompleted={workflow.completed}
              onGenerate={generateForms}
              onSaveOutcome={finalizeOutcome}
              outcome={workflow.outcome}
              savedCaseId={workflow.phase2CaseId}
              updateOutcome={(outcome) => updateWorkflow("outcome", outcome)}
            />
          </div>
        )}

        <div className="mt-8 flex flex-col items-end gap-3 border-t border-gray-100 pt-5">
          {currentStepRequirement && (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800">
              {currentStepRequirement}
            </p>
          )}
          {activeStep < 7 && !workflow.caseCancelled ? (
            <AppButton disabled={!currentStepComplete || isDraftMutating || isAdvancing || isCreatingDraft || isDeletingDraft} onClick={() => proceed().catch(() => undefined)} tone={activeStep === 2 && referralPath ? "danger" : "primary"}>
              {isAdvancing ? "Saving & continuing..." : activeStep === 2 && confirmedVawcPath ? "Continue to VAWC Output" : activeStep === 2 && referralPath ? "Continue to Protected Routing" : `Continue to ${workflowTaskLabels[Math.min(activeStep + 1, 7)]}`}
              <ChevronRight size={17} />
            </AppButton>
          ) : null}
        </div>
      </section>}
      {pendingDraftSwitchId && (
        <ModalPortal
          onDismiss={() => {
            if (!isDraftMutating && !isSwitchingDraft) {
              setPendingDraftSwitchId("");
              setDraftSwitchMessage("");
            }
          }}
        >
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-slate-950/70 p-4 backdrop-blur-sm"
            onMouseDown={() => {
              if (!isDraftMutating && !isSwitchingDraft) {
                setPendingDraftSwitchId("");
                setDraftSwitchMessage("");
              }
            }}
          >
          <section
            aria-describedby="switch-draft-description"
            aria-labelledby="switch-draft-title"
            aria-modal="true"
            className="max-h-[calc(100vh-2rem)] w-full max-w-lg overflow-y-auto rounded-xl border border-gray-200 bg-white p-6 shadow-2xl"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 shrink-0 text-amber-500" size={24} />
              <div>
                <h2 className="text-xl font-black text-gray-950" id="switch-draft-title">Save changes before changing pages?</h2>
                <p className="mt-2 text-sm leading-6 text-gray-600" id="switch-draft-description">
                  The current case has unsaved changes. Save them before going to another draft page, or continue without saving to discard those changes.
                </p>
              </div>
            </div>
            {draftSwitchMessage && <p className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-bold text-red-700" role="alert">{draftSwitchMessage}</p>}
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <AppButton disabled={isDraftMutating || isSwitchingDraft} onClick={() => setPendingDraftSwitchId("")}>Stay on Current Page</AppButton>
              <AppButton disabled={isDraftMutating || isSwitchingDraft} onClick={switchDraftWithoutSaving} tone="danger">Change Page Without Saving</AppButton>
              <AppButton disabled={isDraftMutating || isSwitchingDraft} onClick={() => saveAndSwitchDraft().catch(() => setDraftSwitchMessage("The current draft could not be saved. Stay here and try again."))} tone="primary">
                <Save size={16} />
                {isDraftMutating || isSwitchingDraft ? "Saving..." : "Save & Change Page"}
              </AppButton>
            </div>
          </section>
          </div>
        </ModalPortal>
      )}
      {finalizedCaseConfirmation && (
        <ModalPortal onDismiss={() => setFinalizedCaseConfirmation(null)}>
          <div
            className="fixed inset-0 z-[110] flex items-center justify-center overflow-y-auto bg-slate-950/70 p-4 backdrop-blur-sm"
            onMouseDown={() => setFinalizedCaseConfirmation(null)}
          >
            <section
              aria-describedby="finalized-case-description"
              aria-labelledby="finalized-case-title"
              aria-modal="true"
              className="max-h-[calc(100vh-2rem)] w-full max-w-lg overflow-y-auto rounded-2xl border border-emerald-200 bg-white p-6 text-center shadow-2xl sm:p-8"
              onMouseDown={(event) => event.stopPropagation()}
              role="dialog"
            >
              <div className="mx-auto grid size-16 place-items-center rounded-full bg-emerald-100 text-emerald-700">
                <CheckCircle2 size={34} strokeWidth={2.5} />
              </div>
              <h2 className="mt-5 text-2xl font-black text-gray-950" id="finalized-case-title">
                Case finalized successfully
              </h2>
              <p className="mt-3 text-sm leading-6 text-gray-600" id="finalized-case-description">
                Case <span className="font-black text-gray-900">{finalizedCaseConfirmation.caseId}</span> has been finalized as
                {" "}<span className="font-black text-gray-900">{finalizedCaseConfirmation.outcome}</span> and moved to
                {" "}<span className="font-black text-gray-900">Cases &amp; Records</span>.
              </p>
              <div className="mt-6 rounded-lg border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm font-bold text-emerald-800">
                The Workflow workspace is now closed and ready for your next case.
              </div>
              <div className="mt-7 grid gap-3 sm:grid-cols-2">
                <AppButton
                  disabled={isCreatingDraft}
                  onClick={() => {
                    setFinalizedCaseConfirmation(null);
                    createDraft().catch(() => setDraftMessage("Unable to create a new blotter."));
                  }}
                  tone="primary"
                >
                  <Plus size={17} />
                  {isCreatingDraft ? "Creating..." : "Create New Case"}
                </AppButton>
                <AppButton
                  onClick={() => {
                    setFinalizedCaseConfirmation(null);
                    onOpenCases();
                  }}
                  tone="secondary"
                >
                  <FolderKanban size={17} />
                  Go to Cases &amp; Records
                </AppButton>
              </div>
            </section>
          </div>
        </ModalPortal>
      )}
    </div>
  );
}

function WorkflowOutputs({
  finalizeMessage,
  finalizeMessageTone,
  generatedPacket,
  isFinalizing,
  isSavingOutcome,
  isReferralPath,
  referralStatus,
  isVawcPath,
  isCompleted,
  onGenerate,
  onSaveOutcome,
  outcome,
  savedCaseId,
  updateOutcome,
}: {
  finalizeMessage: string;
  finalizeMessageTone: "blue" | "green" | "red";
  generatedPacket: WorkflowFormPacket | null;
  isFinalizing: boolean;
  isSavingOutcome: boolean;
  isReferralPath: boolean;
  referralStatus?: "completed" | "cancelled";
  isVawcPath: boolean;
  isCompleted: boolean;
  onGenerate: () => Promise<void>;
  onSaveOutcome: () => Promise<void>;
  outcome: string;
  savedCaseId: string;
  updateOutcome: (outcome: string) => void;
}) {
  const outcomeOptions = workflowOutcomeOptions(isReferralPath, isVawcPath, referralStatus);
  const isCancelledReferral = referralStatus === "cancelled";
  const isMissingRequiredPacket = isCompleted && !generatedPacket;
  const canGenerateForms = !isFinalizing && Boolean(savedCaseId) && (!isCompleted || isMissingRequiredPacket);
  const statusLabel = isMissingRequiredPacket
    ? "Forms Needed"
    : isCompleted
      ? "Case Finalized"
      : generatedPacket
        ? "Forms Ready"
        : isReferralPath
          ? isVawcPath ? "Protected Referral" : "Referral Output"
          : "Ready to Generate";
  const statusTone = isMissingRequiredPacket ? "amber" : isCompleted ? "green" : isReferralPath ? "red" : generatedPacket ? "green" : "blue";
  const humanizeUiText = humanizeDisplayText;

  return (
    <div className="space-y-4">
      <div className={`flex flex-col gap-3 rounded-xl border-2 p-5 shadow-sm lg:flex-row lg:items-start lg:justify-between ${isReferralPath ? "border-red-200 bg-red-50/40" : "border-blue-200 bg-blue-50/40"}`}>
        <div>
          <p className={`text-xs font-black uppercase tracking-wide ${isCancelledReferral ? "text-amber-700" : isReferralPath ? "text-red-700" : "text-blue-700"}`}>Resolution & Forms</p>
          <h2 className="mt-1 text-2xl font-black text-gray-950">
            {isVawcPath ? "VAWC Case Referral Output" : isReferralPath ? "Referral & Official Forms" : "Mediation & Outputs"}
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            {isCancelledReferral
              ? "The referral record was cancelled. Generate the audit packet and record the official administrative closure; ordinary mediation remains blocked."
              : isReferralPath
              ? "Review the referral route, generate its official packet, and record the final escalation outcome."
              : "Review mediation support, generate the official KP packet, and save the final case outcome."}
          </p>
        </div>
        <StatusPill
          label={statusLabel}
          tone={statusTone}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        {isReferralPath ? (
          <section className="rounded-lg border-2 border-red-300 bg-red-50 p-5 text-red-950">
            <div className="flex items-center gap-3">
              <AlertTriangle className="text-red-600" size={22} />
              <h3 className="font-black">{isVawcPath ? "Mandatory Referral Protocol" : "Official Referral Protocol"}</h3>
            </div>
            <p className="mt-3 text-sm font-bold leading-6">
              {isCancelledReferral
                ? "Cancelling the referral did not approve mediation or erase the KP analysis. This stage records the cancellation reason, preserves the decision trail, and finalizes the case for official records."
                : isVawcPath
                ? "VAWC or child-abuse indicators block ordinary Katarungang Pambarangay mediation. Record protective referral actions without requiring the complainant to continue through hearing and mediation panels."
                : "The backend decision places this case on a referral or manual-review path instead of ordinary barangay mediation. Generate and review the official referral documents below."}
            </p>
            <ol className="mt-4 space-y-3 text-sm font-bold">
              <li className="rounded-md border border-red-200 bg-white p-3">
                1. {isCancelledReferral ? "Review the cancelled referral, destination, cancellation reason, and fired KP rules." : isVawcPath ? "Assist the complainant in reaching the PNP Women and Children Protection Desk or the proper protection authority." : "Review the destination and download the generated referral packet for official delivery."}
              </li>
              <li className="rounded-md border border-red-200 bg-white p-3">
                2. {isCancelledReferral ? "Generate the audit packet, then save the cancellation outcome to close this workflow without reopening mediation." : isVawcPath ? "Record emergency assistance or a Barangay Protection Order request when applicable." : "Record the final referral or manual-review outcome after the documents are issued."}
              </li>
            </ol>
          </section>
        ) : (
          <section className="rounded-xl border-2 border-blue-200 bg-blue-50 p-5 text-blue-950 shadow-sm">
            <div className="flex items-center gap-3">
              <Brain className="text-blue-700" size={22} />
              <h3 className="font-black">AI Mediation Strategy</h3>
            </div>
            <p className="mt-3 text-sm font-bold leading-6">Use the saved emotion, NER, and symbolic-routing results to guide a fair session.</p>
            <ol className="mt-4 grid gap-2 text-sm font-bold sm:grid-cols-2">
              <li className="rounded-md border border-blue-100 bg-white p-3">1. Establish speaking turns and document each party’s requested resolution.</li>
              <li className="rounded-md border border-blue-100 bg-white p-3">2. Convert agreed terms into the generated settlement form and confirm review by both parties.</li>
            </ol>
          </section>
        )}

        <section className="rounded-xl border-2 border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <CloudDownload className={isReferralPath ? "text-red-600" : "text-blue-600"} size={22} />
            <div>
              <h3 className="font-black text-gray-950">Printable KP Forms</h3>
              <p className="mt-1 text-xs font-bold text-gray-500">Case {savedCaseId || "not saved"}</p>
            </div>
          </div>
          <p className="mt-4 rounded-lg bg-gray-50 p-3 text-sm font-semibold leading-6 text-gray-700">
            Generate the recommended KP forms before finalizing the outcome. Downloads contain the original blank templates. Print and fill them in manually.
          </p>
          <div className="mt-4">
            <AppButton disabled={!canGenerateForms} onClick={() => onGenerate().catch(() => undefined)} tone={isReferralPath ? "danger" : "primary"}>
              <FileCheck2 size={17} />
              {isFinalizing ? "Generating KP Forms..." : generatedPacket ? "Regenerate Required Forms" : "Generate Required KP Forms"}
            </AppButton>
          </div>
        </section>
      </div>

      {!generatedPacket ? (
        <section className={`flex items-start gap-3 rounded-lg border-2 p-4 ${isReferralPath ? "border-red-200 bg-red-50 text-red-800" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
          <Lock className="mt-0.5 shrink-0" size={18} />
          <p className="text-sm font-black leading-6">
            {isMissingRequiredPacket
              ? "This older finalized draft is missing its document packet. Generate the required KP forms to repair the saved case record."
              : "Finalization is locked until the required document packet is generated."}
          </p>
        </section>
      ) : (
        <section className={`${isReferralPath ? "workflow-packet-card-vawc border-red-200 bg-red-50" : "workflow-packet-card border-emerald-200 bg-emerald-50"} rounded-lg border p-5`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className={`font-black ${isReferralPath ? "text-red-950" : "text-emerald-900"}`}>Packet #{generatedPacket.id}</h3>
              <p className={`mt-1 text-sm font-bold ${isReferralPath ? "text-red-800" : "text-emerald-800"}`}>{humanizeUiText(generatedPacket.source_phase3_action)}</p>
            </div>
            <StatusPill
              label={`${generatedPacket.form_accuracy_pct}% case data complete`}
              tone={generatedPacket.validation_status === "ready" ? "green" : "amber"}
            />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {generatedPacket.generated_forms.map((form) => (
              <a
                className={`flex items-center justify-between gap-3 rounded-md border bg-white p-4 text-sm font-black transition ${isReferralPath ? "border-red-200 text-red-800 hover:border-red-400" : "border-emerald-200 text-emerald-800 hover:border-emerald-400"}`}
                href={`${API_BASE_URL}${form.download_url}`}
                key={form.id}
                rel="noreferrer"
                target="_blank"
              >
                <span>
                  {form.title}
                  <span className="mt-1 block text-xs font-bold text-gray-500">
                    Blank template — print and fill in manually
                    {form.missing_fields.length > 0 && ` · Review case data: ${form.missing_fields.map(humanizeUiText).join(", ")}`}
                  </span>
                </span>
                <Download className="shrink-0" size={17} />
              </a>
            ))}
          </div>
        </section>
      )}

      <section className={`rounded-xl border-2 p-5 shadow-sm ${isReferralPath ? "border-red-200 bg-red-50/30" : "border-emerald-200 bg-emerald-50/30"}`}>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <label className="block flex-1 text-sm font-black text-gray-800">
            {isReferralPath ? "Escalation Status" : "Final Case Outcome"}
            <select
              className={`mt-2 h-11 w-full rounded-md border bg-white px-3 text-sm font-bold ${isReferralPath ? "border-red-300 text-red-800" : "border-gray-300 text-gray-900"}`}
              disabled={isCompleted}
              onChange={(event) => updateOutcome(event.target.value)}
              value={outcome}
            >
              {outcomeOptions.map((option) => <option key={option}>{option}</option>)}
            </select>
          </label>
          <AppButton
            disabled={!generatedPacket || isSavingOutcome || isFinalizing || isCompleted || !outcome}
            onClick={() => onSaveOutcome().catch(() => undefined)}
            tone={isReferralPath ? "danger" : "success"}
          >
            <CheckCircle2 size={17} />
            {isSavingOutcome ? "Saving Final Outcome..." : isCompleted ? "Case Finalized" : "Save Outcome & Finalize"}
          </AppButton>
        </div>
        {!generatedPacket && <p className="mt-3 rounded-md bg-white px-3 py-2 text-xs font-bold text-gray-600">Generate and review the required forms to enable finalization.</p>}
      </section>

      {finalizeMessage && (
        <p
          className={`rounded-md border p-3 text-sm font-bold ${
            finalizeMessageTone === "red"
              ? "border-red-200 bg-red-50 text-red-800"
              : finalizeMessageTone === "green"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-blue-100 bg-blue-50 text-blue-800"
          }`}
          role={finalizeMessageTone === "red" ? "alert" : "status"}
        >
          {humanizeUiText(finalizeMessage)}
        </p>
      )}

    </div>
  );
}

function CasesTab({ onNewBlotter }: { onNewBlotter: () => void }) {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [caseSearchQuery, setCaseSearchQuery] = useState("");
  const [caseStatusFilter, setCaseStatusFilter] = useState("");
  const [caseRouteFilter, setCaseRouteFilter] = useState("");
  const [casePage, setCasePage] = useState(1);
  const [casePageSize, setCasePageSize] = useState(10);
  const [caseTotal, setCaseTotal] = useState(0);
  const [caseTotalPages, setCaseTotalPages] = useState(0);
  const [caseRefreshToken, setCaseRefreshToken] = useState(0);
  const [isLoadingCases, setIsLoadingCases] = useState(true);
  const [caseLoadMessage, setCaseLoadMessage] = useState("");
  const [caseSummary, setCaseSummary] = useState<CompletedCaseSummary | null>(null);
  const [caseSummaryMessage, setCaseSummaryMessage] = useState("");
  const [loadingWorkflowId, setLoadingWorkflowId] = useState("");
  const firstShownCase = caseTotal ? (casePage - 1) * casePageSize + 1 : 0;
  const lastShownCase = caseTotal ? firstShownCase + cases.length - 1 : 0;

  useEffect(() => {
    const controller = new AbortController();
    let isCurrentRequest = true;
    const delay = window.setTimeout(async () => {
      setIsLoadingCases(true);
      setCaseLoadMessage("");
      try {
        const response = await axios.get<CasePage>(`${API_BASE_URL}/api/cases`, {
          params: {
            q: caseSearchQuery,
            status: caseStatusFilter,
            route: caseRouteFilter,
            page: casePage,
            page_size: casePageSize,
          },
          signal: controller.signal,
        });
        if (!isCurrentRequest) return;
        setCases(response.data.items);
        setCaseTotal(response.data.total);
        setCaseTotalPages(response.data.total_pages);
        if (response.data.page !== casePage) {
          setCasePage(response.data.page);
        }
      } catch (error) {
        if (!isCurrentRequest || axios.isCancel(error)) return;
        const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
        setCaseLoadMessage(detail ?? "Unable to load finalized case records.");
      } finally {
        if (isCurrentRequest) setIsLoadingCases(false);
      }
    }, caseSearchQuery ? 250 : 0);

    return () => {
      isCurrentRequest = false;
      window.clearTimeout(delay);
      controller.abort();
    };
  }, [casePage, casePageSize, caseRefreshToken, caseRouteFilter, caseSearchQuery, caseStatusFilter]);

  const openCaseSummary = async (workflowId?: string) => {
    if (!workflowId || loadingWorkflowId) return;
    setLoadingWorkflowId(workflowId);
    setCaseSummaryMessage("");
    try {
      const response = await axios.get<CompletedCaseSummary>(`${API_BASE_URL}/api/management/cases/${encodeURIComponent(workflowId)}`);
      setCaseSummary(response.data);
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setCaseSummaryMessage(detail ?? "Unable to load the completed case summary.");
    } finally {
      setLoadingWorkflowId("");
    }
  };

  if (caseSummary) {
    return <CaseSummaryPage apiBaseUrl={API_BASE_URL} onBack={() => setCaseSummary(null)} summary={caseSummary} />;
  }

  return (
    <div className="page-enter mx-auto max-w-7xl space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-black text-gray-950">Case Management</h1>
            <p className="mt-2 text-sm text-gray-600">Search, filter, and manage all blotter and KP cases.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <ManagementSearchInput
              id="case-record-search"
              label="Search finalized cases"
              onChange={(value) => {
                setCaseSearchQuery(value);
                setCasePage(1);
              }}
              placeholder="Search finalized cases..."
              value={caseSearchQuery}
            />
            <AppButton disabled={isLoadingCases} onClick={() => setCaseRefreshToken((value) => value + 1)}><RefreshCw className={isLoadingCases ? "animate-spin" : ""} size={17} /> Refresh</AppButton>
            <AppButton tone="primary" onClick={onNewBlotter}><Plus size={17} /> New Blotter</AppButton>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-3 border-t border-gray-100 pt-4">
          <label className="flex items-center gap-2 text-sm font-bold text-gray-700">
            Status
            <select
              className="h-10 rounded-md border border-gray-300 bg-white px-3 font-medium text-gray-900"
              onChange={(event) => {
                setCaseStatusFilter(event.target.value);
                setCasePage(1);
              }}
              value={caseStatusFilter}
            >
              <option value="">All statuses</option>
              <option value="Amicable Settlement Reached">Amicable Settlement Reached</option>
              <option value="No Settlement - Certificate to File Action">No Settlement - Certificate to File Action</option>
              <option value="Repudiated Settlement">Repudiated Settlement</option>
              <option value="Referred to WCPD / PNP">Referred to WCPD / PNP</option>
              <option value="Referred to MSWDO / PNP">Referred to MSWDO / PNP</option>
              <option value="Emergency Protection Assistance Initiated">Emergency Protection Assistance Initiated</option>
              <option value="Referred to Court / Proper Authority">Referred to Court / Proper Authority</option>
              <option value="Referred for Manual Review">Referred for Manual Review</option>
              <option value="Referral Packet Issued">Referral Packet Issued</option>
              <option value={CANCELLED_REFERRAL_OUTCOME}>{CANCELLED_REFERRAL_OUTCOME}</option>
              <option value="Case Cancelled">Case Cancelled</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-sm font-bold text-gray-700">
            Route
            <select
              className="h-10 rounded-md border border-gray-300 bg-white px-3 font-medium text-gray-900"
              onChange={(event) => {
                setCaseRouteFilter(event.target.value);
                setCasePage(1);
              }}
              value={caseRouteFilter}
            >
              <option value="">All routes</option>
              <option value="mediation">Mediation</option>
              <option value="referral">Referral</option>
              <option value="vawc_referral">VAWC referral</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
        </div>
        {caseLoadMessage && <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700">{caseLoadMessage}</p>}
      </section>

      <section className="case-records-table overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        <CasesTable
          cases={cases}
          formatDate={formatPhilippineDateTime}
          hasFilters={Boolean(caseSearchQuery || caseStatusFilter || caseRouteFilter)}
          loading={isLoadingCases}
          loadingWorkflowId={loadingWorkflowId}
          onOpenSummary={openCaseSummary}
          total={caseTotal}
        />
        <div className="flex flex-col gap-4 border-t border-gray-100 px-6 py-4 text-sm text-gray-600 lg:flex-row lg:items-center lg:justify-between">
          <span>Showing {firstShownCase}–{lastShownCase} of {caseTotal} {caseTotal === 1 ? "case" : "cases"}</span>
          <div className="flex flex-wrap items-center gap-2">
            <label className="mr-2 flex items-center gap-2 text-xs font-bold text-gray-600">
              Cases per page
              <select
                className="h-9 rounded-md border border-gray-300 bg-white px-2 text-sm font-medium text-gray-900"
                onChange={(event) => {
                  setCasePageSize(Number(event.target.value));
                  setCasePage(1);
                }}
                value={casePageSize}
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
            </label>
            <Pagination
              ariaLabel="Finalized case pages"
              disabled={isLoadingCases}
              onChange={setCasePage}
              page={casePage}
              totalPages={caseTotalPages}
            />
          </div>
        </div>
      </section>
      {caseSummaryMessage && <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700">{caseSummaryMessage}</p>}
    </div>
  );
}

function formatTranscriptTime(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--:--";
  }
  const totalSeconds = Math.max(0, Math.floor(value));
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, "0");
  const seconds = (totalSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function formatQuality(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return `${Math.round(value * 100)}%`;
}

function transcriptMetric(transcript: SavedTranscript | null | undefined, key: string) {
  const value = transcript?.accuracy_metrics?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function TranscriptSegmentsTable({
  segments,
  emptyMessage,
}: {
  segments: TranscriptSegment[];
  emptyMessage: string;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-gray-200">
      <table className="w-full min-w-[680px] border-collapse text-left text-sm">
        <thead className="bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Speaker</th>
            <th className="px-4 py-3">Start</th>
            <th className="px-4 py-3">End</th>
            <th className="px-4 py-3">Confidence</th>
            <th className="px-4 py-3">Text</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {!segments.length && (
            <tr>
              <td className="px-4 py-4 text-sm font-bold text-gray-500" colSpan={5}>{emptyMessage}</td>
            </tr>
          )}
          {segments.map((segment, index) => (
            <tr className="align-top" key={`${segment.speaker}-${segment.start}-${index}`}>
              <td className="px-4 py-3 font-black text-gray-950">{segment.speaker || `Speaker ${index + 1}`}</td>
              <td className="px-4 py-3 text-gray-700">{formatTranscriptTime(segment.start)}</td>
              <td className="px-4 py-3 text-gray-700">{formatTranscriptTime(segment.end)}</td>
              <td className="px-4 py-3 text-gray-700">{formatQuality(segment.confidence)}</td>
              <td className="px-4 py-3 leading-6 text-gray-800">{segment.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function addSpeakerTurnSpacing(text: string) {
  const spacedLines: string[] = [];

  for (const line of text.split(/\r?\n/)) {
    const isSpeakerTurn = /^\s*[^:\r\n]{1,80}\s*:\s*\S/.test(line);
    if (isSpeakerTurn && spacedLines.length && spacedLines[spacedLines.length - 1].trim()) {
      spacedLines.push("");
    }
    spacedLines.push(line);
  }

  return spacedLines.join("\n");
}

function HighlightedTranscriptText({ text, phrases }: { text: string; phrases: string[] }) {
  const activePhrases = phrases.map((phrase) => phrase.trim()).filter(Boolean);
  if (!text || !activePhrases.length) {
    return <>{text || "No transcript content saved."}</>;
  }

  const pattern = new RegExp(`(${activePhrases.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);

  return (
    <>
      {parts.map((part, index) => {
        const highlighted = activePhrases.some((phrase) => phrase.toLowerCase() === part.toLowerCase());
        return highlighted ? (
          <mark className="rounded-sm bg-red-100 px-1 font-black text-red-700" key={`${part}-${index}`}>
            {part}
          </mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        );
      })}
    </>
  );
}

function SavedTranscriptsTab() {
  const transcriptPageSize = 10;
  const [transcripts, setTranscripts] = useState<SavedTranscriptSummary[]>([]);
  const [transcriptSearchQuery, setTranscriptSearchQuery] = useState("");
  const [transcriptPage, setTranscriptPage] = useState(1);
  const [transcriptTotal, setTranscriptTotal] = useState(0);
  const [transcriptTotalPages, setTranscriptTotalPages] = useState(0);
  const [transcriptGoToInput, setTranscriptGoToInput] = useState("");
  const [selectedTranscriptId, setSelectedTranscriptId] = useState<number | null>(null);
  const [selectedTranscript, setSelectedTranscript] = useState<SavedTranscript | null>(null);
  const [detailLoadFailedId, setDetailLoadFailedId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"error" | "success">("error");
  const pendingTranscriptSelectionRef = useRef<"first" | "last" | null>(null);

  const transcriptPageItems = useMemo<Array<number | "start-ellipsis" | "end-ellipsis">>(() => {
    if (transcriptTotalPages <= 7) {
      return Array.from({ length: transcriptTotalPages }, (_, index) => index + 1);
    }
    if (transcriptPage <= 4) {
      return [1, 2, 3, 4, 5, "end-ellipsis", transcriptTotalPages];
    }
    if (transcriptPage >= transcriptTotalPages - 3) {
      return [1, "start-ellipsis", ...Array.from({ length: 5 }, (_, index) => transcriptTotalPages - 4 + index)];
    }
    return [1, "start-ellipsis", transcriptPage - 1, transcriptPage, transcriptPage + 1, "end-ellipsis", transcriptTotalPages];
  }, [transcriptPage, transcriptTotalPages]);
  const updateTranscriptSearchQuery = (query: string) => {
    setTranscriptSearchQuery(query);
    setTranscriptPage(1);
  };

  useEffect(() => {
    const controller = new AbortController();
    let isCurrentRequest = true;
    const delay = window.setTimeout(async () => {
      setIsLoading(true);
      try {
        const response = await axios.get<SavedTranscriptPage>(`${API_BASE_URL}/transcripts`, {
          params: {
            q: transcriptSearchQuery,
            page: transcriptPage,
            page_size: transcriptPageSize,
          },
          signal: controller.signal,
        });
        if (!isCurrentRequest) return;
        setTranscripts(response.data.items);
        setTranscriptTotal(response.data.total);
        setTranscriptTotalPages(response.data.total_pages);
        if (response.data.page !== transcriptPage) {
          setTranscriptPage(response.data.page);
        }
        const pendingSelection = pendingTranscriptSelectionRef.current;
        pendingTranscriptSelectionRef.current = null;
        setSelectedTranscriptId((currentId) => {
          if (pendingSelection === "last") {
            return response.data.items[response.data.items.length - 1]?.id ?? null;
          }
          if (pendingSelection === "first") {
            return response.data.items[0]?.id ?? null;
          }
          return response.data.items.some((item) => item.id === currentId)
            ? currentId
            : response.data.items[0]?.id ?? null;
        });
      } catch (error) {
        if (!isCurrentRequest || axios.isCancel(error)) return;
        pendingTranscriptSelectionRef.current = null;
        const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
        setMessageTone("error");
        setMessage(detail ?? "Unable to load saved transcripts.");
      } finally {
        if (isCurrentRequest) setIsLoading(false);
      }
    }, transcriptSearchQuery ? 250 : 0);

    return () => {
      isCurrentRequest = false;
      window.clearTimeout(delay);
      controller.abort();
    };
  }, [refreshToken, transcriptPage, transcriptSearchQuery]);

  useEffect(() => {
    if (selectedTranscriptId === null) {
      return;
    }
    const controller = new AbortController();
    let isCurrentRequest = true;
    axios.get<SavedTranscript>(`${API_BASE_URL}/transcripts/${selectedTranscriptId}`, { signal: controller.signal })
      .then((response) => {
        if (isCurrentRequest) {
          setSelectedTranscript(response.data);
          setDetailLoadFailedId(null);
        }
      })
      .catch((error) => {
        if (!isCurrentRequest || axios.isCancel(error)) return;
        const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
        setDetailLoadFailedId(selectedTranscriptId);
        setMessageTone("error");
        setMessage(detail ?? "Unable to load the selected transcript.");
      });
    return () => {
      isCurrentRequest = false;
      controller.abort();
    };
  }, [selectedTranscriptId]);

  const isLoadingDetail = selectedTranscriptId !== null
    && selectedTranscript?.id !== selectedTranscriptId
    && detailLoadFailedId !== selectedTranscriptId;

  const selectedTranscriptIndex = useMemo(
    () => transcripts.findIndex((item) => item.id === selectedTranscriptId),
    [selectedTranscriptId, transcripts],
  );
  const canNavigateToPreviousTranscript = selectedTranscriptIndex > 0 || transcriptPage > 1;
  const canNavigateToNextTranscript = (
    (selectedTranscriptIndex >= 0 && selectedTranscriptIndex < transcripts.length - 1)
    || transcriptPage < transcriptTotalPages
  );
  const navigateTranscript = useCallback((direction: -1 | 1) => {
    if (isLoading || pendingTranscriptSelectionRef.current || !transcripts.length) {
      return;
    }
    const currentIndex = transcripts.findIndex((item) => item.id === selectedTranscriptId);
    const nextIndex = currentIndex + direction;
    if (nextIndex >= 0 && nextIndex < transcripts.length) {
      setSelectedTranscriptId(transcripts[nextIndex].id);
      return;
    }
    if (direction === -1 && transcriptPage > 1) {
      pendingTranscriptSelectionRef.current = "last";
      setTranscriptPage((page) => page - 1);
      return;
    }
    if (direction === 1 && transcriptPage < transcriptTotalPages) {
      pendingTranscriptSelectionRef.current = "first";
      setTranscriptPage((page) => page + 1);
    }
  }, [isLoading, selectedTranscriptId, transcriptPage, transcriptTotalPages, transcripts]);

  useEffect(() => {
    const handleTranscriptArrowKey = (event: KeyboardEvent) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }
      if (
        (event.key === "ArrowLeft" && !canNavigateToPreviousTranscript)
        || (event.key === "ArrowRight" && !canNavigateToNextTranscript)
      ) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) {
        return;
      }
      event.preventDefault();
      navigateTranscript(event.key === "ArrowLeft" ? -1 : 1);
    };
    window.addEventListener("keydown", handleTranscriptArrowKey);
    return () => window.removeEventListener("keydown", handleTranscriptArrowKey);
  }, [canNavigateToNextTranscript, canNavigateToPreviousTranscript, navigateTranscript]);

  const rawHighlightPhrases = selectedTranscript?.corrections.map((item) => item.wrong).filter(Boolean) ?? [];
  const editedHighlightPhrases = selectedTranscript?.corrections.map((item) => item.corrected).filter(Boolean) ?? [];
  const rawWordAccuracy = transcriptMetric(selectedTranscript, "raw_word_accuracy");
  const editedWordAccuracy = transcriptMetric(selectedTranscript, "edited_word_accuracy");
  const wordErrorRate = transcriptMetric(selectedTranscript, "word_error_rate");
  const goToTranscriptPage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const requestedPage = Number(transcriptGoToInput);
    if (!Number.isInteger(requestedPage) || requestedPage < 1 || requestedPage > transcriptTotalPages) {
      setMessageTone("error");
      setMessage(`Enter a page number from 1 to ${Math.max(1, transcriptTotalPages)}.`);
      return;
    }
    setTranscriptPage(requestedPage);
    setTranscriptGoToInput("");
  };

  const deleteSelectedTranscript = async () => {
    if (!selectedTranscript || isDeleting) {
      return;
    }
    const confirmed = window.confirm(
      `Delete transcript #${selectedTranscript.id}? This cannot be undone. Linked case records will be preserved but detached from this transcript.`
    );
    if (!confirmed) {
      return;
    }

    setIsDeleting(true);
    setMessage("");
    try {
      const response = await axios.delete<{ message: string }>(`${API_BASE_URL}/transcripts/${selectedTranscript.id}`);
      setSelectedTranscriptId(null);
      setSelectedTranscript(null);
      setMessageTone("success");
      setMessage(response.data.message);
      setRefreshToken((value) => value + 1);
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setMessageTone("error");
      setMessage(detail ?? "Unable to delete the selected transcript.");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="page-enter mx-auto max-w-7xl space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-black text-gray-950">Saved Transcripts</h1>
            <p className="mt-2 text-sm text-gray-600">Review the one canonical raw and edited transcript saved for each workflow case.</p>
          </div>
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-start">
            <ManagementSearchInput
              id="saved-transcript-search"
              label="Search saved transcripts"
              onChange={updateTranscriptSearchQuery}
              placeholder="Search saved transcripts..."
              value={transcriptSearchQuery}
            />
            <AppButton disabled={isLoading} onClick={() => setRefreshToken((value) => value + 1)}>
              <RefreshCw className={isLoading ? "animate-spin" : ""} size={17} />
              {isLoading ? "Loading..." : "Refresh"}
            </AppButton>
          </div>
        </div>
        {message && (
          <p className={`mt-4 rounded-md border p-3 text-sm font-bold ${messageTone === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-100 bg-red-50 text-red-700"}`}>
            {message}
          </p>
        )}
      </section>

      {isLoading && !transcripts.length ? (
        <section className="rounded-lg border border-gray-200 bg-white p-8 text-center shadow-sm">
          <LoaderCircle className="mx-auto animate-spin text-blue-600" size={34} />
          <h2 className="mt-4 text-lg font-black text-gray-950">Loading saved transcripts...</h2>
        </section>
      ) : !isLoading && !transcriptTotal && !transcriptSearchQuery.trim() ? (
        <section className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center shadow-sm">
          <FileClock className="mx-auto text-gray-400" size={34} />
          <h2 className="mt-4 text-lg font-black text-gray-950">No saved transcripts yet</h2>
          <p className="mt-2 text-sm leading-6 text-gray-600">Select Save Transcript in Intake to create a case transcript. Save Hearing updates that same record.</p>
        </section>
      ) : !isLoading && !transcriptTotal ? (
        <section className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center shadow-sm">
          <Search className="mx-auto text-gray-400" size={34} />
          <h2 className="mt-4 text-lg font-black text-gray-950">No transcripts match your search</h2>
          <p className="mt-2 text-sm leading-6 text-gray-600">Clear the search or try a transcript number, case ID, transcript phrase, provider, or recording type.</p>
        </section>
      ) : (
        <div className="space-y-5">
          <TranscriptNavigator selectionLabel={<>{selectedTranscriptId ? `Viewing transcript #${selectedTranscriptId}` : "Select a transcript"}{" "}<span className="font-bold text-gray-400">(lowest number first · use ← → arrow keys)</span></>}>
            <div className="mt-4 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 border-t border-gray-100 pt-4">
              <button
                aria-label="Show previous transcript"
                className="draft-pagination-button grid size-9 place-items-center rounded-full border font-black shadow-sm transition duration-200 hover:-translate-x-0.5 disabled:cursor-not-allowed disabled:opacity-35"
                disabled={isLoading || !canNavigateToPreviousTranscript}
                onClick={() => navigateTranscript(-1)}
                title="Previous transcript (Left Arrow)"
                type="button"
              >
                <ChevronLeft size={17} />
              </button>
              <div className="flex min-w-0 flex-wrap gap-2">
                {transcripts.map((item) => (
                  <button
                    className={`inline-flex h-9 items-center gap-2 rounded-md border px-3 text-xs font-black transition ${
                      item.id === selectedTranscriptId ? "border-blue-500 bg-blue-600 text-white" : "border-gray-200 bg-gray-50 text-gray-700 hover:border-blue-200 hover:bg-blue-50"
                    }`}
                    key={item.id}
                    onClick={() => setSelectedTranscriptId(item.id)}
                    type="button"
                  >
                    #{item.id}
                    <span className={item.id === selectedTranscriptId ? "text-blue-100" : "text-gray-400"}>{item.segment_count} seg.</span>
                  </button>
                ))}
              </div>
              <button
                aria-label="Show next transcript"
                className="draft-pagination-button grid size-9 place-items-center rounded-full border font-black shadow-sm transition duration-200 hover:translate-x-0.5 disabled:cursor-not-allowed disabled:opacity-35"
                disabled={isLoading || !canNavigateToNextTranscript}
                onClick={() => navigateTranscript(1)}
                title="Next transcript (Right Arrow)"
                type="button"
              >
                <ChevronRight size={17} />
              </button>
            </div>
            <div className="draft-pagination-shell -mx-4 -mb-4 mt-4 flex flex-col gap-4 border-t px-4 py-4 text-sm sm:-mx-5 sm:-mb-5 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="draft-pagination-heading font-black">Page {transcriptPage} of {Math.max(1, transcriptTotalPages)}</p>
                <p aria-live="polite" className="draft-pagination-summary mt-1 text-xs font-bold">
                  {transcriptTotal
                    ? `Showing transcripts ${(transcriptPage - 1) * transcriptPageSize + 1}-${(transcriptPage - 1) * transcriptPageSize + transcripts.length} of ${transcriptTotal}`
                    : "No transcripts to show"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
                <nav aria-label="Saved transcript pages" className="flex flex-wrap items-center gap-1.5">
                  <button
                    aria-label="Previous transcript page"
                    className="draft-pagination-button grid size-9 place-items-center rounded-full border font-black shadow-sm transition duration-200 hover:-translate-x-0.5 disabled:cursor-not-allowed disabled:opacity-35"
                    disabled={isLoading || transcriptPage <= 1}
                    onClick={() => setTranscriptPage((value) => Math.max(1, value - 1))}
                    type="button"
                  >
                    <ChevronLeft size={17} />
                  </button>
                  {transcriptPageItems.map((item) => typeof item === "number" ? (
                    <button
                      aria-current={item === transcriptPage ? "page" : undefined}
                      aria-label={`Go to transcript page ${item}`}
                      className={`draft-pagination-button grid size-9 place-items-center rounded-lg border font-black shadow-sm transition duration-200 hover:-translate-y-0.5 ${item === transcriptPage ? "draft-pagination-active" : ""}`}
                      disabled={isLoading}
                      key={item}
                      onClick={() => setTranscriptPage(item)}
                      type="button"
                    >
                      {item}
                    </button>
                  ) : (
                    <span aria-hidden="true" className="draft-pagination-ellipsis px-1 font-black" key={item}>…</span>
                  ))}
                  <button
                    aria-label="Next transcript page"
                    className="draft-pagination-button grid size-9 place-items-center rounded-full border font-black shadow-sm transition duration-200 hover:translate-x-0.5 disabled:cursor-not-allowed disabled:opacity-35"
                    disabled={isLoading || transcriptPage >= transcriptTotalPages}
                    onClick={() => setTranscriptPage((value) => Math.min(transcriptTotalPages, value + 1))}
                    type="button"
                  >
                    <ChevronRight size={17} />
                  </button>
                </nav>
                <span aria-label="Page size: ten transcripts" className="draft-page-size rounded-md border px-2.5 py-2 text-xs font-black">10 transcripts / page</span>
                <form className="flex items-center gap-2" onSubmit={goToTranscriptPage}>
                  <label className="draft-pagination-label text-xs font-black" htmlFor="transcript-go-to-page">Go to</label>
                  <input
                    aria-label={`Go to a transcript page from 1 to ${Math.max(1, transcriptTotalPages)}`}
                    className="draft-pagination-input h-9 w-20 rounded-md border px-2 text-sm font-bold outline-none transition focus:ring-2"
                    disabled={isLoading || !transcriptTotalPages}
                    id="transcript-go-to-page"
                    inputMode="numeric"
                    max={Math.max(1, transcriptTotalPages)}
                    min={1}
                    onChange={(event) => setTranscriptGoToInput(event.target.value.replace(/\D/g, ""))}
                    placeholder="e.g. 2"
                    type="text"
                    value={transcriptGoToInput}
                  />
                  <button
                    className="draft-pagination-go h-9 rounded-md border px-3 text-xs font-black transition disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={isLoading || !transcriptGoToInput}
                    type="submit"
                  >
                    Go
                  </button>
                </form>
              </div>
            </div>
          </TranscriptNavigator>

          {isLoadingDetail ? (
            <section className="rounded-lg border border-gray-200 bg-white p-8 text-center shadow-sm">
              <LoaderCircle className="mx-auto animate-spin text-blue-600" size={34} />
              <h2 className="mt-4 text-lg font-black text-gray-950">Loading transcript #{selectedTranscriptId}...</h2>
            </section>
          ) : !selectedTranscript || selectedTranscript.id !== selectedTranscriptId ? (
            <section className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center shadow-sm">
              <Eye className="mx-auto text-gray-400" size={34} />
              <h2 className="mt-4 text-lg font-black text-gray-950">Transcript detail is unavailable</h2>
            </section>
          ) : (
            <section className="space-y-5">
              <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <p className="text-sm font-black uppercase tracking-wide text-blue-700">Transcript #{selectedTranscript.id}</p>
                    <h2 className="mt-1 text-xl font-black text-gray-950">Saved Transcript Record</h2>
                    <p className="mt-2 text-sm text-gray-600">
                      {selectedTranscript.case_id ? `Case ${selectedTranscript.case_id} · ` : ""}
                      Last updated {formatPhilippineDateTime(selectedTranscript.updated_at || selectedTranscript.created_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedTranscript.case_id && <StatusPill label={selectedTranscript.case_id} tone="green" />}
                    <StatusPill label={selectedTranscript.save_context === "hearing" ? "Latest: Hearing" : selectedTranscript.save_context === "intake" ? "Latest: Intake" : "Standalone"} tone="gray" />
                    <StatusPill label={selectedTranscript.asr_provider || "manual"} tone="blue" />
                    <StatusPill label={`${selectedTranscript.segments.length} segments`} tone="green" />
                    <button
                      className="inline-flex h-9 items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 text-xs font-black text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={isDeleting}
                      onClick={() => deleteSelectedTranscript().catch(() => undefined)}
                      type="button"
                    >
                      <Trash2 size={15} />
                      {isDeleting ? "Deleting..." : "Delete Transcript"}
                    </button>
                  </div>
                </div>
                <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <MetricTile label="ASR Confidence" value={formatQuality(selectedTranscript.asr_confidence)} />
                  <MetricTile label="Raw Word Accuracy" value={formatQuality(rawWordAccuracy)} tone="blue" />
                  <MetricTile label="Edited Reference" value={formatQuality(editedWordAccuracy)} tone="green" />
                  <MetricTile label="Word Error Rate" value={formatQuality(wordErrorRate)} tone="red" />
                  <MetricTile label="Diarization" value={formatQuality(selectedTranscript.diarization_quality)} tone="green" />
                  <MetricTile label="Correction Rate" value={formatQuality(selectedTranscript.manual_correction_rate)} tone="amber" />
                  <MetricTile label="Detected Speakers" value={String(selectedTranscript.detected_speakers ?? selectedTranscript.accuracy_metrics.detected_speakers ?? "N/A")} tone="gray" />
                </div>
                <p className="mt-4 rounded-md border border-blue-100 bg-blue-50 p-3 text-xs font-bold leading-5 text-blue-900">
                  Raw word accuracy and word error rate compare the uploaded ASR text with the final text saved by the reviewer. The edited transcript is treated as the human-reviewed reference; it is not an independent ASR confidence score.
                </p>
              </section>

              <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <h2 className="font-black text-gray-950">Raw vs Edited Transcription</h2>
                  <StatusPill label={`${selectedTranscript.corrections.length} corrections`} tone={selectedTranscript.corrections.length ? "red" : "gray"} />
                </div>
                <div className="mt-4 grid gap-4 xl:grid-cols-2">
                  <div>
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-black text-gray-950">Raw Transcription</h3>
                      <StatusPill label={`Accuracy ${formatQuality(rawWordAccuracy)}`} tone="amber" />
                    </div>
                    <div className="mt-3 max-h-[460px] overflow-auto whitespace-pre-wrap rounded-md border border-gray-200 bg-gray-50 p-4 font-mono text-sm leading-6 text-gray-900">
                      <HighlightedTranscriptText
                        text={addSpeakerTurnSpacing(selectedTranscript.raw_content || selectedTranscript.content)}
                        phrases={rawHighlightPhrases}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-black text-gray-950">Edited Transcription</h3>
                      <StatusPill label={`Reviewed ${formatQuality(editedWordAccuracy)}`} tone="blue" />
                    </div>
                    <div className="mt-3 max-h-[460px] overflow-auto whitespace-pre-wrap rounded-md border border-gray-200 bg-white p-4 font-mono text-sm leading-6 text-gray-900">
                      <HighlightedTranscriptText text={selectedTranscript.content || "No transcript content saved."} phrases={editedHighlightPhrases} />
                    </div>
                  </div>
                </div>
                <div className="mt-4 rounded-md border border-gray-200 bg-gray-50 p-4">
                  <h3 className="text-sm font-black text-gray-950">Correction Pairs</h3>
                  {!selectedTranscript.corrections.length ? (
                    <p className="mt-2 text-sm font-bold text-gray-500">No manual word corrections were detected for this transcript.</p>
                  ) : (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedTranscript.corrections.map((item, index) => (
                        <span className="rounded-md border border-red-200 bg-white px-3 py-2 text-xs font-black text-gray-800" key={`${item.wrong}-${item.corrected}-${index}`}>
                          <mark className="rounded-sm bg-red-100 px-1 text-red-700">{item.wrong}</mark>
                          <span className="px-2 text-gray-400">to</span>
                          <mark className="rounded-sm bg-red-100 px-1 text-red-700">{item.corrected}</mark>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
                <h2 className="font-black text-gray-950">Raw and Edited Speaker Segments</h2>
                <p className="mt-1 text-sm text-gray-600">Compare the original ASR timing and confidence with the final reviewer-approved segments.</p>
                <div className="mt-4 grid gap-5 2xl:grid-cols-2">
                  <div>
                    <h3 className="mb-2 text-sm font-black text-amber-700">Raw ASR Segments</h3>
                    <TranscriptSegmentsTable
                      emptyMessage="No raw ASR segments were saved for this transcript."
                      segments={selectedTranscript.raw_segments ?? []}
                    />
                  </div>
                  <div>
                    <h3 className="mb-2 text-sm font-black text-blue-700">Edited/Reviewed Segments</h3>
                    <TranscriptSegmentsTable
                      emptyMessage="No edited speaker segments were saved for this transcript."
                      segments={selectedTranscript.segments}
                    />
                  </div>
                </div>
              </section>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function FormsTab() {
  const [stageFilter, setStageFilter] = useState<KPFormDefinition["stage"] | "All">("All");
  const [formSearchQuery, setFormSearchQuery] = useState("");
  const visibleForms = useMemo(
    () => kpForms.filter((form) => (
      (stageFilter === "All" || form.stage === stageFilter)
      && matchesSearchQuery(formSearchQuery, [
        form.id,
        form.formNumber,
        form.title,
        form.description,
        form.stage,
        form.status,
      ])
    )),
    [formSearchQuery, stageFilter],
  );

  return (
    <div className="page-enter mx-auto max-w-7xl space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-black text-gray-950">KP Forms Library</h1>
            <p className="mt-2 text-sm text-gray-600">Official updated KP PDF templates from docs/KP_Updated_Forms, ready for viewing and download.</p>
          </div>
          <FormsSearch
            onQueryChange={setFormSearchQuery}
            onStageChange={(value) => setStageFilter(value as KPFormDefinition["stage"] | "All")}
            query={formSearchQuery}
            resultCount={visibleForms.length}
            stage={stageFilter}
            totalCount={kpForms.length}
          />
        </div>
      </section>
      <section className="forms-table-shell overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="forms-table w-full min-w-[760px] border-collapse text-left">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <th className="w-20 px-5 py-4 font-black">Form</th>
                <th className="px-5 py-4 font-black">Description</th>
                <th className="w-40 px-5 py-4 font-black">Stage</th>
                <th className="w-44 px-5 py-4 font-black">Status</th>
                <th className="w-56 px-5 py-4 text-right font-black">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleForms.map((form) => (
                <tr className="border-b border-gray-100 last:border-b-0 hover:bg-gray-50" key={form.id}>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <ToneIcon icon={FileCheck2} tone={form.tone} />
                      <span className="font-black text-gray-950">{form.formNumber}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <p className="font-bold text-gray-950">{form.title}</p>
                    <p className="mt-1 max-w-2xl text-sm leading-5 text-gray-600">{form.description}</p>
                  </td>
                  <td className="px-5 py-4 text-sm font-bold text-gray-600">{form.stage}</td>
                  <td className="px-5 py-4"><StatusPill label={form.status} tone={form.tone === "gray" ? "gray" : form.tone} /></td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button className="inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-blue-600 bg-blue-600 px-3 text-sm font-bold text-white shadow-sm transition hover:bg-blue-700" onClick={() => openKpForm(form)} type="button">
                        <Eye size={16} /> View PDF
                      </button>
                      <button className="forms-download-button inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-3 text-sm font-bold text-gray-900 shadow-sm transition hover:bg-gray-50" onClick={() => downloadKpForm(form)} type="button">
                        <Download size={16} /> Download
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!visibleForms.length && (
                <tr>
                  <td className="px-5 py-12 text-center text-sm font-bold text-gray-500" colSpan={5}>
                    No KP forms match the current search and stage filter. Clear the search or select another stage.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function ReportsTab() {
  const [period, setPeriod] = useState("Current Month (May 2026)");

  return (
    <div className="page-enter mx-auto max-w-7xl space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-black text-gray-950">Reports Generation</h1>
            <p className="mt-2 text-sm text-gray-600">Generate, print, and export official Barangay statistical and performance reports.</p>
          </div>
          <select className="h-11 rounded-md border border-gray-300 bg-white px-4 text-sm font-bold" onChange={(event) => setPeriod(event.target.value)} value={period}>
            <option>Current Month (May 2026)</option>
            <option>Previous Month (April 2026)</option>
            <option>Quarter 2 2026</option>
          </select>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-3">
        {reports.map((report) => (
          <article className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md" key={report.id}>
            <div className="flex items-start gap-4">
              <ToneIcon icon={report.icon} tone={report.tone} />
              <div>
                <h2 className="text-lg font-black text-gray-950">{report.title}</h2>
                <p className="mt-2 text-xs font-bold text-gray-400">Updated in real-time</p>
              </div>
            </div>
            <p className="mt-5 min-h-16 text-sm leading-6 text-gray-700">{report.description}</p>
            <div className="mt-5 flex gap-3 border-t border-gray-100 pt-4">
              <AppButton onClick={() => window.print()}><Printer size={17} /> Print</AppButton>
              <AppButton
                onClick={() =>
                  downloadPdf({
                    title: report.title,
                    subtitle: `${period}. ${report.description}`,
                    rows: report.rows,
                    filename: `${report.id}-report.pdf`,
                  })
                }
                tone="primary"
              >
                <CloudDownload size={17} />
                Export PDF
              </AppButton>
            </div>
          </article>
        ))}
        <article className="flex min-h-64 items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white p-6 text-center">
          <div>
            <ToneIcon icon={FileCog} tone="gray" />
            <h2 className="mt-5 text-lg font-black text-gray-950">Custom Report Builder</h2>
            <p className="mt-3 text-sm leading-6 text-gray-600">Create a tailored report with specific date ranges and data points.</p>
            <div className="mt-5"><AppButton>Configure Report</AppButton></div>
          </div>
        </article>
      </section>
    </div>
  );
}

const emptyGroundTruth: Phase5GroundTruth = {
  expected_covered_under_kp: null,
  expected_jurisdiction_decision: "",
  expected_exclusion_ground: "",
  expected_sensitive_case: null,
  expected_referral_route: "",
  expected_mediation_eligible: null,
  expected_form_ids: [],
  expected_keywords: [],
  expected_speaker_count: null,
  reference_transcript: "",
  reviewer_name: "researcher",
};

const emptyCompliance: Phase5ComplianceReview = {
  consent_confirmed: false,
  transcript_anonymized: false,
  official_decision_saved: false,
  generated_forms_reviewed: false,
  audit_trail_complete: false,
  sensitive_case_referred: false,
  reviewer_name: "researcher",
  notes: "",
};

function formatMetric(value: number | null | undefined, suffix = "%") {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return `${value}${suffix}`;
}

function splitList(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function MetricTile({ label, value, tone = "blue" }: { label: string; value: string; tone?: "blue" | "green" | "amber" | "red" | "gray" }) {
  const toneClasses = {
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    blue: "border-blue-100 bg-blue-50 text-blue-700",
    gray: "border-gray-200 bg-gray-50 text-gray-700",
    green: "border-emerald-200 bg-emerald-50 text-emerald-700",
    red: "border-red-200 bg-red-50 text-red-700",
  };
  return (
    <div className={`rounded-lg border p-4 ${toneClasses[tone]}`}>
      <p className="text-xs font-black uppercase tracking-wide opacity-80">{label}</p>
      <p className="mt-2 text-2xl font-black">{humanizeDisplayText(value)}</p>
    </div>
  );
}

function ValidationTab() {
  const [importableWorkflows, setImportableWorkflows] = useState<Phase5ImportableWorkflow[]>([]);
  const [dataset, setDataset] = useState<Phase5ValidationCase[]>([]);
  const [metrics, setMetrics] = useState<Phase5Metrics | null>(null);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [selectedValidationId, setSelectedValidationId] = useState("");
  const [manualTime, setManualTime] = useState("45");
  const [speakerGenderMix, setSpeakerGenderMix] = useState("unspecified");
  const [audioQuality, setAudioQuality] = useState("unspecified");
  const [groundTruth, setGroundTruth] = useState<Phase5GroundTruth>(emptyGroundTruth);
  const [compliance, setCompliance] = useState<Phase5ComplianceReview>(emptyCompliance);
  const [message, setMessage] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const selectedValidation = useMemo(
    () => dataset.find((item) => item.case_id === selectedValidationId) || null,
    [dataset, selectedValidationId]
  );

  const loadPhase5 = async () => {
    const [casesResponse, datasetResponse, metricsResponse] = await Promise.all([
      axios.get<Phase5ImportableWorkflow[]>(`${API_BASE_URL}/api/phase5/importable-workflows`),
      axios.get<Phase5ValidationCase[]>(`${API_BASE_URL}/api/phase5/dataset`),
      axios.get<Phase5Metrics>(`${API_BASE_URL}/api/phase5/metrics`),
    ]);
    setImportableWorkflows(casesResponse.data);
    setDataset(datasetResponse.data);
    setMetrics(metricsResponse.data);
    setSelectedWorkflowId((current) => (
      casesResponse.data.some((item) => item.workflow_id === current)
        ? current
        : casesResponse.data[0]?.workflow_id || ""
    ));
    setSelectedValidationId((current) => (
      datasetResponse.data.some((item) => item.case_id === current)
        ? current
        : datasetResponse.data[0]?.case_id || ""
    ));
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadPhase5().catch(() => setMessage("Unable to load validation data."));
  }, []);

  useEffect(() => {
    if (!selectedValidation) {
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGroundTruth({
      ...emptyGroundTruth,
      ...(selectedValidation.ground_truth || {}),
      expected_form_ids: selectedValidation.ground_truth?.expected_form_ids || [],
      expected_keywords: selectedValidation.ground_truth?.expected_keywords || [],
    });
    setCompliance({
      ...emptyCompliance,
      ...(selectedValidation.compliance_review || {}),
    });
  }, [selectedValidation]);

  const importCase = async () => {
    if (!selectedWorkflowId) {
      setMessage("Select a finalized workflow first.");
      return;
    }
    setIsBusy(true);
    setMessage("");
    try {
      const response = await axios.post<Phase5FinalizedWorkflowImportResponse>(`${API_BASE_URL}/api/phase5/import-workflow/${selectedWorkflowId}`, {
        dataset_split: "validation",
        speaker_gender_mix: speakerGenderMix,
        audio_quality: audioQuality,
        manual_processing_time_min: manualTime ? Number(manualTime) : null,
      });
      setSelectedValidationId(response.data.validation_case.case_id);
      setMessage(`${response.data.validation_case.case_id} imported from its finalized workflow into the validation dataset.`);
      await loadPhase5();
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.detail;
        if (typeof detail === "string") {
          setMessage(detail);
        } else if (detail && typeof detail === "object") {
          const structured = detail as { message?: string; reasons?: string[] };
          setMessage([structured.message, ...(structured.reasons ?? [])].filter(Boolean).join(" ") || "Import failed.");
        } else {
          setMessage("Import failed.");
        }
      } else {
        setMessage("Import failed.");
      }
    } finally {
      setIsBusy(false);
    }
  };

  const saveGroundTruth = async () => {
    if (!selectedValidation) {
      return;
    }
    setIsBusy(true);
    setMessage("");
    try {
      await axios.patch(`${API_BASE_URL}/api/phase5/ground-truth/${selectedValidation.case_id}`, groundTruth);
      setMessage("Ground truth saved.");
      await loadPhase5();
    } catch {
      setMessage("Unable to save ground truth.");
    } finally {
      setIsBusy(false);
    }
  };

  const saveCompliance = async () => {
    if (!selectedValidation) {
      return;
    }
    setIsBusy(true);
    setMessage("");
    try {
      await axios.patch(`${API_BASE_URL}/api/phase5/compliance/${selectedValidation.case_id}`, compliance);
      setMessage("Compliance review saved.");
      await loadPhase5();
    } catch {
      setMessage("Unable to save compliance review.");
    } finally {
      setIsBusy(false);
    }
  };

  const evaluateCase = async () => {
    if (!selectedValidation) {
      return;
    }
    setIsBusy(true);
    setMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/phase5/evaluate/${selectedValidation.case_id}`);
      setMessage("Case evaluation completed.");
      await loadPhase5();
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      if (detail && typeof detail === "object") {
        const structured = detail as { message?: string; missing_fields?: string[] };
        setMessage([
          structured.message,
          structured.missing_fields?.length ? `Missing: ${structured.missing_fields.join(", ")}.` : "",
        ].filter(Boolean).join(" "));
      } else {
        setMessage(typeof detail === "string" ? detail : "Unable to evaluate case.");
      }
    } finally {
      setIsBusy(false);
    }
  };

  const evaluateAll = async () => {
    setIsBusy(true);
    setMessage("");
    try {
      const response = await axios.post<unknown[]>(`${API_BASE_URL}/api/phase5/evaluate-all`);
      setMessage(response.data.length
        ? `${response.data.length} ground-truth-ready validation case(s) evaluated.`
        : "No cases are ready. Complete and save the required ground truth first.");
      await loadPhase5();
    } catch {
      setMessage("Unable to evaluate all cases.");
    } finally {
      setIsBusy(false);
    }
  };

  const createRun = async () => {
    setIsBusy(true);
    setMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/phase5/experiment-runs`, {
        name: `Validation run ${formatPhilippineDateTime(new Date())}`,
        created_by: "Barangay Official",
      });
      setMessage("Experiment run snapshot saved.");
      await loadPhase5();
    } catch {
      setMessage("Unable to save experiment run.");
    } finally {
      setIsBusy(false);
    }
  };

  const deletePendingValidation = async (item: Phase5ValidationCase) => {
    const confirmed = window.confirm(
      `Remove ${item.case_id} from the validation dataset? This will not delete its finalized case, transcript, workflow, or forms.`,
    );
    if (!confirmed) return;
    setIsBusy(true);
    setMessage("");
    try {
      const response = await axios.delete<{ message: string }>(`${API_BASE_URL}/api/phase5/dataset/${item.case_id}`);
      setMessage(response.data.message);
      await loadPhase5();
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setMessage(typeof detail === "string" ? detail : "Unable to remove the validation entry.");
    } finally {
      setIsBusy(false);
    }
  };

  const setGroundTruthBoolean = (key: keyof Phase5GroundTruth, value: string) => {
    setGroundTruth((current) => ({ ...current, [key]: value === "" ? null : value === "true" }));
  };

  return (
    <div className="page-enter mx-auto max-w-7xl space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h1 className="text-2xl font-black text-gray-950">Validation and Research Metrics</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
              Compare finalized system decisions against independently reviewed answers, then generate reproducible research metrics and exports.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <a className="inline-flex h-10 items-center gap-2 rounded-md border border-gray-300 bg-white px-4 text-sm font-black text-gray-900 hover:bg-gray-50" href={`${API_BASE_URL}/api/phase5/export/csv`}>
              <CloudDownload size={16} />
              CSV
            </a>
            <a className="inline-flex h-10 items-center gap-2 rounded-md border border-gray-300 bg-white px-4 text-sm font-black text-gray-900 hover:bg-gray-50" href={`${API_BASE_URL}/api/phase5/export/anonymized.csv`}>
              <EyeOff size={16} />
              Anon CSV
            </a>
            <a className="inline-flex h-10 items-center gap-2 rounded-md border border-gray-300 bg-white px-4 text-sm font-black text-gray-900 hover:bg-gray-50" href={`${API_BASE_URL}/api/phase5/export/report`} target="_blank" rel="noreferrer">
              <FileText size={16} />
              Report
            </a>
            <a className="inline-flex h-10 items-center gap-2 rounded-md border border-gray-300 bg-white px-4 text-sm font-black text-gray-900 hover:bg-gray-50" href={`${API_BASE_URL}/api/phase5/export/report.pdf`}>
              <FileCheck2 size={16} />
              PDF
            </a>
            <a className="inline-flex h-10 items-center gap-2 rounded-md border border-gray-300 bg-white px-4 text-sm font-black text-gray-900 hover:bg-gray-50" href={`${API_BASE_URL}/api/phase5/export/anonymized-report.pdf`}>
              <Shield size={16} />
              Anon PDF
            </a>
            <AppButton disabled={isBusy || !dataset.length} onClick={evaluateAll} tone="primary"><CheckCircle2 size={17} /> Evaluate All</AppButton>
            <AppButton disabled={isBusy || !metrics?.evaluated_count} onClick={createRun}><Database size={17} /> Save Run</AppButton>
          </div>
        </div>
        {message && <p className="mt-4 rounded-md border border-blue-100 bg-blue-50 p-3 text-sm font-bold text-blue-800">{message}</p>}
      </section>

      <section className="grid gap-3 md:grid-cols-3" aria-label="Validation process">
        {[
          ["1", "Import a finalized case", "Copies its saved system outputs into the research dataset. The official case remains unchanged."],
          ["2", "Enter reviewed ground truth", "A qualified reviewer records the expected KP decision, route, forms, and compliance evidence."],
          ["3", "Evaluate and preserve results", "The system compares expected versus actual outputs, calculates metrics, saves a run, and exports evidence."],
        ].map(([number, title, description]) => (
          <article className="rounded-lg border border-blue-100 bg-blue-50 p-4" key={number}>
            <p className="text-xs font-black uppercase tracking-wide text-blue-700">Step {number}</p>
            <h2 className="mt-1 font-black text-gray-950">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-gray-600">{description}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile label="Cases" value={`${metrics?.case_count ?? 0}`} />
        <MetricTile label="Evaluated" value={`${metrics?.evaluated_count ?? 0}`} tone="green" />
        <MetricTile label="Overall Accuracy" value={formatMetric(metrics?.overall_accuracy_pct)} tone="green" />
        <MetricTile label="Time Saved" value={formatMetric(metrics?.average_time_saved_pct)} tone="amber" />
        <MetricTile label="Jurisdiction" value={formatMetric(metrics?.jurisdiction_accuracy_pct)} />
        <MetricTile label="Sensitive Cases" value={formatMetric(metrics?.sensitive_accuracy_pct)} />
        <MetricTile label="Forms" value={formatMetric(metrics?.forms_accuracy_pct)} />
        <MetricTile label="Compliance" value={formatMetric(metrics?.average_compliance_score_pct)} tone="green" />
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 lg:grid-cols-[1fr_180px_180px_160px]">
          <label className="text-sm font-bold text-gray-700">
            Finalized Workflow
            <select className="mt-2 h-11 w-full rounded-md border border-gray-300 bg-white px-3" value={selectedWorkflowId} onChange={(event) => setSelectedWorkflowId(event.target.value)}>
              <option value="">Select a finalized, forms-ready case</option>
              {importableWorkflows.map((item) => (
                <option key={item.workflow_id} value={item.workflow_id}>
                  {item.case_id} - {item.outcome}{item.already_imported ? " (Already imported)" : ""}
                </option>
              ))}
            </select>
            {!importableWorkflows.length && (
              <span className="mt-2 block text-xs font-bold text-amber-700">No finalized, forms-ready workflows are available for import.</span>
            )}
          </label>
          <label className="text-sm font-bold text-gray-700">
            Gender Mix
            <select className="mt-2 h-11 w-full rounded-md border border-gray-300 bg-white px-3" value={speakerGenderMix} onChange={(event) => setSpeakerGenderMix(event.target.value)}>
              <option value="unspecified">Unspecified</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="mixed">Mixed</option>
              <option value="same_gender">Same gender</option>
            </select>
          </label>
          <label className="text-sm font-bold text-gray-700">
            Audio Quality
            <select className="mt-2 h-11 w-full rounded-md border border-gray-300 bg-white px-3" value={audioQuality} onChange={(event) => setAudioQuality(event.target.value)}>
              <option value="unspecified">Unspecified</option>
              <option value="quiet">Quiet</option>
              <option value="moderate_noise">Moderate noise</option>
              <option value="noisy">Noisy</option>
            </select>
          </label>
          <label className="text-sm font-bold text-gray-700">
            Manual Processing (min)
            <input className="mt-2 h-11 w-full rounded-md border border-gray-300 px-3" min={0} type="number" value={manualTime} onChange={(event) => setManualTime(event.target.value)} />
          </label>
        </div>
        <div className="mt-4">
          <AppButton disabled={isBusy || !selectedWorkflowId} onClick={importCase} tone="primary"><Plus size={17} /> Import Finalized Case</AppButton>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-black text-gray-950">Validation Dataset</h2>
          <div className="mt-4 space-y-3">
            {!dataset.length && <p className="text-sm font-bold text-gray-500">No validation cases imported.</p>}
            {dataset.map((item) => {
              const active = item.case_id === selectedValidationId;
              const evaluation = item.latest_evaluation;
              const statusLabel = evaluation?.overall_correct === true
                ? "Correct"
                : evaluation?.overall_correct === false
                  ? "Review"
                  : item.ground_truth_ready
                    ? "Ready to Evaluate"
                    : "Needs Ground Truth";
              const statusTone = evaluation?.overall_correct === true
                ? "green"
                : evaluation?.overall_correct === false
                  ? "red"
                  : item.ground_truth_ready
                    ? "blue"
                    : "gray";
              return (
                <article
                  className={`rounded-md border p-3 transition ${active ? "border-blue-500 bg-blue-50" : "border-gray-200 bg-gray-50 hover:bg-white"}`}
                  key={item.case_id}
                >
                  <button className="block w-full text-left" onClick={() => setSelectedValidationId(item.case_id)} type="button">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-black text-gray-950">{item.case_id}</p>
                      <p className="mt-1 text-xs font-bold text-gray-500">{formatDisplayLabel(String(item.case_information.dispute_category || "unknown"))} · {humanizeDisplayText(item.speaker_gender_mix)}</p>
                    </div>
                    <StatusPill label={statusLabel} tone={statusTone} />
                  </div>
                  <p className="mt-3 text-xs font-bold text-gray-600">System: {formatDisplayLabel(item.system_outputs.jurisdiction_decision)} / {formatDisplayLabel(item.system_outputs.referral_route)}</p>
                  </button>
                  {item.can_delete && (
                    <button
                      aria-label={`Remove ${item.case_id} from validation dataset`}
                      className="mt-3 inline-flex min-h-9 items-center gap-2 rounded-md border border-red-200 bg-white px-3 text-xs font-black text-red-700 transition hover:bg-red-50 disabled:opacity-50"
                      disabled={isBusy}
                      onClick={() => deletePendingValidation(item)}
                      type="button"
                    >
                      <Trash2 size={15} /> Remove Pending Entry
                    </button>
                  )}
                </article>
              );
            })}
          </div>
        </section>

        {!selectedValidation ? (
          <section className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center shadow-sm">
            <FileBarChart className="mx-auto text-gray-400" size={34} />
            <h2 className="mt-4 text-lg font-black text-gray-950">Select a validation case</h2>
          </section>
        ) : (
          <section className="space-y-5">
            <div className="grid gap-4 lg:grid-cols-3">
              <MetricTile label="System Decision" value={selectedValidation.system_outputs.jurisdiction_decision} />
              <MetricTile label="Referral Route" value={selectedValidation.system_outputs.referral_route || "None"} tone={selectedValidation.system_outputs.sensitive_case ? "red" : "green"} />
              <MetricTile label="Form Accuracy" value={formatMetric(selectedValidation.system_outputs.form_accuracy_pct)} tone="green" />
            </div>

            <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-black text-gray-950">Ground Truth</h2>
                  <p className="mt-1 max-w-2xl text-xs font-bold leading-5 text-gray-500">
                    The case details and system outputs were imported successfully and are displayed above. Only this independent reviewer answer key remains blank; copying the system output here would invalidate the accuracy test.
                  </p>
                </div>
                <StatusPill label={selectedValidation.ground_truth_ready ? "Ready to Evaluate" : "Incomplete"} tone={selectedValidation.ground_truth_ready ? "blue" : "gray"} />
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                <label className="text-sm font-bold text-gray-700">Jurisdiction<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={groundTruth.expected_jurisdiction_decision} onChange={(event) => setGroundTruth({ ...groundTruth, expected_jurisdiction_decision: event.target.value })} /></label>
                <label className="text-sm font-bold text-gray-700">Exclusion Ground<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={groundTruth.expected_exclusion_ground} onChange={(event) => setGroundTruth({ ...groundTruth, expected_exclusion_ground: event.target.value })} /></label>
                <label className="text-sm font-bold text-gray-700">Referral Route<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={groundTruth.expected_referral_route} onChange={(event) => setGroundTruth({ ...groundTruth, expected_referral_route: event.target.value })} /></label>
                <label className="text-sm font-bold text-gray-700">Covered Under KP<select className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3" value={groundTruth.expected_covered_under_kp === null || groundTruth.expected_covered_under_kp === undefined ? "" : String(groundTruth.expected_covered_under_kp)} onChange={(event) => setGroundTruthBoolean("expected_covered_under_kp", event.target.value)}><option value="">Unset</option><option value="true">Yes</option><option value="false">No</option></select></label>
                <label className="text-sm font-bold text-gray-700">Sensitive Case<select className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3" value={groundTruth.expected_sensitive_case === null || groundTruth.expected_sensitive_case === undefined ? "" : String(groundTruth.expected_sensitive_case)} onChange={(event) => setGroundTruthBoolean("expected_sensitive_case", event.target.value)}><option value="">Unset</option><option value="true">Yes</option><option value="false">No</option></select></label>
                <label className="text-sm font-bold text-gray-700">Mediation Eligible<select className="mt-2 h-10 w-full rounded-md border border-gray-300 bg-white px-3" value={groundTruth.expected_mediation_eligible === null || groundTruth.expected_mediation_eligible === undefined ? "" : String(groundTruth.expected_mediation_eligible)} onChange={(event) => setGroundTruthBoolean("expected_mediation_eligible", event.target.value)}><option value="">Unset</option><option value="true">Yes</option><option value="false">No</option></select></label>
                <label className="text-sm font-bold text-gray-700">Expected Forms<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={groundTruth.expected_form_ids.join(", ")} onChange={(event) => setGroundTruth({ ...groundTruth, expected_form_ids: splitList(event.target.value) })} /></label>
                <label className="text-sm font-bold text-gray-700">Expected Keywords<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={groundTruth.expected_keywords.join(", ")} onChange={(event) => setGroundTruth({ ...groundTruth, expected_keywords: splitList(event.target.value) })} /></label>
                <label className="text-sm font-bold text-gray-700">Expected Speakers<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" min={0} type="number" value={groundTruth.expected_speaker_count ?? ""} onChange={(event) => setGroundTruth({ ...groundTruth, expected_speaker_count: event.target.value ? Number(event.target.value) : null })} /></label>
              </div>
              <label className="mt-4 block text-sm font-bold text-gray-700">Reviewer<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={groundTruth.reviewer_name} onChange={(event) => setGroundTruth({ ...groundTruth, reviewer_name: event.target.value })} /></label>
              <div className="mt-4 flex flex-wrap gap-3">
                <AppButton disabled={isBusy} onClick={saveGroundTruth} tone="primary"><Save size={17} /> Save Ground Truth</AppButton>
                <AppButton disabled={isBusy || !selectedValidation.ground_truth_ready} onClick={evaluateCase} tone="success"><CheckCircle2 size={17} /> Evaluate Case</AppButton>
              </div>
              {!selectedValidation.ground_truth_ready && (
                <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-800">
                  Save these required fields to evaluate: {formatDisplayList(selectedValidation.ground_truth_missing_fields)}.
                </p>
              )}
            </section>

            <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-black text-gray-950">Compliance Review</h2>
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {[
                  ["consent_confirmed", "Consent confirmed"],
                  ["transcript_anonymized", "Transcript anonymized"],
                  ["official_decision_saved", "Official decision saved"],
                  ["generated_forms_reviewed", "Forms reviewed"],
                  ["audit_trail_complete", "Audit trail complete"],
                  ["sensitive_case_referred", "Sensitive case referred"],
                ].map(([key, label]) => (
                  <label className="flex items-center gap-3 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm font-bold text-gray-800" key={key}>
                    <input checked={Boolean(compliance[key as keyof Phase5ComplianceReview])} className="size-4 accent-blue-600" onChange={(event) => setCompliance({ ...compliance, [key]: event.target.checked })} type="checkbox" />
                    {label}
                  </label>
                ))}
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="text-sm font-bold text-gray-700">Reviewer<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={compliance.reviewer_name} onChange={(event) => setCompliance({ ...compliance, reviewer_name: event.target.value })} /></label>
                <label className="text-sm font-bold text-gray-700">Notes<input className="mt-2 h-10 w-full rounded-md border border-gray-300 px-3" value={compliance.notes} onChange={(event) => setCompliance({ ...compliance, notes: event.target.value })} /></label>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <AppButton disabled={isBusy} onClick={saveCompliance}><Shield size={17} /> Save Compliance</AppButton>
                <StatusPill label={`${formatMetric(selectedValidation.compliance_review?.compliance_score as number | null)} compliant`} tone="green" />
              </div>
            </section>

            <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-black text-gray-950">Latest Evaluation</h2>
              {!selectedValidation.latest_evaluation ? (
                <p className="mt-3 text-sm font-bold text-gray-500">No evaluation result yet.</p>
              ) : selectedValidation.latest_evaluation.overall_correct === null || selectedValidation.latest_evaluation.overall_correct === undefined ? (
                <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm font-bold text-amber-800">
                  An older incomplete evaluation was ignored because it had no reviewed ground truth. Complete the required fields and evaluate again.
                </p>
              ) : (
                <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <MetricTile label="Overall" value={selectedValidation.latest_evaluation.overall_correct ? "Correct" : "Review"} tone={selectedValidation.latest_evaluation.overall_correct ? "green" : "red"} />
                  <MetricTile label="Keyword Recall" value={formatMetric(selectedValidation.latest_evaluation.keyword_recall as number | null)} />
                  <MetricTile label="Time Saved" value={`${selectedValidation.latest_evaluation.time_saved_min ?? "N/A"} min`} tone="amber" />
                  <MetricTile label="Compliance" value={formatMetric(selectedValidation.latest_evaluation.compliance_score as number | null)} tone="green" />
                </div>
              )}
              {Array.isArray(selectedValidation.latest_evaluation?.errors_json) && selectedValidation.latest_evaluation.errors_json.length > 0 && (
                <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm font-bold leading-6 text-red-700">
                  {(selectedValidation.latest_evaluation.errors_json as string[]).join(" | ")}
                </div>
              )}
            </section>
          </section>
        )}
      </div>
    </div>
  );
}

function AdminUsersPanel() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [form, setForm] = useState({
    username: "",
    full_name: "",
    role_name: "barangay_secretary",
    password: "ChangeMe123!",
  });
  const [message, setMessage] = useState("");
  const [messageTone, setMessageTone] = useState<"success" | "error">("success");
  const [statusUserId, setStatusUserId] = useState<number | null>(null);

  const loadUsers = async () => {
    const response = await axios.get<AdminUser[]>(`${API_BASE_URL}/api/admin/users`);
    setUsers(response.data);
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadUsers().catch(() => {
      setMessageTone("error");
      setMessage("Unable to load user accounts. Please refresh the page and try again.");
    });
  }, []);

  const createUser = async (event: FormEvent) => {
    event.preventDefault();
    setMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/admin/users`, form);
      setForm({ username: "", full_name: "", role_name: "barangay_secretary", password: "ChangeMe123!" });
      setMessageTone("success");
      setMessage("The user account was created successfully.");
      await loadUsers();
    } catch (error) {
      setMessageTone("error");
      setMessage(axios.isAxiosError(error) ? error.response?.data?.detail ?? "Unable to create user." : "Unable to create user.");
    }
  };

  const setStatus = async (user: AdminUser, isActive: boolean) => {
    setStatusUserId(user.id);
    setMessage("");
    try {
      await axios.patch(`${API_BASE_URL}/api/admin/users/${user.id}/status`, { is_active: isActive });
      await loadUsers();
      setMessageTone("success");
      setMessage(`The account for ${user.username} was ${isActive ? "activated" : "deactivated"} successfully.`);
    } catch (error) {
      setMessageTone("error");
      setMessage(
        axios.isAxiosError(error)
          ? error.response?.data?.detail ?? "Unable to update the account status. Please try again."
          : "Unable to update the account status. Please try again.",
      );
    } finally {
      setStatusUserId(null);
    }
  };

  return (
    <SettingsRow icon={UsersRound} title="Admin User Management" tone="blue">
      <form className="grid gap-3 lg:grid-cols-[1fr_1fr_180px_180px_auto]" onSubmit={createUser}>
        <input className="h-10 rounded-md border border-gray-300 px-3 text-sm" placeholder="Username" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
        <input className="h-10 rounded-md border border-gray-300 px-3 text-sm" placeholder="Full name" value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
        <select className="h-10 rounded-md border border-gray-300 px-3 text-sm" value={form.role_name} onChange={(event) => setForm({ ...form, role_name: event.target.value })}>
          <option value="system_admin">System Admin</option>
          <option value="barangay_secretary">Barangay Secretary</option>
          <option value="lupon_chair">Lupon Chair</option>
          <option value="lupon_member">Lupon Member</option>
          <option value="researcher">Researcher</option>
          <option value="viewer">Viewer</option>
        </select>
        <input className="h-10 rounded-md border border-gray-300 px-3 text-sm" placeholder="Temporary password" type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
        <AppButton tone="primary" type="submit"><Plus size={17} /> Create</AppButton>
      </form>
      {message && (
        <p
          aria-live="polite"
          className={`mt-3 rounded-md border px-3 py-2 text-sm font-bold ${
            messageTone === "error" ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"
          }`}
          role={messageTone === "error" ? "alert" : "status"}
        >
          {message}
        </p>
      )}
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-gray-100 text-xs uppercase text-gray-500">
            <tr><th className="py-3">Username</th><th>Full Name</th><th>Role</th><th>Status</th><th>Action</th></tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((user) => (
              <tr key={user.id}>
                <td className="py-3 font-black">{user.username}</td>
                <td>{user.full_name}</td>
                <td>{formatDisplayLabel(user.role_name)}</td>
                <td><StatusPill label={user.is_active ? "Active" : "Inactive"} tone={user.is_active ? "green" : "gray"} /></td>
                <td>
                  <button className="text-xs font-black text-blue-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={statusUserId !== null} onClick={() => setStatus(user, !user.is_active)} type="button">
                    {statusUserId === user.id ? "Updating..." : user.is_active ? "Deactivate" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SettingsRow>
  );
}

function BackupPanel() {
  const [backups, setBackups] = useState<BackupRecord[]>([]);
  const [message, setMessage] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  const loadBackups = async () => {
    const response = await axios.get<BackupRecord[]>(`${API_BASE_URL}/api/admin/backups`);
    setBackups(response.data);
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadBackups().catch(() => setMessage("Unable to load backups."));
  }, []);

  const runBackup = async () => {
    setIsBusy(true);
    setMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/admin/backups/run`);
      setMessage("Encrypted backup created.");
      await loadBackups();
    } catch {
      setMessage("Unable to create backup.");
    } finally {
      setIsBusy(false);
    }
  };

  const verifyBackup = async (backupId: string) => {
    setIsBusy(true);
    setMessage("");
    try {
      await axios.post(`${API_BASE_URL}/api/admin/backups/${backupId}/verify`);
      setMessage("Backup verified.");
      await loadBackups();
    } catch {
      setMessage("Backup verification failed.");
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <SettingsRow icon={Database} title="Backup and Restore" tone="green">
      <div className="flex flex-wrap items-center gap-3">
        <AppButton disabled={isBusy} onClick={runBackup} tone="primary"><Database size={17} /> Run Backup</AppButton>
        {message && <p className="text-sm font-bold text-blue-700">{message}</p>}
      </div>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-gray-100 text-xs uppercase text-gray-500">
            <tr><th className="py-3">Backup ID</th><th>Status</th><th>Files</th><th>Encryption</th><th>Created</th><th>Actions</th></tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {backups.map((backup) => (
              <tr key={backup.backup_id}>
                <td className="py-3 font-black">{backup.backup_id}</td>
                <td><StatusPill label={backup.status} tone={backup.status === "verified" ? "green" : "amber"} /></td>
                <td>{backup.manifest.file_count ?? 0}</td>
                <td>{backup.manifest.encryption_algorithm || "configured"}</td>
                <td>{formatPhilippineDateTime(backup.created_at)}</td>
                <td className="flex gap-3 py-3">
                  <button className="text-xs font-black text-blue-700" disabled={isBusy} onClick={() => verifyBackup(backup.backup_id)} type="button">Verify</button>
                  <a className="text-xs font-black text-blue-700" href={`${API_BASE_URL}/api/admin/backups/${backup.backup_id}/download`}>Download</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!backups.length && <p className="mt-3 text-sm font-bold text-gray-500">No backups created yet.</p>}
      </div>
    </SettingsRow>
  );
}

function SettingsTab({ currentUser, darkMode, onDarkModeChange }: { currentUser: CurrentUser; darkMode: boolean; onDarkModeChange: (value: boolean) => void }) {
  const [settings, setSettings] = useState<SettingsState>({
    fullName: "Juan Dela Cruz",
    role: "Barangay Secretary",
    darkMode,
    hearingReminders: true,
    aiAlerts: true,
  });

  const set = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => setSettings((current) => ({ ...current, [key]: value }));

  return (
    <div className="page-enter mx-auto max-w-4xl space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm sm:p-6">
        <h1 className="text-2xl font-black text-gray-950">System Settings</h1>
        <p className="mt-2 text-sm text-gray-600">Manage your account, preferences, and JUSTICE-KP configurations.</p>
      </section>

      <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 p-6">
          <h2 className="flex items-center gap-3 text-lg font-black text-gray-950"><UserRound className="text-blue-600" size={20} /> User Profile</h2>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-bold text-gray-700">Full Name<input className="mt-2 h-11 w-full rounded-md border border-gray-300 px-3" onChange={(event) => set("fullName", event.target.value)} value={settings.fullName} /></label>
            <label className="block text-sm font-bold text-gray-700">Role<input className="mt-2 h-11 w-full rounded-md border border-gray-300 px-3" onChange={(event) => set("role", event.target.value)} value={settings.role} /></label>
          </div>
        </div>
        <SettingsRow icon={SlidersHorizontal} title="Display Preferences" tone="blue">
          <div className="flex items-center justify-between gap-4">
            <div><p className="font-bold">Dark Mode</p><p className="mt-1 text-sm text-gray-500">Switch the full interface between light and dark themes.</p></div>
            <Toggle checked={darkMode} onChange={onDarkModeChange} />
          </div>
        </SettingsRow>
        <SettingsRow icon={Bell} title="Notification Settings" tone="amber">
          <div className="space-y-5">
            <div className="flex items-center justify-between gap-4"><div><p className="font-bold">Hearing Reminders</p><p className="mt-1 text-sm text-gray-500">Get notified 24 hours before hearings</p></div><Toggle checked={settings.hearingReminders} onChange={(value) => set("hearingReminders", value)} /></div>
            <div className="flex items-center justify-between gap-4"><div><p className="font-bold">AI Alerts</p><p className="mt-1 text-sm text-gray-500">Notifications for sentiment escalations</p></div><Toggle checked={settings.aiAlerts} onChange={(value) => set("aiAlerts", value)} /></div>
          </div>
        </SettingsRow>
        <SettingsRow icon={Shield} title="Data Security & Backup" tone="green">
          <div className="flex flex-wrap gap-3">
            <AppButton
              onClick={() =>
                downloadPdf({
                  title: "JUSTICE-KP Export Data",
                  subtitle: "Frontend demo export generated from Settings.",
                  rows: [`User: ${settings.fullName}`, `Role: ${settings.role}`, `AI Alerts: ${settings.aiAlerts ? "On" : "Off"}`],
                  filename: "justice-kp-export-data.pdf",
                })
              }
            >
              <Database size={17} />
              Export Data
            </AppButton>
            <AppButton><FileArchive size={17} /> Local Backup</AppButton>
          </div>
        </SettingsRow>
        {hasPermission(currentUser, "backup.manage") && <BackupPanel />}
        {hasPermission(currentUser, "users.manage") && <AdminUsersPanel />}
      </section>
    </div>
  );
}

function SettingsRow({ icon: Icon, title, tone, children }: { icon: LucideIcon; title: string; tone: "blue" | "amber" | "green"; children: React.ReactNode }) {
  const colors = { amber: "text-amber-600", blue: "text-blue-600", green: "text-emerald-600" };
  return (
    <div className="border-b border-gray-100 p-6 last:border-b-0">
      <h2 className="flex items-center gap-3 text-lg font-black text-gray-950"><Icon className={colors[tone]} size={20} /> {title}</h2>
      <div className="mt-5">{children}</div>
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <button
      aria-pressed={checked}
      className={`relative h-7 w-12 rounded-full transition ${checked ? "bg-blue-600" : "bg-gray-300"}`}
      onClick={() => onChange(!checked)}
      type="button"
    >
      <span className={`absolute top-1 size-5 rounded-full bg-white shadow transition ${checked ? "left-6" : "left-1"}`} />
    </button>
  );
}

function TopBar({ darkMode }: { darkMode: boolean }) {
  return (
    <header className={`sticky top-0 z-20 border-b px-4 py-3 lg:px-8 ${darkMode ? "border-white/10 bg-slate-950 text-slate-100" : "border-gray-200 bg-white text-gray-950"}`}>
      <div className="flex items-center justify-end gap-4">
        <div className="flex items-center gap-4">
          <button className={`relative rounded-md border p-2 transition ${darkMode ? "border-white/10 bg-white/[0.04] text-slate-300 hover:border-sky-300/30 hover:bg-white/10 hover:text-white" : "border-gray-200 bg-white text-gray-500 hover:bg-gray-50 hover:text-blue-700"}`} type="button">
            <Bell size={20} />
            <span className="absolute right-2 top-2 size-2 rounded-full bg-rose-400 shadow-lg shadow-rose-400/40" />
          </button>
          <div className={`hidden h-8 w-px sm:block ${darkMode ? "bg-white/10" : "bg-gray-200"}`} />
          <div className="flex items-center gap-3">
            <CircleUserRound className={darkMode ? "text-sky-300" : "text-blue-600"} size={32} />
            <div className="hidden sm:block">
              <p className={`text-sm font-black ${darkMode ? "text-white" : "text-gray-950"}`}>admin</p>
              <p className={`text-xs ${darkMode ? "text-slate-400" : "text-gray-600"}`}>Barangay Secretary</p>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function tabAllowed(tab: TabId, user: CurrentUser | null) {
  if (tab === "dashboard" || tab === "cases") {
    return hasPermission(user, "case.read");
  }
  if (tab === "transcripts") {
    return hasPermission(user, "transcript.read") || hasPermission(user, "transcript.write");
  }
  if (tab === "workflow") {
    return hasPermission(user, "case.write") || hasPermission(user, "transcript.write");
  }
  if (tab === "forms") {
    return hasPermission(user, "forms.download");
  }
  if (tab === "reports") {
    return hasPermission(user, "reports.export");
  }
  if (tab === "validation") {
    return hasPermission(user, "phase5.evaluate") || hasPermission(user, "reports.export");
  }
  if (tab === "settings") {
    return hasPermission(user, "settings.manage") || hasPermission(user, "users.manage") || hasPermission(user, "backup.manage");
  }
  return false;
}

function MainPage({ currentUser, onLogout }: { currentUser: CurrentUser; onLogout: () => void }) {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [darkMode, setDarkMode] = useState(false);
  const [themePreferenceLoaded, setThemePreferenceLoaded] = useState(false);
  const [pendingNavigationTab, setPendingNavigationTab] = useState<TabId | null>(null);
  const [pendingLogout, setPendingLogout] = useState(false);
  const [pendingDraftLabel, setPendingDraftLabel] = useState("");
  const [navigationSaveMessage, setNavigationSaveMessage] = useState("");
  const [isSavingBeforeNavigation, setIsSavingBeforeNavigation] = useState(false);
  const workflowNavigationGuardRef = useRef<WorkflowNavigationGuard | null>(null);
  const visibleTabs = useMemo(() => tabs.filter((tab) => tabAllowed(tab.id, currentUser)), [currentUser]);
  const ActiveIcon = tabs.find((tab) => tab.id === activeTab)?.icon ?? BarChart3;

  const requestTabChange = (nextTab: TabId) => {
    if (nextTab === activeTab) {
      return;
    }
    const workflowGuard = workflowNavigationGuardRef.current;
    if (activeTab === "workflow" && workflowGuard?.hasUnsavedChanges()) {
      setPendingDraftLabel(workflowGuard.draftLabel());
      setPendingNavigationTab(nextTab);
      setNavigationSaveMessage("");
      return;
    }
    setActiveTab(nextTab);
  };

  const requestLogout = () => {
    const workflowGuard = workflowNavigationGuardRef.current;
    if (activeTab === "workflow" && workflowGuard?.hasUnsavedChanges()) {
      setPendingDraftLabel(workflowGuard.draftLabel());
      setPendingLogout(true);
      setNavigationSaveMessage("");
      return;
    }
    onLogout();
  };

  const leaveWorkflowWithoutSaving = () => {
    if (pendingLogout) {
      onLogout();
    } else if (pendingNavigationTab) {
      setActiveTab(pendingNavigationTab);
    }
    setPendingNavigationTab(null);
    setPendingLogout(false);
    setNavigationSaveMessage("");
  };

  const saveWorkflowAndNavigate = async () => {
    const workflowGuard = workflowNavigationGuardRef.current;
    if ((!pendingNavigationTab && !pendingLogout) || !workflowGuard) {
      setPendingNavigationTab(null);
      setPendingLogout(false);
      return;
    }
    setIsSavingBeforeNavigation(true);
    setNavigationSaveMessage("");
    try {
      const saved = await workflowGuard.saveDraft();
      if (!saved) {
        setNavigationSaveMessage("The draft could not be saved. Stay on this page and try again.");
        return;
      }
      if (pendingLogout) {
        onLogout();
      } else if (pendingNavigationTab) {
        setActiveTab(pendingNavigationTab);
      }
      setPendingNavigationTab(null);
      setPendingLogout(false);
    } finally {
      setIsSavingBeforeNavigation(false);
    }
  };

  useEffect(() => {
    const themeDefaultVersion = "light-default-v1";
    const storedDefaultVersion = localStorage.getItem("justice_kp_theme_default_version");
    const storedTheme = localStorage.getItem("justice_kp_theme");

    if (storedDefaultVersion !== themeDefaultVersion) {
      localStorage.setItem("justice_kp_theme", "light");
      localStorage.setItem("justice_kp_theme_default_version", themeDefaultVersion);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDarkMode(false);
    } else if (storedTheme === "light" || storedTheme === "dark") {
      setDarkMode(storedTheme === "dark");
    }
    setThemePreferenceLoaded(true);
  }, []);

  useEffect(() => {
    if (!themePreferenceLoaded) {
      return;
    }
    localStorage.setItem("justice_kp_theme", darkMode ? "dark" : "light");
    document.documentElement.dataset.theme = darkMode ? "dark" : "light";
  }, [darkMode, themePreferenceLoaded]);

  useEffect(() => {
    if (!visibleTabs.some((tab) => tab.id === activeTab) && visibleTabs[0]) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setActiveTab(visibleTabs[0].id);
    }
  }, [activeTab, visibleTabs]);

  return (
    <main className={`min-h-screen ${darkMode ? "theme-dark bg-slate-950" : "theme-light bg-gray-100"} text-gray-950`}>
      <div className="lg:grid lg:min-h-screen lg:grid-cols-[288px_1fr]">
        <aside className={`border-b lg:sticky lg:top-0 lg:h-screen lg:overflow-hidden lg:border-b-0 lg:border-r ${darkMode ? "border-white/10 bg-slate-950 text-slate-100" : "border-gray-200 bg-white text-gray-950"}`}>
          <div className="flex h-full flex-col">
            <div className={`flex h-16 items-center gap-3 border-b px-6 ${darkMode ? "border-white/10" : "border-gray-200"}`}>
              <span className={`grid size-10 place-items-center rounded-lg border ${darkMode ? "border-sky-300/20 bg-sky-400/10 text-sky-200" : "border-blue-100 bg-blue-50 text-blue-700"}`}>
                <Scale size={24} />
              </span>
              <p className={`text-xl font-black ${darkMode ? "text-white" : "text-gray-950"}`}>JUSTICE-KP <span className={darkMode ? "text-sky-300" : "text-blue-600"}>2.0</span></p>
            </div>
            <nav className="grid gap-2 p-4">
              <p className={`px-3 py-2 text-xs font-black uppercase tracking-wide ${darkMode ? "text-slate-500" : "text-gray-400"}`}>Main Navigation</p>
              {visibleTabs.map((tab) => {
                const Icon = tab.icon;
                const active = tab.id === activeTab;
                return (
                  <button
                    className={`flex h-11 items-center gap-3 rounded-md px-3 text-left text-sm font-bold transition ${
                      active ? "bg-blue-600 text-white shadow-lg shadow-blue-600/25" : darkMode ? "text-slate-400 hover:bg-white/[0.06] hover:text-sky-100" : "text-gray-700 hover:bg-blue-50 hover:text-blue-700"
                    }`}
                    key={tab.id}
                    onClick={() => requestTabChange(tab.id)}
                    type="button"
                  >
                    <Icon size={18} />
                    {tab.label}
                  </button>
                );
              })}
            </nav>
            <div className={`mt-auto border-t p-4 ${darkMode ? "border-white/10" : "border-gray-200"}`}>
              <button className={`flex h-11 w-full items-center justify-center gap-2 rounded-md border text-sm font-black transition ${darkMode ? "border-rose-300/20 text-rose-300 hover:bg-rose-500/10" : "border-red-200 text-red-600 hover:bg-red-50"}`} onClick={requestLogout} type="button">
                <LogOut size={17} />
                Sign Out
              </button>
            </div>
          </div>
        </aside>

        <section className="min-w-0">
          <TopBar darkMode={darkMode} />
          <div className={`theme-surface min-h-[calc(100vh-69px)] p-4 sm:p-6 lg:p-8 ${darkMode ? "bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.16),transparent_32%),linear-gradient(180deg,#0f172a_0%,#020617_58%,#030712_100%)]" : "bg-gray-100"}`}>
            <div className="sr-only">
              <ActiveIcon />
            </div>
            {activeTab === "dashboard" && <DashboardTab onSwitchTab={requestTabChange} />}
            {activeTab === "workflow" && (
              <WorkflowTab
                currentUser={currentUser}
                navigationGuardRef={workflowNavigationGuardRef}
                onOpenCases={() => setActiveTab("cases")}
              />
            )}
            {activeTab === "cases" && <CasesTab onNewBlotter={() => requestTabChange("workflow")} />}
            {activeTab === "transcripts" && <SavedTranscriptsTab />}
            {activeTab === "forms" && <FormsTab />}
            {activeTab === "reports" && <ReportsTab />}
            {activeTab === "validation" && <ValidationTab />}
            {activeTab === "settings" && <SettingsTab currentUser={currentUser} darkMode={darkMode} onDarkModeChange={setDarkMode} />}
          </div>
        </section>
      </div>
      {(pendingNavigationTab || pendingLogout) && (
        <ModalPortal
          onDismiss={() => {
            if (!isSavingBeforeNavigation) {
              setPendingNavigationTab(null);
              setPendingLogout(false);
              setNavigationSaveMessage("");
            }
          }}
        >
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-slate-950/70 p-4 backdrop-blur-sm"
          onMouseDown={() => {
            if (!isSavingBeforeNavigation) {
              setPendingNavigationTab(null);
              setPendingLogout(false);
              setNavigationSaveMessage("");
            }
          }}
        >
          <section
            aria-describedby="unsaved-workflow-description"
            aria-labelledby="unsaved-workflow-title"
            aria-modal="true"
            className={`max-h-[calc(100vh-2rem)] w-full max-w-lg overflow-y-auto rounded-xl border p-6 shadow-2xl ${darkMode ? "border-slate-600 bg-slate-900 text-slate-100" : "border-gray-200 bg-white text-gray-950"}`}
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 shrink-0 text-amber-500" size={24} />
              <div>
                <h2 className="text-xl font-black" id="unsaved-workflow-title">Unsaved workflow changes</h2>
                <p className={`mt-2 text-sm leading-6 ${darkMode ? "text-slate-300" : "text-gray-600"}`} id="unsaved-workflow-description">
                  Changes to {pendingDraftLabel || "this workflow draft"} have not been saved. Save the draft before {pendingLogout ? "signing out" : "opening another section"}, or continue without saving to discard those changes.
                </p>
              </div>
            </div>
            {navigationSaveMessage && (
              <p className="mt-4 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm font-bold text-red-700" role="alert">
                {navigationSaveMessage}
              </p>
            )}
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <AppButton disabled={isSavingBeforeNavigation} onClick={() => setPendingNavigationTab(null)}>Stay on Workflow</AppButton>
              <AppButton disabled={isSavingBeforeNavigation} onClick={leaveWorkflowWithoutSaving} tone="danger">{pendingLogout ? "Sign Out Without Saving" : "Leave Without Saving"}</AppButton>
              <AppButton disabled={isSavingBeforeNavigation} onClick={() => saveWorkflowAndNavigate().catch(() => setNavigationSaveMessage("The draft could not be saved. Stay on this page and try again."))} tone="primary">
                <Save size={16} />
                {isSavingBeforeNavigation ? "Saving..." : pendingLogout ? "Save Draft & Sign Out" : "Save Draft & Continue"}
              </AppButton>
            </div>
          </section>
        </div>
        </ModalPortal>
      )}
    </main>
  );
}

export default function JusticeDashboard() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  useEffect(() => {
    const sessionController = new AbortController();
    const sessionTimeout = window.setTimeout(() => sessionController.abort(), 2500);
    const storedCsrf = localStorage.getItem("justice_kp_csrf");
    if (storedCsrf) {
      axios.defaults.headers.common["X-CSRF-Token"] = storedCsrf;
    }
    axios
      .get<CurrentUser>(`${API_BASE_URL}/api/auth/me`, { signal: sessionController.signal })
      .then((response) => {
        if (response.data.csrf_token) {
          setCsrfToken(response.data.csrf_token);
        }
        setCurrentUser(response.data);
      })
      .catch(() => {
        clearCsrfToken();
        setCurrentUser(null);
      })
      .finally(() => {
        window.clearTimeout(sessionTimeout);
        setIsCheckingSession(false);
      });

    return () => {
      window.clearTimeout(sessionTimeout);
      sessionController.abort();
    };
  }, []);

  const logoutUser = async () => {
    try {
      await axios.post(`${API_BASE_URL}/api/auth/logout`);
    } catch {
      // Local state cleanup still matters if the server session has expired.
    }
    clearCsrfToken();
    setCurrentUser(null);
  };

  if (isCheckingSession) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-100 text-gray-950">
        <p className="text-sm font-black text-gray-600">Checking secure session...</p>
      </main>
    );
  }

  if (!currentUser) {
    return <LoginScreen onLogin={setCurrentUser} />;
  }

  return <MainPage currentUser={currentUser} onLogout={logoutUser} />;
}
