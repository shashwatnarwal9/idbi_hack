import { ArrowLeft } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

/** Shared origin passed via React Router location state so a customer view can
 * return to the exact screen + view it was opened from (Leads, an Act-now list,
 * an Overview quadrant, …). Navigate with `{ state: { from, fromLabel } }`. */
export interface NavOrigin {
  from: string; // full path (may include query string) to return to
  fromLabel: string; // human label shown on the Back button
}

interface Props {
  /** Where to go when no origin is in location state. */
  fallback?: string;
  fallbackLabel?: string;
}

/** Back button that reads the origin from location state and returns to it. */
export function BackButton({ fallback = "/intent", fallbackLabel = "search" }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const origin = (location.state ?? null) as Partial<NavOrigin> | null;
  const to = origin?.from ?? fallback;
  const label = origin?.fromLabel ?? fallbackLabel;
  return (
    <button
      type="button"
      onClick={() => navigate(to)}
      className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-3.5 py-2 text-sm font-medium text-ink-soft transition-colors hover:bg-sage"
    >
      <ArrowLeft size={15} strokeWidth={1.8} />
      Back to {label}
    </button>
  );
}
