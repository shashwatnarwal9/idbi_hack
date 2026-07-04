import { Bell, Search } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

const TITLES: Record<string, string> = {
  "/": "Overview",
  "/analysis": "Deep Analysis",
  "/customers": "Customer Profile",
  "/loan-assessment": "Loan Assessment",
  "/upload": "Upload & Analyze",
  "/pipeline": "Pipeline Runs",
  "/validation": "Validation",
};

export function Topbar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const title = TITLES[pathname] ?? "Overview";

  const submit = () => {
    const query = q.trim();
    if (!query) return;
    setQ("");
    navigate(`/customers?id=${encodeURIComponent(query)}`);
  };

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-line bg-white px-6">
      <h1 className="text-lg font-semibold">{title}</h1>

      <div className="flex items-center gap-3">
        <label className="hidden items-center gap-2 rounded-xl border border-line bg-cream px-3 py-2 md:flex">
          <Search size={15} className="text-ink-muted" />
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Open customer by id…"
            className="w-48 bg-transparent text-sm outline-none placeholder:text-ink-muted"
          />
        </label>

        <button
          type="button"
          aria-label="Notifications"
          className="rounded-xl border border-line bg-white p-2.5 text-ink-soft transition-colors hover:bg-sage"
        >
          <Bell size={17} strokeWidth={1.8} />
        </button>

        <div className="flex items-center gap-2.5 pl-1">
          <div className="flex size-9 items-center justify-center rounded-full bg-forest text-xs font-semibold text-white">
            AA
          </div>
          <div className="hidden leading-tight lg:block">
            <div className="text-sm font-medium">Analyst</div>
            <div className="text-xs text-ink-muted">IDBI Bank</div>
          </div>
        </div>
      </div>
    </header>
  );
}
