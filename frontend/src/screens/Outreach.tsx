import { useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  Loader,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { ErrorNote, Loading } from "../components/Feedback";
import { apiGet, apiPost } from "../lib/api";
import type {
  GenerateStatus,
  Interaction,
  InteractionStatus,
  OutreachQueue,
} from "../lib/apiTypes";
import { useApi, useInvalidateApi } from "../lib/useApi";

const QUEUE_KEY = ["api", "/outreach/queue"];

const STATUS_TONE: Record<InteractionStatus, BadgeTone> = {
  planned: "neutral",
  contacted: "brand",
  responded: "warning",
  converted: "success",
  dormant: "neutral",
};

/** Legal next steps per status (mirrors the backend state machine). */
const NEXT_STATUS: Record<InteractionStatus, InteractionStatus[]> = {
  planned: ["contacted", "dormant"],
  contacted: ["responded", "dormant"],
  responded: ["converted", "dormant"],
  converted: [],
  dormant: [],
};

const STATUS_LABEL: Record<InteractionStatus, string> = {
  planned: "Planned",
  contacted: "Contacted",
  responded: "Responded",
  converted: "Converted",
  dormant: "Dormant",
};

type Tab = "all" | "due" | "upcoming" | "planned" | "contacted";
type QueueRow = Interaction & { isDue: boolean };

function fmtWhen(iso: string | null): string {
  if (!iso) return "unscheduled";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InteractionCard({
  row,
  onStatus,
  onApprove,
}: {
  row: QueueRow;
  onStatus: (row: Interaction, status: InteractionStatus) => Promise<void>;
  onApprove: (row: Interaction) => Promise<void>;
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const wrap = (fn: () => Promise<void>) => async () => {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className={row.isDue ? "border-l-4 border-l-amber" : undefined}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() =>
                navigate(`/intent/${encodeURIComponent(row.cust_id)}`, {
                  state: { from: "/outreach", fromLabel: "Outreach" },
                })
              }
              className="font-mono text-sm font-semibold hover:text-forest"
            >
              {row.cust_id}
            </button>
            {row.product && (
              <span className="text-xs capitalize text-ink-soft">{row.product}</span>
            )}
            <Badge tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Badge>
            {row.isDue && <Badge tone="warning">Due</Badge>}
            {row.approved_at ? (
              <span className="inline-flex items-center gap-1 text-xs text-emerald">
                <ShieldCheck size={13} /> approved
              </span>
            ) : (
              <span className="text-xs text-amber">awaiting approval</span>
            )}
          </div>
          <div className="mt-1 flex items-center gap-1.5 text-xs text-ink-muted">
            <CalendarClock size={13} />
            {fmtWhen(row.scheduled_at)} · {row.channel ?? "channel tbd"}
          </div>
          {row.why_now && (
            <p className="mt-2 text-sm text-ink-soft">
              <span className="font-semibold text-ink">Why now: </span>
              {row.why_now}
            </p>
          )}
          {row.signals && row.signals.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {row.signals.map((s) => (
                <span
                  key={s}
                  className="rounded-full bg-mint px-2 py-0.5 font-mono text-[10px] text-forest-deep"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
          {row.drafted_message && (
            <div className="mt-2 flex items-start gap-2 rounded-xl bg-sage p-3 text-sm text-ink-soft">
              <MessageSquareText size={15} className="mt-0.5 shrink-0 text-forest" />
              <span>{row.drafted_message}</span>
            </div>
          )}
          {row.next_action && (
            <p className="mt-2 text-xs text-ink-muted">Next action: {row.next_action}</p>
          )}
        </div>

        <div className="flex shrink-0 flex-row flex-wrap gap-2 sm:flex-col sm:items-end">
          {!row.approved_at && row.status === "planned" && (
            <button
              type="button"
              disabled={busy}
              onClick={wrap(() => onApprove(row))}
              className="inline-flex items-center gap-1.5 rounded-xl bg-forest px-3 py-1.5 text-xs font-semibold text-white hover:bg-forest-deep disabled:opacity-50"
            >
              <CheckCircle2 size={13} />
              Approve
            </button>
          )}
          <div className="flex flex-wrap gap-1.5 sm:justify-end">
            {NEXT_STATUS[row.status].map((s) => (
              <button
                key={s}
                type="button"
                disabled={busy}
                onClick={wrap(() => onStatus(row, s))}
                className="rounded-xl border border-line bg-white px-2.5 py-1 text-xs font-medium text-ink-soft hover:bg-sage disabled:opacity-50"
              >
                {STATUS_LABEL[s]}
              </button>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}

/** Today's outreach queue, snappy: optimistic status/approve, auto-refresh,
 * filter tabs, manual Refresh, and an async "Generate outreach" job. */
export function Outreach() {
  const { data, loading, error, reload } = useApi<OutreachQueue>("/outreach/queue", {
    refetchInterval: 30_000, // surface newly planned rows without a reload
  });
  const invalidate = useInvalidateApi();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("all");
  const [actionError, setActionError] = useState<string | null>(null);

  // optimistic cache patching
  const patchRow = (id: number, patch: Partial<Interaction>) => {
    qc.setQueryData<OutreachQueue>(QUEUE_KEY, (old) => {
      if (!old) return old;
      const apply = (arr: Interaction[]) =>
        arr.map((r) => (r.id === id ? { ...r, ...patch } : r));
      return { ...old, due: apply(old.due), upcoming: apply(old.upcoming) };
    });
  };

  const onStatus = async (row: Interaction, status: InteractionStatus) => {
    setActionError(null);
    patchRow(row.id, { status }); // flip instantly
    try {
      await apiPost(`/outreach/${row.id}/status`, { status });
      invalidate("/outreach"); // reconcile (drops the row if it left the open set)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      reload(); // restore truth
    }
  };

  const onApprove = async (row: Interaction) => {
    setActionError(null);
    patchRow(row.id, {
      approved_at: new Date().toISOString(),
      approved_by: row.rm_id,
    });
    try {
      await apiPost(`/outreach/${row.id}/approve`, { approved_by: row.rm_id });
      invalidate("/outreach");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      reload();
    }
  };

  // generate outreach (async background job)
  const [generating, setGenerating] = useState(false);
  const [genNote, setGenNote] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  const generate = async () => {
    setGenNote(null);
    setActionError(null);
    try {
      await apiPost<GenerateStatus>("/outreach/generate", { quadrant: "act_now" });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
      return;
    }
    setGenerating(true);
    pollRef.current = window.setInterval(async () => {
      try {
        const st = await apiGet<GenerateStatus>("/outreach/generate/status");
        if (!st.running) {
          if (pollRef.current) window.clearInterval(pollRef.current);
          pollRef.current = null;
          setGenerating(false);
          setGenNote(
            st.error
              ? `Planning failed: ${st.error}`
              : `Planned ${st.planned} new interaction(s), awaiting approval.`,
          );
          reload();
        }
      } catch {
        /* transient; keep polling */
      }
    }, 5_000);
  };

  const combined: QueueRow[] = data
    ? [
        ...data.due.map((r) => ({ ...r, isDue: true })),
        ...data.upcoming.map((r) => ({ ...r, isDue: false })),
      ]
    : [];

  const counts = {
    all: combined.length,
    due: combined.filter((r) => r.isDue).length,
    upcoming: combined.filter((r) => !r.isDue).length,
    planned: combined.filter((r) => r.status === "planned").length,
    contacted: combined.filter((r) => r.status === "contacted").length,
  };
  const shown = combined.filter((r) => {
    if (tab === "all") return true;
    if (tab === "due") return r.isDue;
    if (tab === "upcoming") return !r.isDue;
    return r.status === tab;
  });

  const TABS: { key: Tab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "due", label: "Due" },
    { key: "upcoming", label: "Upcoming" },
    { key: "planned", label: "Planned" },
    { key: "contacted", label: "Contacted" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-soft">
          Agent-proposed outreach, the agent plans and drafts; you approve and commit.
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => reload()}
            className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-3 py-2 text-sm font-medium text-ink-soft hover:bg-sage"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
          <button
            type="button"
            disabled={generating}
            onClick={() => void generate()}
            className="inline-flex items-center gap-2 rounded-xl bg-forest px-3.5 py-2 text-sm font-semibold text-white hover:bg-forest-deep disabled:opacity-60"
          >
            {generating ? (
              <Loader size={15} className="animate-spin" />
            ) : (
              <Sparkles size={15} />
            )}
            {generating ? "Planning…" : "Generate outreach"}
          </button>
        </div>
      </div>

      {generating && (
        <div className="rounded-xl border border-line bg-mint/40 p-3 text-sm text-forest-deep">
          Planning act-now outreach in the background (GLM-5.2 can take a few minutes).
          New interactions will appear here as they are drafted.
        </div>
      )}
      {genNote && (
        <div className="rounded-xl border border-line bg-sage p-3 text-sm text-ink-soft">
          {genNote}
        </div>
      )}
      {actionError && <ErrorNote message={actionError} />}
      {error && <ErrorNote message={error} />}
      {loading && <Loading />}

      {data && (
        <>
          <div className="flex flex-wrap gap-1 rounded-xl bg-sage p-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                  tab === t.key
                    ? "bg-white text-forest-deep shadow-sm"
                    : "text-ink-soft hover:text-ink"
                }`}
              >
                {t.label}
                <span className="ml-1.5 text-xs text-ink-muted">{counts[t.key]}</span>
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <Card>
              <p className="py-6 text-center text-sm text-ink-muted">
                {combined.length === 0
                  ? "No open interactions. Press “Generate outreach”, or run the planner: "
                  : "Nothing in this view."}
                {combined.length === 0 && (
                  <code className="font-mono text-xs">
                    python -m aayai.agent.run_planner
                  </code>
                )}
              </p>
            </Card>
          ) : (
            <div className="space-y-3">
              {shown.map((row) => (
                <InteractionCard
                  key={row.id}
                  row={row}
                  onStatus={onStatus}
                  onApprove={onApprove}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
