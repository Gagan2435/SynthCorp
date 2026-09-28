"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, Check, Quality } from "@/lib/api";

export default function QualityReport({ runId }: { runId: number }) {
  const [q, setQ] = useState<Quality | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.quality(runId).then(setQ).catch((e) => setError(e.message));
  }, [runId]);

  if (error) return <p className="status-bad">{error}</p>;
  if (!q) return <p className="muted">Loading the report…</p>;

  const byTable = new Map<string, Check[]>();
  q.checks.forEach((c) => byTable.set(c.table, [...(byTable.get(c.table) ?? []), c]));
  const chart = [...byTable.entries()].map(([table, checks]) => ({
    table,
    passed: checks.filter((c) => c.status === "pass").length,
    failed: checks.filter((c) => c.status === "fail").length,
  }));

  return (
    <div className="stack">
      <div>
        <p className="scoreline">
          {q.failed === 0 ? `All ${q.total} checks passed` : `${q.failed} of ${q.total} checks failed`}
        </p>
        <p className="muted" style={{ margin: 0 }}>
          The checks run as SQL against the stored tables, so they verify what is actually in the database.
        </p>
      </div>

      {q.injected_defects.length > 0 && (
        <div className="banner">
          You asked for damaged rows. Injected: {q.injected_defects.map((d) => `${d.rows} rows in ${d.table}.${d.column} (${d.defect})`).join("; ")}. The failures below are the checks
          catching them.
        </div>
      )}

      <div className="panel panel-body" style={{ height: 40 + chart.length * 36 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chart} layout="vertical" margin={{ left: 20, right: 10 }}>
            <CartesianGrid horizontal={false} stroke="#c5cec9" />
            <XAxis type="number" allowDecimals={false} />
            <YAxis type="category" dataKey="table" width={110} interval={0} />
            <Tooltip />
            <Legend />
            <Bar dataKey="passed" stackId="a" name="Passed" fill="#0e6e63" />
            <Bar dataKey="failed" stackId="a" name="Failed" fill="#b3352a" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {[...byTable.entries()].map(([table, checks]) => (
        <div className="panel" key={table}>
          <div className="group-title">{table}</div>
          <ul className="checks">
            {[...checks].sort((a, b) => Number(b.status === "fail") - Number(a.status === "fail")).map((c, i) => (
              <li key={i} className={`check ${c.status}`}>
                <span className="check-mark" aria-label={c.status}>
                  {c.status === "pass" ? "✓" : "✕"}
                </span>
                <span>
                  {c.description}
                  {c.status === "fail" && c.samples.length > 0 && <small>Examples: {c.samples.join(", ")}</small>}
                </span>
                <span className="muted">{c.status === "fail" ? `${c.failed} bad` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
