import type { ReactNode } from "react";

export default function SavedDraftPicker({ children }: { children: ReactNode }) {
  return (
    <section aria-labelledby="saved-drafts-title" className="mt-5 overflow-hidden rounded-lg border border-gray-200 bg-gray-50">
      {children}
    </section>
  );
}
