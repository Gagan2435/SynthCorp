import type { Plan } from "@/lib/api";

const CARD_W = 160;
const CARD_H = 56;
const GAP_X = 70;
const GAP_Y = 22;
const PAD = 12;

/** Lay tables out in columns by generation tier: tier 0 has no parents, tier n depends on tier n-1 or earlier. */
export default function SchemaMap({ plan }: { plan: Plan | null }) {
  if (!plan) return <div className="map-empty">Fix the schema to see how its tables connect.</div>;

  const parents: Record<string, string[]> = {};
  plan.order.forEach((t) => (parents[t] = []));
  plan.edges.forEach((e) => parents[e.from].push(e.to));

  const tier: Record<string, number> = {};
  plan.order.forEach((t) => {
    tier[t] = parents[t].length ? 1 + Math.max(...parents[t].map((p) => tier[p])) : 0;
  });
  const tiers = Math.max(...Object.values(tier)) + 1;
  const columns: string[][] = Array.from({ length: tiers }, () => []);
  plan.order.forEach((t) => columns[tier[t]].push(t));

  const tallest = Math.max(...columns.map((c) => c.length));
  const height = PAD * 2 + 18 + tallest * CARD_H + (tallest - 1) * GAP_Y;
  const width = PAD * 2 + tiers * CARD_W + (tiers - 1) * GAP_X;

  const pos: Record<string, { x: number; y: number }> = {};
  columns.forEach((col, ci) => {
    const colH = col.length * CARD_H + (col.length - 1) * GAP_Y;
    const top = PAD + 18 + (tallest * CARD_H + (tallest - 1) * GAP_Y - colH) / 2;
    col.forEach((t, ri) => (pos[t] = { x: PAD + ci * (CARD_W + GAP_X), y: top + ri * (CARD_H + GAP_Y) }));
  });

  const info = Object.fromEntries(plan.tables.map((t) => [t.name, t]));

  return (
    <svg className="map" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Table dependency map">
      {columns.map((_, ci) => (
        <text key={ci} className="tier-label" x={PAD + ci * (CARD_W + GAP_X)} y={PAD + 8}>
          {ci === 0 ? "generated first" : `then, tier ${ci + 1}`}
        </text>
      ))}
      {plan.edges.map((e, i) => {
        const a = pos[e.to];
        const b = pos[e.from];
        const x1 = a.x + CARD_W;
        const y1 = a.y + CARD_H / 2 + ((i % 3) - 1) * 6;
        const x2 = b.x;
        const y2 = b.y + CARD_H / 2 + ((i % 3) - 1) * 6;
        const mx = (x1 + x2) / 2;
        return (
          <path key={i} className="edge" d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}>
            <title>{`${e.from}.${e.column} → ${e.to}`}</title>
          </path>
        );
      })}
      {plan.order.map((t) => (
        <g key={t} transform={`translate(${pos[t].x},${pos[t].y})`}>
          <rect className={`card ${tier[t] === 0 ? "card-tier0" : ""}`} width={CARD_W} height={CARD_H} rx={4} />
          <text className="name" x={10} y={23}>{t}</text>
          <text className="meta" x={10} y={42}>{`${info[t].rows.toLocaleString()} rows, ${info[t].columns.length} columns`}</text>
        </g>
      ))}
    </svg>
  );
}
