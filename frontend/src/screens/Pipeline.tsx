import {
  CircleAlert,
  CircleCheck,
  ExternalLink,
  Loader,
  MinusCircle,
  Plug,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import type { PipelineState, PipelineTask } from "../lib/apiTypes";
import { useApi } from "../lib/useApi";

const STATE_ICON: Record<string, { icon: LucideIcon; className: string }> = {
  success: { icon: CircleCheck, className: "text-emerald" },
  failed: { icon: CircleAlert, className: "text-negative" },
  upstream_failed: { icon: CircleAlert, className: "text-negative" },
  running: { icon: Loader, className: "animate-spin text-amber" },
  skipped: { icon: MinusCircle, className: "text-ink-muted" },
};

const RUN_TONE: Record<string, BadgeTone> = {
  success: "success",
  running: "warning",
  queued: "neutral",
  failed: "danger",
};

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function TaskRow({ task }: { task: PipelineTask }) {
  const meta = STATE_ICON[task.state ?? ""] ?? {
    icon: MinusCircle,
    className: "text-ink-muted",
  };
  const Icon = meta.icon;
  return (
    <li className="flex items-center gap-3 py-3">
      <Icon size={18} strokeWidth={2} className={`shrink-0 ${meta.className}`} />
      <span className="w-44 shrink-0 font-mono text-sm">{task.task_id}</span>
      <span className="text-xs text-ink-soft">{task.state ?? "no state"}</span>
      <span className="ml-auto font-mono text-xs text-ink-muted">
        {fmtTime(task.start_date)}
        {task.duration !== null && ` · ${task.duration.toFixed(1)}s`}
      </span>
    </li>
  );
}

/** Airflow orchestration state for the aayai_pipeline DAG — read live. */
export function Pipeline() {
  const [creds, setCreds] = useState({ username: "", password: "" });
  const [applied, setApplied] = useState({ username: "", password: "" });
  const path = useMemo(() => {
    const params = new URLSearchParams();
    if (applied.username) params.set("username", applied.username);
    if (applied.password) params.set("password", applied.password);
    const qs = params.toString();
    return `/pipeline/state${qs ? `?${qs}` : ""}`;
  }, [applied]);
  const { data, error, loading, reload } = useApi<PipelineState>(path);

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Pipeline Runs"
        description="Latest aayai_pipeline DAG run, read live from Airflow"
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={reload}
              className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-3.5 py-2 text-sm font-medium text-ink-soft hover:bg-sage"
            >
              <RefreshCw size={14} strokeWidth={1.8} />
              Refresh
            </button>
            {data && (
              <a
                href={data.ui_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-xl bg-forest px-3.5 py-2 text-sm font-semibold text-white hover:bg-forest-deep"
              >
                Open Airflow UI
                <ExternalLink size={14} strokeWidth={1.8} />
              </a>
            )}
          </div>
        }
      />

      {loading && <Loading label="Reading Airflow state…" />}
      {error && <ErrorNote message={error} />}

      {data && !data.available && (
        <Card title="Airflow unavailable — showing no live run">
          <p className="text-sm text-ink-soft">{data.reason}</p>
          <p className="mt-2 text-xs text-ink-muted">
            Airflow runs on the operator's machine (
            <code className="font-mono">docker compose up -d</code>). Enter an
            Airflow id and password to connect, or open the UI directly.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="text-xs text-ink-soft">
              <span className="mb-1 block">Airflow id</span>
              <input
                value={creds.username}
                onChange={(e) => setCreds((c) => ({ ...c, username: e.target.value }))}
                placeholder="admin"
                className="rounded-lg border border-line bg-cream px-3 py-1.5 text-sm outline-none"
              />
            </label>
            <label className="text-xs text-ink-soft">
              <span className="mb-1 block">Password</span>
              <input
                type="password"
                value={creds.password}
                onChange={(e) => setCreds((c) => ({ ...c, password: e.target.value }))}
                placeholder="admin"
                className="rounded-lg border border-line bg-cream px-3 py-1.5 text-sm outline-none"
              />
            </label>
            <button
              type="button"
              onClick={() => setApplied(creds)}
              className="inline-flex items-center gap-2 rounded-xl bg-forest px-3.5 py-2 text-sm font-semibold text-white hover:bg-forest-deep"
            >
              <Plug size={14} strokeWidth={1.8} />
              Connect
            </button>
          </div>
        </Card>
      )}

      {data?.available && !data.run && (
        <Card title="No runs yet">
          <p className="text-sm text-ink-soft">
            The DAG has never run. Trigger it from the Airflow UI or with{" "}
            <code className="font-mono">
              docker compose exec airflow-scheduler airflow dags trigger aayai_pipeline
            </code>
            .
          </p>
        </Card>
      )}

      {data?.available && data.run && (
        <Card
          title="Latest run"
          subtitle={data.run.run_id}
          actions={
            <Badge tone={RUN_TONE[data.run.state] ?? "neutral"}>
              {data.run.state}
            </Badge>
          }
        >
          <p className="mb-2 text-xs text-ink-muted">
            started {fmtTime(data.run.start_date)} · finished{" "}
            {fmtTime(data.run.end_date)}
          </p>
          <ul className="divide-y divide-line/60">
            {data.tasks.map((task) => (
              <TaskRow key={task.task_id} task={task} />
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
