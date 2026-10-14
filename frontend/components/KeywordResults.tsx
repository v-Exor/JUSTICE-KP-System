import { ShieldAlert } from "lucide-react";
import type { AnalyzeCaseResponse } from "./CaseAnalysis";
import { humanizeDisplayText } from "./displayText";

export default function KeywordResults({
  detectedKeywords,
}: {
  detectedKeywords: AnalyzeCaseResponse["detected_keywords"];
}) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-black text-gray-950">Detected Keywords</h3>
          <p className="mt-1 text-sm text-gray-600">VAWC and sensitive-case keyword scan.</p>
        </div>
        <span className={`inline-flex min-h-8 items-center rounded-md border px-3 text-xs font-black ${detectedKeywords.vawc_trigger ? "border-red-200 bg-red-50 text-red-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>
          {detectedKeywords.vawc_trigger ? "VAWC Trigger: Yes" : "VAWC Trigger: No"}
        </span>
      </div>
      <div className="mt-5 flex items-center gap-3 rounded-md border border-gray-200 bg-gray-50 p-4">
        <ShieldAlert className={detectedKeywords.vawc_trigger ? "text-red-600" : "text-gray-400"} size={22} />
        <div>
          <p className="text-xs font-black uppercase text-gray-500">Keyword Count</p>
          <p className="text-lg font-black text-gray-950">{detectedKeywords.keyword_count}</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {detectedKeywords.detected_keywords.length ? (
          detectedKeywords.detected_keywords.map((keyword) => (
            <span className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-black text-red-700" key={keyword}>
              {humanizeDisplayText(keyword)}
            </span>
          ))
        ) : (
          <span className="rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-black text-gray-500">
            No sensitive keywords detected
          </span>
        )}
      </div>
    </section>
  );
}
