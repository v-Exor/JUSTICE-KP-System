"use client";

import axios from "axios";
import { useMemo, useState } from "react";
import { AlertTriangle, Database, PlayCircle, Save } from "lucide-react";
import CaseInfoForm, { applicableNumericFields } from "./CaseInfoForm";
import JurisdictionResult from "./JurisdictionResult";
import KeywordResults from "./KeywordResults";
import XAITracePanel from "./XAITracePanel";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type CaseInformation = {
  case_id: string;
  barangay_name: string;
  city_municipality: string;
  case_year: number | "";
  case_type: "civil" | "criminal" | "administrative" | "other";
  dispute_category:
    | ""
    | "debt"
    | "boundary"
    | "family_dispute"
    | "physical_injury"
    | "nuisance"
    | "threat"
    | "property_damage"
    | "online_defamation"
    | "neighbor_altercation"
    | "harassment_unjust_vexation"
    | "business_defamation"
    | "other";
  complainant_residency: "same_barangay" | "adjacent_barangay" | "different_municipality" | "";
  respondent_residency: "same_barangay" | "adjacent_barangay" | "different_municipality" | "";
  debt_amount_php: number | "" | null;
  maximum_penalty_years: number | "" | null;
  fine_amount_php: number | "" | null;
  government_party_involved: boolean;
  already_filed_in_court: boolean;
  has_vawc_or_child_abuse_indicators: boolean;
};

export type AnalyzeCaseResponse = {
  transcript_id: number | null;
  case_information: CaseInformation;
  extracted_entities: Record<string, unknown>;
  detected_keywords: {
    detected_keywords: string[];
    keyword_count: number;
    vawc_trigger: boolean;
  };
  jurisdiction_decision:
    | "within_kp"
    | "outside_kp"
    | "refer_to_pnp_wcpc_or_authority"
    | "ambiguous_manual_review";
  exclusion_ground: string;
  confidence_level: "high" | "medium" | "low";
  missing_fields: string[];
  recommended_next_action: string;
  xai_trace: string[];
  rule_results: Array<Record<string, unknown>>;
};

export const defaultCaseInformation: CaseInformation = {
  case_id: `KP-${new Date().getFullYear()}-0001`,
  barangay_name: "",
  city_municipality: "",
  case_year: new Date().getFullYear(),
  case_type: "civil",
  dispute_category: "",
  complainant_residency: "same_barangay",
  respondent_residency: "same_barangay",
  debt_amount_php: "",
  maximum_penalty_years: 0,
  fine_amount_php: 0,
  government_party_involved: false,
  already_filed_in_court: false,
  has_vawc_or_child_abuse_indicators: false,
};

export function toApiCaseInformation(caseInformation: CaseInformation) {
  const nullableNumber = (value: number | "" | null) => (value === "" || value === null ? null : Number(value));
  const applicableFields = applicableNumericFields(caseInformation.dispute_category);

  return {
    ...caseInformation,
    case_year: caseInformation.case_year === "" ? null : Number(caseInformation.case_year),
    complainant_residency: caseInformation.complainant_residency || null,
    respondent_residency: caseInformation.respondent_residency || null,
    debt_amount_php: applicableFields.debt_amount_php ? nullableNumber(caseInformation.debt_amount_php) : null,
    maximum_penalty_years: applicableFields.maximum_penalty_years ? nullableNumber(caseInformation.maximum_penalty_years) : null,
    fine_amount_php: applicableFields.fine_amount_php ? nullableNumber(caseInformation.fine_amount_php) : null,
  };
}

function displayValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : "None detected";
  }
  if (value === null || value === undefined || value === "") {
    return "None detected";
  }
  return String(value);
}

export default function CaseAnalysis({
  transcript,
  transcriptId,
  onAnalysisComplete,
  onAnalysisSaved,
}: {
  transcript: string;
  transcriptId: number | null;
  onAnalysisComplete?: (analysis: AnalyzeCaseResponse) => void;
  onAnalysisSaved?: (caseId: string, analysisId: number) => void;
}) {
  const [caseInformation, setCaseInformation] = useState<CaseInformation>(defaultCaseInformation);
  const [analysis, setAnalysis] = useState<AnalyzeCaseResponse | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const transcriptPreview = useMemo(() => transcript.trim() || "No edited transcript is available yet.", [transcript]);

  const analyzeCase = async () => {
    if (!transcript.trim()) {
      setErrorMessage("Transcript is empty. Complete the editable transcript before running Phase 2 analysis.");
      return;
    }
    if (!caseInformation.dispute_category) {
      setErrorMessage("Select a dispute category before analyzing the case.");
      return;
    }

    setIsAnalyzing(true);
    setErrorMessage("");
    setStatusMessage("");

    try {
      const response = await axios.post<AnalyzeCaseResponse>(`${API_BASE_URL}/analyze-case`, {
        transcript_id: transcriptId,
        transcript_text: transcript,
        case_information: toApiCaseInformation(caseInformation),
      });
      setAnalysis(response.data);
      setStatusMessage("Case analysis completed. Review the decision, entities, keywords, and XAI trace.");
      onAnalysisComplete?.(response.data);
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setErrorMessage(detail ?? "Case analysis failed. Check the backend connection and required fields.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const saveAnalysis = async () => {
    if (!analysis) {
      return;
    }

    setIsSaving(true);
    setErrorMessage("");
    setStatusMessage("");

    try {
      const response = await axios.post<{ id: number; message: string }>(`${API_BASE_URL}/save-case-analysis`, analysis);
      onAnalysisSaved?.(analysis.case_information.case_id, response.data.id);
      setStatusMessage(`${response.data.message} Record #${response.data.id}. Workflow Panel 7 is now connected to this case.`);
    } catch (error) {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      setErrorMessage(detail ?? "Saving case analysis failed. Check the backend connection and try again.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-black uppercase tracking-wide text-blue-700">Phase 2</p>
          <h2 className="mt-1 text-2xl font-black text-gray-950">Case Analysis and Jurisdiction Validation</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
            JUSTICE-KP is a decision-support system. Final authority remains with barangay officials.
          </p>
        </div>
        <div className="rounded-md border border-blue-100 bg-blue-50 px-4 py-3 text-xs font-bold text-blue-800">
          RA 7160 Rule Engine
        </div>
      </div>

      <section className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="font-black text-gray-950">Editable Transcript Preview</h3>
            <p className="mt-1 text-xs font-bold text-gray-500">
              {transcriptId ? `Linked to transcript #${transcriptId}` : "Uses the current edited text"}
            </p>
          </div>
        </div>
        <pre className="mt-4 max-h-72 overflow-auto rounded-md border border-gray-200 bg-gray-50 p-4 whitespace-pre-wrap font-mono text-sm leading-6 text-gray-800">
          {transcriptPreview}
        </pre>
      </section>

      <CaseInfoForm value={caseInformation} onChange={setCaseInformation} />

      <div className="flex flex-wrap items-center gap-3">
        <button
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-blue-600 bg-blue-600 px-4 text-sm font-black text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:border-gray-200 disabled:bg-gray-100 disabled:text-gray-400"
          disabled={isAnalyzing || !transcript.trim() || !caseInformation.dispute_category}
          onClick={analyzeCase}
          type="button"
        >
          <PlayCircle size={17} />
          {isAnalyzing ? "Analyzing..." : "Analyze Case"}
        </button>
        <button
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-4 text-sm font-black text-gray-900 shadow-sm transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:bg-gray-100 disabled:text-gray-400"
          disabled={isSaving || !analysis}
          onClick={saveAnalysis}
          type="button"
        >
          {isSaving ? <Database size={17} /> : <Save size={17} />}
          {isSaving ? "Saving..." : "Save Case Analysis"}
        </button>
      </div>

      {statusMessage && <p className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm font-bold text-emerald-700">{statusMessage}</p>}
      {errorMessage && <p className="rounded-md border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700">{errorMessage}</p>}

      {analysis?.detected_keywords.vawc_trigger && (
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
          <AlertTriangle className="mt-0.5 shrink-0" size={20} />
          <p className="text-sm font-bold leading-6">
            Sensitive case detected. Do not proceed with normal barangay mediation. Refer to the proper authority.
          </p>
        </div>
      )}

      {analysis && (
        <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
          <JurisdictionResult analysis={analysis} />
          <KeywordResults detectedKeywords={analysis.detected_keywords} />
          <section className="rounded-lg border border-gray-200 bg-white p-5">
            <h3 className="font-black text-gray-950">Extracted Entities</h3>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {Object.entries(analysis.extracted_entities).map(([key, value]) => (
                <div className="rounded-md border border-gray-200 bg-gray-50 p-3" key={key}>
                  <p className="text-xs font-black uppercase tracking-wide text-gray-500">{key.replaceAll("_", " ")}</p>
                  <p className="mt-2 break-words text-sm font-bold text-gray-900">{displayValue(value)}</p>
                </div>
              ))}
            </div>
          </section>
          <XAITracePanel trace={analysis.xai_trace} />
        </div>
      )}
    </div>
  );
}
