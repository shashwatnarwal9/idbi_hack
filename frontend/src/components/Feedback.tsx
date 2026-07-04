import { CircleAlert } from "lucide-react";

export function Loading({ label = "Loading live data…" }: { label?: string }) {
  return <p className="py-10 text-center text-sm text-ink-muted">{label}</p>;
}

/** Honest failure state: shows the real error, never placeholder numbers. */
export function ErrorNote({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-negative/30 bg-negative/5 p-4 text-sm text-negative">
      <CircleAlert size={17} className="mt-0.5 shrink-0" />
      <div>
        <div className="font-semibold">Data unavailable</div>
        <p className="mt-0.5 text-negative/90">{message}</p>
      </div>
    </div>
  );
}
