import { useLocation } from "react-router-dom";

const TITLES: Record<string, string> = {
  "/": "Overview",
  "/analysis": "Deep Analysis",
  "/customers": "Customer Profile",
  "/loan-assessment": "Loan Assessment",
  "/upload": "Upload & Analyze",
  "/pipeline": "Pipeline Runs",
  "/validation": "Validation",
};

function titleFor(pathname: string): string {
  if (TITLES[pathname]) return TITLES[pathname];
  if (pathname.startsWith("/loan-assessment/")) return "Loan Details";
  return "Overview";
}

export function Topbar() {
  const { pathname } = useLocation();
  const title = titleFor(pathname);

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-line bg-white px-6">
      <h1 className="text-lg font-semibold">{title}</h1>

      <div className="flex items-center gap-2.5 pl-1">
        <div className="flex size-9 items-center justify-center rounded-full bg-forest text-xs font-semibold text-white">
          AA
        </div>
        <div className="hidden leading-tight lg:block">
          <div className="text-sm font-medium">Analyst</div>
          <div className="text-xs text-ink-muted">IDBI Bank</div>
        </div>
      </div>
    </header>
  );
}
