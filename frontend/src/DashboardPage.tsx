import { useEffect, useState } from "react";
import { fetchDashboard } from "./api";
import { fmtArea, fmtMonth } from "./format";
import { STATUS_COLOR, STATUS_LABEL, STATUS_ORDER } from "./status";
import type { Dashboard, MonthlyClearance } from "./types";

function MonthlyChart({ data }: { data: MonthlyClearance[] }) {
  if (data.length === 0) return <p className="muted">No clearance records yet.</p>;
  const W = 640;
  const H = 200;
  const pad = { l: 8, r: 8, t: 8, b: 28 };
  const max = Math.max(...data.map((d) => d.cleared_area_m2));
  const slot = (W - pad.l - pad.r) / data.length;
  const barW = Math.min(28, slot * 0.7);
  const labelEvery = Math.ceil(data.length / 12);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Area cleared per month" className="chart">
      {data.map((d, i) => {
        const h = max > 0 ? ((H - pad.t - pad.b) * d.cleared_area_m2) / max : 0;
        const x = pad.l + i * slot + (slot - barW) / 2;
        return (
          <g key={d.month}>
            <rect x={x} y={H - pad.b - h} width={barW} height={h} rx={2} fill={STATUS_COLOR.in_clearance}>
              <title>{`${fmtMonth(d.month)}: ${fmtArea(d.cleared_area_m2)}, ${d.items_destroyed} items destroyed`}</title>
            </rect>
            {i % labelEvery === 0 && (
              <text x={x + barW / 2} y={H - 10} textAnchor="middle" className="axis">
                {fmtMonth(d.month)}
              </text>
            )}
          </g>
        );
      })}
      <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} className="axis-line" />
    </svg>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboard()
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <div className="page"><p className="error">Could not load dashboard: {error}</p></div>;
  if (!data) return <div className="page"><p className="muted">Loading…</p></div>;

  const statusTotal = STATUS_ORDER.reduce((sum, s) => sum + data.area_by_status[s], 0);
  const maxRegion = Math.max(1, ...data.by_region.map((r) => r.total_area_m2));

  return (
    <div className="page">
      <h1>Progress dashboard</h1>
      <p className="muted">
        Areas are geodesic. “Contaminated” excludes cancelled hazards; “released” counts hazards
        with status released.
      </p>

      <div className="kpis">
        <div className="card kpi">
          <span className="big">{data.release_percent}%</span>
          <span className="muted">of contaminated area released</span>
          <div className="progress" role="progressbar" aria-valuenow={data.release_percent} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${data.release_percent}%`, background: STATUS_COLOR.released }} />
          </div>
        </div>
        <div className="card kpi">
          <span className="big">{fmtArea(data.released_area_m2)}</span>
          <span className="muted">released</span>
        </div>
        <div className="card kpi">
          <span className="big">{fmtArea(data.remaining_area_m2)}</span>
          <span className="muted">remaining</span>
        </div>
        <div className="card kpi">
          <span className="big">{fmtArea(data.cancelled_area_m2)}</span>
          <span className="muted">cancelled by survey</span>
        </div>
      </div>

      <section className="card">
        <h3>Area by hazard status</h3>
        <div className="stack" role="img" aria-label="Area by hazard status">
          {STATUS_ORDER.map((s) =>
            data.area_by_status[s] > 0 ? (
              <div
                key={s}
                style={{ width: `${(100 * data.area_by_status[s]) / statusTotal}%`, background: STATUS_COLOR[s] }}
                title={`${STATUS_LABEL[s]}: ${fmtArea(data.area_by_status[s])}`}
              />
            ) : null,
          )}
        </div>
        <div className="legend-row">
          {STATUS_ORDER.map((s) => (
            <span key={s}>
              <span className="dot" style={{ background: STATUS_COLOR[s] }} />
              {STATUS_LABEL[s]} <span className="muted">{fmtArea(data.area_by_status[s])}</span>
            </span>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>Progress by region</h3>
        <table>
          <thead>
            <tr>
              <th>Region</th>
              <th className="num">Hazards</th>
              <th>Released vs remaining</th>
              <th className="num">Released</th>
              <th className="num">Remaining</th>
              <th className="num">Cleared (records)</th>
            </tr>
          </thead>
          <tbody>
            {data.by_region.map((r) => (
              <tr key={r.region}>
                <td>{r.region}</td>
                <td className="num">{r.hazard_count}</td>
                <td>
                  <div className="stack small" style={{ width: `${(100 * r.total_area_m2) / maxRegion}%` }}>
                    <div style={{ flex: r.released_area_m2, background: STATUS_COLOR.released }} />
                    <div style={{ flex: r.remaining_area_m2, background: STATUS_COLOR.confirmed, opacity: 0.55 }} />
                  </div>
                </td>
                <td className="num">{fmtArea(r.released_area_m2)}</td>
                <td className="num">{fmtArea(r.remaining_area_m2)}</td>
                <td className="num">{fmtArea(r.cleared_area_m2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Reports and data exports</h3>
        <p className="muted">Public downloads (CSV opens in Excel; formulas in text cells are neutralised).</p>
        <div className="actions">
          <a className="button" href="/api/reports/progress.csv" download>
            Progress report by region (CSV)
          </a>
          <a className="button" href="/api/reports/clearance.csv" download>
            Clearance records (CSV)
          </a>
          <a className="button" href="/api/exports/hazards.csv" download>
            All hazards, re-importable (CSV)
          </a>
          <a className="button" href="/api/exports/hazards.geojson" download>
            All hazards (GeoJSON)
          </a>
        </div>
      </section>

      <div className="two-col">
        <section className="card">
          <h3>Area cleared per month</h3>
          <MonthlyChart data={data.monthly_clearance} />
        </section>
        <section className="card">
          <h3>Tasks by status</h3>
          <table>
            <tbody>
              {Object.entries(data.tasks_by_status).map(([status, count]) => (
                <tr key={status}>
                  <td>{status}</td>
                  <td className="num">{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
