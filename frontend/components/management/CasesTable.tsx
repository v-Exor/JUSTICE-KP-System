"use client";

import { AlertTriangle, FileText, LoaderCircle, Shield } from "lucide-react";

export type ManagementCaseRecord = {
  id: string;
  parties: string;
  type: string;
  dateFiled: string;
  status: string;
  tone: "amber" | "green" | "red" | "blue";
  workflow_id?: string;
  is_sensitive: boolean;
  duplicate_case_id?: boolean;
};

const toneClasses = {
  amber: "border-amber-200 bg-amber-100 text-amber-800",
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  green: "border-emerald-200 bg-emerald-100 text-emerald-700",
  red: "border-red-200 bg-red-50 text-red-700",
};

export default function CasesTable({
  cases,
  loading,
  total,
  hasFilters,
  loadingWorkflowId,
  formatDate,
  onOpenSummary,
}: {
  cases: ManagementCaseRecord[];
  loading: boolean;
  total: number;
  hasFilters: boolean;
  loadingWorkflowId: string;
  formatDate: (value: string) => string;
  onOpenSummary: (workflowId?: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] border-collapse text-left text-sm">
        <thead className="bg-gray-50 text-xs uppercase text-gray-500">
          <tr>{['Case ID', 'Parties Involved', 'Case Type', 'Date Filed', 'Status', 'Actions'].map((heading) => <th className="px-6 py-4" key={heading}>{heading}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {cases.map((item) => (
            <tr className="case-record-row transition hover:bg-gray-50" key={item.workflow_id ?? item.id}>
              <td className="px-6 py-4 font-black text-gray-950">
                <span>{item.id}</span>
                {item.is_sensitive && <span className="mt-1 flex items-center gap-1 text-[11px] font-black uppercase tracking-wide text-red-700"><Shield size={12} /> Sensitive</span>}
                {item.duplicate_case_id && <span className="mt-1 flex items-center gap-1 text-[11px] font-black uppercase tracking-wide text-amber-700"><AlertTriangle size={12} /> Historical duplicate ID</span>}
              </td>
              <td className="px-6 py-4 text-gray-700">{item.parties}</td>
              <td className="px-6 py-4 text-gray-700">{item.type}</td>
              <td className="px-6 py-4 text-gray-700">{formatDate(item.dateFiled)}</td>
              <td className="px-6 py-4"><span className={`inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-bold ${toneClasses[item.tone]}`}>{item.status}</span></td>
              <td className="px-6 py-4"><button aria-label={`View summary for ${item.id}`} className="inline-flex h-9 items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 text-xs font-black text-blue-700 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50" disabled={!item.workflow_id || Boolean(loadingWorkflowId)} onClick={() => onOpenSummary(item.workflow_id)} type="button">{loadingWorkflowId === item.workflow_id ? <LoaderCircle className="animate-spin" size={15} /> : <FileText size={15} />} Summary</button></td>
            </tr>
          ))}
          {!loading && !total && <tr><td className="px-6 py-12 text-center text-sm font-bold text-gray-500" colSpan={6}>{hasFilters ? "No finalized cases match the current search and filters." : "No finalized cases yet. Complete Resolution & Forms and select Save Outcome & Finalize to create the first record."}</td></tr>}
          {loading && <tr><td className="px-6 py-12 text-center text-sm font-bold text-gray-500" colSpan={6}>Loading finalized cases...</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
