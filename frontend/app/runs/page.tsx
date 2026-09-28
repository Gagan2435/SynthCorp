"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, RunSummary } from "@/lib/api";

export default function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.runs().then(setRuns).catch(() => setError("Could not load runs. Check that the backend is running."));
  }, []);
  useEffect(load, [load]);

  const remove = async (id: number) => {
    if (!confirm(`Delete run ${id} and all its generated tables?`)) return;
    await api.deleteRun(id);
    load();
  };

  return (
    <div>
      <h1>Past runs</h1>
      <p className="lede">Each run keeps its own copy of the data, so you can compare seeds side by side.</p>
      {error && <p className="status-bad">{error}</p>}
      {runs && runs.length === 0 && (
        <p>
          Nothing here yet. <Link href="/">Generate your first dataset.</Link>
        </p>
      )}
      {runs && runs.length > 0 && (
        <div className="panel data-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th>Run</th>
                <th>Schema</th>
                <th>Status</th>
                <th>Rows</th>
                <th>Quality checks</th>
                <th>Seed</th>
                <th>Started</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/runs/${r.id}`}>#{r.id}</Link>
                  </td>
                  <td>{r.name}</td>
                  <td>
                    <span className={`pill pill-${r.status}`}>{r.status}</span>
                  </td>
                  <td className="num">{r.table_counts ? Object.values(r.table_counts).reduce((a, b) => a + b, 0).toLocaleString() : "-"}</td>
                  <td>{r.quality_passed === null ? "-" : `${r.quality_passed} passed, ${r.quality_failed} failed`}</td>
                  <td className="num">{r.seed}</td>
                  <td>{new Date(r.created_at + "Z").toLocaleString()}</td>
                  <td>
                    <button className="btn btn-quiet btn-danger" onClick={() => remove(r.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
