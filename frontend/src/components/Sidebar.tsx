import {
  HandCoins,
  LayoutDashboard,
  ShieldCheck,
  UploadCloud,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/customers", label: "Customers", icon: Users },
  { to: "/loan-assessment", label: "Loan Assessment", icon: HandCoins },
  { to: "/upload", label: "Upload & Analyze", icon: UploadCloud },
  { to: "/pipeline", label: "Pipeline", icon: Workflow },
  { to: "/validation", label: "Validation", icon: ShieldCheck },
];

function navClasses({ isActive }: { isActive: boolean }): string {
  const base =
    "flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-colors";
  return isActive
    ? `${base} bg-mint text-forest-deep`
    : `${base} text-white/65 hover:bg-white/10 hover:text-white`;
}

export function Sidebar() {
  return (
    <aside className="flex w-60 shrink-0 flex-col bg-forest-deep">
      <div className="px-6 pb-6 pt-7">
        <div className="text-2xl font-bold tracking-tight text-white">आय·AI</div>
        <div className="mt-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-mint/70">
          Financial Intelligence
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} end={to === "/"} className={navClasses}>
            <Icon size={18} strokeWidth={1.8} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
