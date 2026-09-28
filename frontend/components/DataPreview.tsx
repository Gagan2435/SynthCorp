"use client";

import { useEffect, useState } from "react";
import { api, Preview } from "@/lib/api";

const PAGE = 25;

function Cell({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <td className="null">empty</td>;
  if (typeof value === "number") return <td className="num">{value.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>;
  if (typeof value === "boolean") return <td>{value ? "yes" : "no"}</td>;
  return <td title={String(value)}>{String(value)}</td>;
}

export default function DataPreview({ runId, tables }: { runId: number; tables: { name: string; rows: number }[] }) {
  const [table, setTable] = useState(tables[0]?.name ?? "");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.preview(runId, table, offset, PAGE).then(setData).catch((e) => setError(e.message));
  }, [runId, table, offset]);

  return (
    <div className="split">
      <div className="tablist" role="tablist" aria-label="Tables">
        {tables.map((t) => (
          <button
            key={t.name}
            role="tab"
            aria-selected={t.name === table}
            onClick={() => {
              setTable(t.name);
              setOffset(0);
            }}
          >
            {t.name}
            <small>{t.rows.toLocaleString()}</small>
          </button>
        ))}
      </div>
      <div className="panel">
        {error && <p className="status-bad panel-body">{error}</p>}
        {data && (
          <>
            <div className="data-wrap">
              <table className="grid">
                <thead>
                  <tr>
                    {data.columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i}>
                      {data.columns.map((c) => (
                        <Cell key={c} value={r[c]} />
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <button className="btn btn-quiet" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Previous
              </button>
              <span>
                Rows {data.total === 0 ? 0 : offset + 1} to {Math.min(offset + PAGE, data.total)} of {data.total.toLocaleString()}
              </span>
              <button className="btn btn-quiet" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
