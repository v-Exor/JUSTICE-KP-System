import type { ReactNode } from "react";

export default function TranscriptNavigator({
  selectionLabel,
  children,
}: {
  selectionLabel: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm sm:p-5">
      <div>
        <h2 className="font-black text-gray-950">Transcript Navigator</h2>
        <p className="mt-1 text-sm text-gray-600">{selectionLabel}</p>
      </div>
      {children}
    </section>
  );
}
