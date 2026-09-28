"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import DataPreview from "@/components/DataPreview";
import QualityReport from "@/components/QualityReport";
import SchemaMap from "@/components/SchemaMap";
import UseIt from "@/components/UseIt";
import { api, RunDetail } from "@/lib/api";

type Tab = "data" | "quality" | "use";

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("data");

  // Poll while the run is still working.
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await api.run(id);
        if (stop) return;
        setRun(r);
        if (r.status === "pending" || r.status === "running") timer = setTimeout(tick, 1000);
      } catch {
        if (!stop) setError("This run does not exist, or the backend is not reachable.");
      }
    };
    tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [id]);

  if (error)
    return (
      <div>
        <p className="status-bad">{error}</p>
        <Link href="/runs">Back to past runs</Link>
      </div>
    );
  if (!run) return <p className="muted">Loading…</p>;

  const working = run.status === "pending" || run.status === "running";
  const done = run.progress?.done_tables.length ?? 0;
  const total = run.progress?.total_tables ?? 1;
  const tables = (run.plan?.tables ?? []).map((t) => ({ name: t.name, rows: run.table_counts?.[t.name] ?? t.rows }));

  return (
    <div>
      <h1>
        {run.name} <span className={`pill pill-${run.status}`}>{run.status}</span>
      </h1>
      <p className="lede" style={{ marginBottom: 0 }}>
        Run #{run.id}, seed {run.seed}. Same seed and schema always give the same data.
      </p>

      {working && (
        <div className="panel panel-body" style={{ marginTop: 20 }} aria-live="polite">
          <strong>{run.progress?.stage === "loading" ? "Saving to the database" : run.progress?.stage === "checking" ? "Running quality checks" : "Generating tables"}</strong>
          <div className="progress">
            <div style={{ width: `${Math.round((done / total) * 100)}%` }} />
          </div>
          <span className="muted">
            {done} of {total} tables generated
          </span>
        </div>
      )}

      {run.status === "failed" && (
        <div className="panel panel-body" style={{ marginTop: 20 }}>
          <p className="status-bad" style={{ marginTop: 0 }}>
            The run failed: {run.error}
          </p>
          <button className="btn btn-quiet" onClick={() => router.push("/")}>
            Back to the editor
          </button>
        </div>
      )}

      {run.status === "done" && (
        <>
          <div className="tabs" role="tablist">
            {([
              ["data", "Data"],
              ["quality", `Quality (${run.quality_failed === 0 ? "all passed" : `${run.quality_failed} failed`})`],
              ["use", "Download and use"],
            ] as [Tab, string][]).map(([key, label]) => (
              <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
                {label}
              </button>
            ))}
          </div>
          {tab === "data" && (
            <div className="stack">
              <div className="panel panel-body" style={{ maxWidth: 760 }}>
                <SchemaMap plan={run.plan} />
              </div>
              <DataPreview runId={run.id} tables={tables} />
            </div>
          )}
          {tab === "quality" && <QualityReport runId={run.id} />}
          {tab === "use" && <UseIt runId={run.id} tables={tables.map((t) => t.name)} />}
        </>
      )}
    </div>
  );
}
