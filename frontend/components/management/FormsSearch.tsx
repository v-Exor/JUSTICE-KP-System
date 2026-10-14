"use client";

import ManagementSearchInput from "./ManagementSearchInput";

export default function FormsSearch({
  query,
  onQueryChange,
  stage,
  onStageChange,
  resultCount,
  totalCount,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  stage: string;
  onStageChange: (value: string) => void;
  resultCount: number;
  totalCount: number;
}) {
  return (
    <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-start">
      <ManagementSearchInput
        id="kp-form-search"
        label="Search KP forms"
        onChange={onQueryChange}
        placeholder="Search KP forms..."
        resultCount={resultCount}
        resultLabel="forms"
        totalCount={totalCount}
        value={query}
      />
      <label className="block">
        <span className="sr-only">Filter KP forms by stage</span>
        <select
          aria-label="Filter KP forms by stage"
          className="h-10 w-full rounded-md border border-gray-300 bg-white px-4 text-sm font-bold sm:w-auto"
          onChange={(event) => onStageChange(event.target.value)}
          value={stage}
        >
          {['All', 'Complaint', 'Notice', 'Pangkat', 'Settlement', 'Certification', 'Execution'].map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
