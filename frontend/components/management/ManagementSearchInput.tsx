"use client";

import { Search, X } from "lucide-react";

export default function ManagementSearchInput({
  id,
  label,
  placeholder,
  value,
  onChange,
  resultCount,
  totalCount,
  resultLabel = "results",
}: {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  resultCount?: number;
  totalCount?: number;
  resultLabel?: string;
}) {
  return (
    <div className="w-full sm:w-72">
      <label className="sr-only" htmlFor={id}>{label}</label>
      <div className="relative">
        <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={17} />
        <input
          className="h-10 w-full rounded-md border border-gray-300 bg-white pl-9 pr-10 text-sm text-gray-950 outline-none transition placeholder:text-gray-400 focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
          id={id}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          role="searchbox"
          type="text"
          value={value}
        />
        {value && (
          <button
            aria-label={`Clear ${label.toLowerCase()}`}
            className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md text-gray-400 transition hover:bg-gray-100 hover:text-gray-700"
            onClick={() => onChange("")}
            type="button"
          >
            <X size={15} />
          </button>
        )}
      </div>
      {resultCount !== undefined && totalCount !== undefined && (
        <p aria-live="polite" className="mt-1 text-right text-xs font-bold text-gray-500">
          {resultCount} of {totalCount} {resultLabel}
        </p>
      )}
    </div>
  );
}
