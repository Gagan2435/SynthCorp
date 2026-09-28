"use client";

import { useEffect, useState } from "react";

export default function UseIt({ runId, tables }: { runId: number; tables: string[] }) {
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  const first = tables[tables.length - 1] ?? "customers";

  return (
    <div className="stack">
      <section>
        <h2>Download</h2>
        <div className="linklist">
          <a className="btn btn-quiet" href={`/api/runs/${runId}/dump.sql`}>
            Everything as one SQL file
          </a>
          {tables.map((t) => (
            <a key={t} className="btn btn-quiet" href={`/api/runs/${runId}/tables/${t}/csv`}>
              {t}.csv
            </a>
          ))}
        </div>
      </section>

      <section>
        <h2>Use it like a real app's API</h2>
        <p className="muted" style={{ maxWidth: "62ch" }}>
          The dataset is also served as a small REST API. Point an agent or a test script at it to practice on realistic records instead of real customer data.
          Filter by any column, for example every ticket of one customer.
        </p>
        <pre className="code">{`# what tables and relationships exist
curl ${origin}/api/mock/${runId}

# list ${first}, 20 at a time
curl "${origin}/api/mock/${runId}/${first}?limit=20&offset=0"

# one record by id
curl ${origin}/api/mock/${runId}/${first}/1

# filter by a column
curl "${origin}/api/mock/${runId}/${first}?customer_id=1"`}</pre>
      </section>
    </div>
  );
}
