"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

export default function Pagination({
  page,
  totalPages,
  disabled,
  onChange,
  ariaLabel,
}: {
  page: number;
  totalPages: number;
  disabled?: boolean;
  onChange: (page: number) => void;
  ariaLabel: string;
}) {
  const pages = totalPages <= 5
    ? Array.from({ length: totalPages }, (_, index) => index + 1)
    : Array.from(
      { length: 5 },
      (_, index) => Math.min(Math.max(page - 2, 1), totalPages - 4) + index,
    );

  return (
    <nav aria-label={ariaLabel} className="flex flex-wrap items-center gap-2">
      <button
        className="inline-flex h-9 items-center gap-1 rounded-md border border-gray-300 px-3 font-bold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
        disabled={disabled || page <= 1}
        onClick={() => onChange(Math.max(1, page - 1))}
        type="button"
      >
        <ChevronLeft size={16} /> Previous
      </button>
      {pages.map((pageNumber) => (
        <button
          aria-current={pageNumber === page ? "page" : undefined}
          aria-label={`Go to page ${pageNumber}`}
          className={`grid size-9 place-items-center rounded-md border font-black transition ${pageNumber === page ? "border-blue-600 bg-blue-600 text-white" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`}
          disabled={disabled}
          key={pageNumber}
          onClick={() => onChange(pageNumber)}
          type="button"
        >
          {pageNumber}
        </button>
      ))}
      <button
        className="inline-flex h-9 items-center gap-1 rounded-md border border-gray-300 px-3 font-bold text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
        disabled={disabled || !totalPages || page >= totalPages}
        onClick={() => onChange(Math.min(totalPages, page + 1))}
        type="button"
      >
        Next <ChevronRight size={16} />
      </button>
    </nav>
  );
}
