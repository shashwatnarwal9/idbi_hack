import {
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  PhoneCall,
  Target,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

// Exactly four pages. Upload is a modal on Overview; Loan Details and the
// Behaviour view are drill-ins, not nav items. Pipeline/Validation UIs removed.
const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/customers", label: "Customers", icon: Users },
  { to: "/intent", label: "Intent", icon: TrendingUp },
  { to: "/leads", label: "Leads", icon: Target },
  { to: "/outreach", label: "Outreach", icon: PhoneCall },
];

// Collapsed/expanded is a pure UI preference, localStorage is the right and
// only place for it in this project. Do not extend this to real app data.
const STORAGE_KEY = "aayai:sidebar-collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      /* ignore write failures (private mode etc.) */
    }
  }, [collapsed]);

  return (
    <aside
      className={`flex shrink-0 flex-col bg-forest-deep transition-[width] duration-200 ease-in-out ${
        collapsed ? "w-16" : "w-60"
      }`}
    >
      <div
        className={`flex pb-6 pt-7 ${
          collapsed ? "flex-col items-center gap-3 px-2" : "items-start justify-between px-6"
        }`}
      >
        {collapsed ? (
          <div className="text-2xl font-bold tracking-tight text-white">आ</div>
        ) : (
          <div>
            <div className="text-2xl font-bold tracking-tight text-white">
              आय·AI
            </div>
            <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-mint/70">
              Financial Intelligence
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white/60 transition-colors hover:bg-white/10 hover:text-white"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            title={collapsed ? label : undefined}
            className={({ isActive }) => {
              const base = `flex items-center rounded-xl py-2.5 text-sm font-medium transition-colors ${
                collapsed ? "justify-center px-0" : "gap-3 px-3.5"
              }`;
              return isActive
                ? `${base} bg-mint text-forest-deep`
                : `${base} text-white/65 hover:bg-white/10 hover:text-white`;
            }}
          >
            <Icon size={18} strokeWidth={1.8} className="shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
