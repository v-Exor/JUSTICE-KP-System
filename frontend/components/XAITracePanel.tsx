import { Route } from "lucide-react";
import { humanizeDisplayText } from "./displayText";

export default function XAITracePanel({ trace }: { trace: string[] }) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5">
      <h3 className="flex items-center gap-2 font-black text-gray-950">
        <Route className="text-blue-600" size={18} />
        XAI Reasoning Trace
      </h3>
      <div className="mt-4 space-y-3">
        {trace.map((line, index) => (
          <p className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm font-bold leading-6 text-gray-800" key={`${line}-${index}`}>
            {humanizeDisplayText(line)}
          </p>
        ))}
      </div>
    </section>
  );
}
