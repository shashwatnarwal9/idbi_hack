import { PlayCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { getHealth } from "./lib/api";
import { Customers } from "./screens/Customers";
import { DeepAnalysis } from "./screens/DeepAnalysis";
import { Intent } from "./screens/Intent";
import { Leads } from "./screens/Leads";
import { LoanAssessment } from "./screens/LoanAssessment";
import { LoanDetails } from "./screens/LoanDetails";
import { Outreach } from "./screens/Outreach";
import { DEMO_URL, Overview } from "./screens/Overview";
import { QuadrantList } from "./screens/QuadrantList";
import { Upload } from "./screens/Upload";

export default function App() {
  // Surface API connectivity problems in the console; stay quiet on success.
  useEffect(() => {
    getHealth().catch((err: unknown) =>
      console.warn("aayai api unreachable:", err),
    );
  }, []);

  const [demoOpen, setDemoOpen] = useState(true);

  return (
    <>
      {demoOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-forest-deep/40 p-4 backdrop-blur-sm"
          onClick={() => setDemoOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-2xl border border-line bg-cream/95 p-6 text-center shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <PlayCircle size={32} className="mx-auto text-forest" />
            <h2 className="mt-3 text-base font-semibold text-ink">
              See the demo video
            </h2>
            <p className="mt-1 text-sm text-ink-soft">
              A short walkthrough of the dashboard.
            </p>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={() => setDemoOpen(false)}
                className="flex-1 rounded-xl border border-line bg-white px-4 py-2.5 text-sm font-medium text-ink-soft hover:bg-sage"
              >
                Cancel
              </button>
              <a
                href={DEMO_URL}
                target="_blank"
                rel="noreferrer"
                onClick={() => setDemoOpen(false)}
                className="flex-1 rounded-xl bg-gradient-to-r from-forest to-amber-400 px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
              >
                Open
              </a>
            </div>
          </div>
        </div>
      )}
      <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Overview />} />
        <Route path="analysis" element={<DeepAnalysis />} />
        <Route path="customers" element={<Customers />} />
        <Route path="intent" element={<Intent />} />
        <Route path="intent/:customerId" element={<Intent />} />
        <Route path="quadrant/:quadrant" element={<QuadrantList />} />
        <Route path="leads" element={<Leads />} />
        <Route path="outreach" element={<Outreach />} />
        <Route path="loan-assessment" element={<LoanAssessment />} />
        <Route path="loan-assessment/:customerId" element={<LoanDetails />} />
        <Route path="upload" element={<Upload />} />
        {/* Pipeline & Validation UI pages removed; their APIs remain. */}
        <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </>
  );
}
