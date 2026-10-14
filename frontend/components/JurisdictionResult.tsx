import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import type { AnalyzeCaseResponse } from "./CaseAnalysis";
import { formatDisplayLabel, formatDisplayList } from "./displayText";

const decisionLabels = {
  ambiguous_manual_review: "Ambiguous / Manual Review",
  outside_kp: "Outside KP",
  refer_to_pnp_wcpc_or_authority: "Refer to PNP/WCPC or Authority",
  within_kp: "Within KP",
};

export default function JurisdictionResult({ analysis }: { analysis: AnalyzeCaseResponse }) {
  const tone =
    analysis.jurisdiction_decision === "within_kp"
      ? "green"
      : analysis.jurisdiction_decision === "refer_to_pnp_wcpc_or_authority"
        ? "red"
        : analysis.jurisdiction_decision === "outside_kp"
          ? "amber"
          : "gray";
  const Icon = tone === "green" ? CheckCircle2 : tone === "red" ? AlertTriangle : tone === "amber" ? XCircle : HelpCircle;
  const styles = {
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    gray: "border-gray-200 bg-gray-50 text-gray-800",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    red: "border-red-200 bg-red-50 text-red-800",
  };

  return (
    <section className={`jurisdiction-result jurisdiction-result-${tone} rounded-lg border p-5 ${styles[tone]}`}>
      <div className="flex items-start gap-3">
        <Icon className="mt-1 shrink-0" size={24} />
        <div>
          <p className="text-xs font-black uppercase tracking-wide">Jurisdiction Result</p>
          <h3 className="mt-1 text-xl font-black">{decisionLabels[analysis.jurisdiction_decision]}</h3>
          <p className="mt-3 text-sm font-bold leading-6">{analysis.recommended_next_action}</p>
        </div>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-md bg-white/75 p-3">
          <p className="text-xs font-black uppercase text-gray-500">Exclusion Ground</p>
          <p className="mt-1 text-sm font-black text-gray-950">{formatDisplayLabel(analysis.exclusion_ground)}</p>
        </div>
        <div className="rounded-md bg-white/75 p-3">
          <p className="text-xs font-black uppercase text-gray-500">Confidence</p>
          <p className="mt-1 text-sm font-black text-gray-950">{formatDisplayLabel(analysis.confidence_level)}</p>
        </div>
        <div className="rounded-md bg-white/75 p-3">
          <p className="text-xs font-black uppercase text-gray-500">Missing Fields</p>
          <p className="mt-1 text-sm font-black text-gray-950">
            {analysis.missing_fields.length ? formatDisplayList(analysis.missing_fields) : "None"}
          </p>
        </div>
      </div>
    </section>
  );
}
