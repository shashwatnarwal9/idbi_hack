import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "./components/AppShell";
import { getHealth } from "./lib/api";
import { Customers } from "./screens/Customers";
import { DeepAnalysis } from "./screens/DeepAnalysis";
import { LoanAssessment } from "./screens/LoanAssessment";
import { Overview } from "./screens/Overview";
import { Pipeline } from "./screens/Pipeline";
import { Upload } from "./screens/Upload";
import { Validation } from "./screens/Validation";

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
        <Route path="loan-assessment" element={<LoanAssessment />} />
        <Route path="upload" element={<Upload />} />
        <Route path="pipeline" element={<Pipeline />} />
        <Route path="validation" element={<Validation />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
