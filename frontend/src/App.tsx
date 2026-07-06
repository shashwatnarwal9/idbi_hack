import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { getHealth } from "./lib/api";
import { Customers } from "./screens/Customers";
import { DeepAnalysis } from "./screens/DeepAnalysis";
import { Intent } from "./screens/Intent";
import { Leads } from "./screens/Leads";
import { LoanAssessment } from "./screens/LoanAssessment";
import { LoanDetails } from "./screens/LoanDetails";
import { Overview } from "./screens/Overview";
import { Upload } from "./screens/Upload";

export default function App() {
  // Surface API connectivity problems in the console; stay quiet on success.
  useEffect(() => {
    getHealth().catch((err: unknown) =>
      console.warn("aayai api unreachable:", err),
    );
  }, []);

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Overview />} />
        <Route path="analysis" element={<DeepAnalysis />} />
        <Route path="customers" element={<Customers />} />
        <Route path="intent" element={<Intent />} />
        <Route path="leads" element={<Leads />} />
        <Route path="loan-assessment" element={<LoanAssessment />} />
        <Route path="loan-assessment/:customerId" element={<LoanDetails />} />
        <Route path="upload" element={<Upload />} />
        {/* Pipeline & Validation UI pages removed; their APIs remain. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
