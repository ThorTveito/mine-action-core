import { useState } from "react";
import type { ReactNode } from "react";

export interface Series {
  key: string;
  label: string;
  color: string;
}

interface StackedProps<T> {
  rows: T[];
  x: (row: T) => string;
  series: Series[];
  value: (row: T, key: string) => number;
  format: (v: number) => string;
  ariaLabel: string;
}

/** Vertical stacked bars with a legend, per-column hover tooltip and a table view. One y-axis. */
export function StackedBars<T>({ rows, x, series, value, format, ariaLabel }: StackedProps<T>) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  if (rows.length === 0) return <p className="muted">No data yet.</p>;
  const W = 560;
  const H = 200;
  const pad = { l: 8, r: 8, t: 14, b: 24 };
  const plotH = H - pad.t - pad.b;
  const totals = rows.map((r) => series.reduce((s, ser) => s + value(r, ser.key), 0));
  const max = Math.max(1, ...totals);
  const slot = (W - pad.l - pad.r) / rows.length;
  const barW = Math.max(4, Math.min(44, slot - 6));
  const h = hover !== null ? rows[hover] : null;

  return (
    <div>
      <div className="chart-head">
        <div className="legend-row compact">
          {series.map((s) => (
            <span key={s.key}>
              <span className="swatch" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
        <button className="link" onClick={() => setTable(!table)}>
          {table ? "Show chart" : "Show table"}
        </button>
      </div>
      {table ? (
        <table>
          <thead>
            <tr>
              <th />
              {series.map((s) => (
                <th key={s.key} className="num">
                  {s.label}
                </th>
              ))}
              <th className="num">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={x(r)}>
                <td>{x(r)}</td>
                {series.map((s) => (
                  <td key={s.key} className="num">
                    {format(value(r, s.key))}
                  </td>
                ))}
                <td className="num">{format(totals[i])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="chart-wrap" onMouseLeave={() => setHover(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel} className="chart">
            <line x1={pad.l} x2={W - pad.r} y1={pad.t} y2={pad.t} className="grid-line" />
            {rows.map((r, i) => {
              const x0 = pad.l + i * slot + (slot - barW) / 2;
              let y = H - pad.b;
              const parts = series
                .map((s) => ({ s, v: value(r, s.key) }))
                .filter((p) => p.v > 0)
                .map((p, j, arr) => {
                  const bh = (plotH * p.v) / max;
                  const gap = j < arr.length - 1 ? 2 : 0; // 2px surface gap between segments
                  y -= bh;
                  const top = j === arr.length - 1;
                  const r4 = top ? Math.min(4, barW / 2, bh) : 0;
                  const d = `M${x0},${y + bh - gap} V${y + r4} Q${x0},${y} ${x0 + r4},${y} H${x0 + barW - r4} Q${x0 + barW},${y} ${x0 + barW},${y + r4} V${y + bh - gap} Z`;
                  return <path key={p.s.key} d={d} fill={p.s.color} opacity={hover === null || hover === i ? 1 : 0.45} />;
                });
              return (
                <g key={x(r)}>
                  {parts}
                  <rect
                    x={pad.l + i * slot}
                    y={pad.t}
                    width={slot}
                    height={plotH}
                    fill="transparent"
                    tabIndex={0}
                    aria-label={`${x(r)}: ${series.map((s) => `${s.label} ${format(value(r, s.key))}`).join(", ")}`}
                    onMouseEnter={() => setHover(i)}
                    onFocus={() => setHover(i)}
                    onBlur={() => setHover(null)}
                  />
                  <text x={x0 + barW / 2} y={H - 7} textAnchor="middle" className="axis">
                    {x(r)}
                  </text>
                </g>
              );
            })}
            <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} className="axis-line" />
            <text x={W - pad.r} y={pad.t - 3} textAnchor="end" className="axis">
              max {format(max)}
            </text>
          </svg>
          {h && hover !== null && (
            <div className="tooltip" style={{ left: `${((pad.l + (hover + 0.5) * slot) / W) * 100}%` }}>
              <strong>{format(totals[hover])}</strong>
              <span>{x(h)}</span>
              {series.map((s) => (
                <span key={s.key} className="tip-row">
                  <span className="tip-key" style={{ background: s.color }} />
                  {format(value(h, s.key))} {s.label.toLowerCase()}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function HBar({
  label,
  value,
  max,
  text,
  color,
}: {
  label: ReactNode;
  value: number;
  max: number;
  text: string;
  color: string;
}) {
  return (
    <div className="hbar">
      <span className="hbar-label">{label}</span>
      <span className="hbar-track">
        <span className="hbar-fill" style={{ width: `${Math.max(value > 0 ? 1 : 0, (100 * value) / max)}%`, background: color }} />
      </span>
      <span className="hbar-value">{text}</span>
    </div>
  );
}
