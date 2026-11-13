import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchAdminAreas, fetchDashboard } from "./api";
import { HBar as Bar, StackedBars } from "./charts";
import Choropleth from "./Choropleth";
import { fillMonths, fmtArea, fmtMonth } from "./format";
import { STATUS_COLOR, STATUS_LABEL, STATUS_ORDER } from "./status";
import type { Dashboard, MonthlyClearance } from "./types";
import { CATEGORICAL, OUTCOME_COLOR, RELEASE_COLOR, RELEASE_LABEL, RELEASE_ORDER } from "./viz";

// One neutral series colour for single-series charts. Deliberately not a status colour.
const SERIES = "#0f766e";

const CLASS_LABEL: Record<string, string> = {
  anti_personnel: "Anti-personnel",
  anti_vehicle: "Anti-vehicle",
  mixed: "Mixed",
  cluster_munition: "Cluster munition",
  uxo: "UXO",
};
const FINDING_LABEL: Record<string, string> = {
  item_found: "Item found",
  suspected_area: "Suspected area",
  accident: "Accident",
  other: "Other",
};
const RULE_LABEL: Record<string, string> = {
  overlap: "Overlaps",
  minor_overlap: "Minor overlaps",
  release_conflict: "Release conflicts",
  gap: "Near-miss gaps",
  sliver: "Slivers",
  tiny_area: "Tiny areas",
  tiny_hole: "Tiny holes",
  spike: "Spikes",
  duplicate_vertices: "Duplicate vertices",
};

const fmtInt = (n: number) => n.toLocaleString();

function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function Kpi({ value, label, children }: { value: string; label: string; children?: ReactNode }) {
  return (
    <div className="card kpi">
      <span className="big">{value}</span>
      <span className="muted">{label}</span>
      {children}
    </div>
  );
}

// --------------------------------------------------------------------- monthly bars

type Metric = "area" | "items";

function MonthlyChart({ data: raw }: { data: MonthlyClearance[] }) {
  const data = fillMonths(raw);
  const [metric, setMetric] = useState<Metric>("area");
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  if (data.length === 0) return <p className="muted">No clearance records yet.</p>;

  const value = (d: MonthlyClearance) => (metric === "area" ? d.cleared_area_m2 : d.items_destroyed);
  const W = 640;
  const H = 210;
  const pad = { l: 8, r: 8, t: 12, b: 26 };
  const max = Math.max(1, ...data.map(value));
  const slot = (W - pad.l - pad.r) / data.length;
  const barW = Math.max(3, Math.min(28, slot - 2)); // keeps a 2px gap between bars
  const labelEvery = Math.ceil(data.length / 10);
  const plotH = H - pad.t - pad.b;
  const h = hover !== null ? data[hover] : null;

  return (
    <div>
      <div className="chart-head">
        <div className="segmented small" role="radiogroup" aria-label="Measure">
          <button role="radio" aria-checked={metric === "area"} className={metric === "area" ? "active" : ""} onClick={() => setMetric("area")}>
            Area cleared
          </button>
          <button role="radio" aria-checked={metric === "items"} className={metric === "items" ? "active" : ""} onClick={() => setMetric("items")}>
            Items destroyed
          </button>
        </div>
        <button className="link" onClick={() => setTable(!table)}>
          {table ? "Show chart" : "Show table"}
        </button>
      </div>
      {table ? (
        <table>
          <thead>
            <tr>
              <th>Month</th>
              <th className="num">Area cleared</th>
              <th className="num">Items found</th>
              <th className="num">Items destroyed</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.month}>
                <td>{fmtMonth(d.month)}</td>
                <td className="num">{fmtArea(d.cleared_area_m2)}</td>
                <td className="num">{d.items_found}</td>
                <td className="num">{d.items_destroyed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="chart-wrap" onMouseLeave={() => setHover(null)}>
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={metric === "area" ? "Area cleared per month" : "Items destroyed per month"} className="chart">
            {[0.5, 1].map((f) => (
              <line key={f} x1={pad.l} x2={W - pad.r} y1={pad.t + plotH * (1 - f)} y2={pad.t + plotH * (1 - f)} className="grid-line" />
            ))}
            {data.map((d, i) => {
              const bh = (plotH * value(d)) / max;
              const x = pad.l + i * slot + (slot - barW) / 2;
              const r = Math.min(4, barW / 2, bh);
              const y = H - pad.b - bh;
              return (
                <g key={d.month}>
                  {bh > 0 && (
                    // Rounded data end, square on the baseline.
                    <path
                      d={`M${x},${H - pad.b} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${H - pad.b} Z`}
                      fill={SERIES}
                      opacity={hover === null || hover === i ? 1 : 0.45}
                    />
                  )}
                  {/* Hit target: the whole column, not just the painted bar. */}
                  <rect
                    x={pad.l + i * slot}
                    y={pad.t}
                    width={slot}
                    height={plotH}
                    fill="transparent"
                    tabIndex={0}
                    aria-label={`${fmtMonth(d.month)}: ${fmtArea(d.cleared_area_m2)} cleared, ${d.items_destroyed} items destroyed`}
                    onMouseEnter={() => setHover(i)}
                    onFocus={() => setHover(i)}
                    onBlur={() => setHover(null)}
                  />
                  {i % labelEvery === 0 && (
                    <text x={x + barW / 2} y={H - 8} textAnchor="middle" className="axis">
                      {fmtMonth(d.month)}
                    </text>
                  )}
                </g>
              );
            })}
            <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} className="axis-line" />
            <text x={W - pad.r} y={pad.t - 2} textAnchor="end" className="axis">
              max {metric === "area" ? fmtArea(max) : fmtInt(max)}
            </text>
          </svg>
          {h && hover !== null && (
            <div className="tooltip" style={{ left: `${((pad.l + (hover + 0.5) * slot) / W) * 100}%` }}>
              <strong>{metric === "area" ? fmtArea(h.cleared_area_m2) : `${h.items_destroyed} destroyed`}</strong>
              <span>{fmtMonth(h.month)}</span>
              <span className="muted">
                {metric === "area" ? `${h.items_destroyed} items destroyed` : `${fmtArea(h.cleared_area_m2)} cleared`} · {h.items_found} found
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function HBar({ label, value, max, text }: { label: string; value: number; max: number; text: string }) {
  return (
    <div className="hbar" title={`${label}: ${text}`}>
      <span className="hbar-label">{label}</span>
      <span className="hbar-track">
        <span className="hbar-fill" style={{ width: `${Math.max(1, (100 * value) / max)}%`, background: SERIES }} />
      </span>
      <span className="hbar-value">{text}</span>
    </div>
  );
}

// ------------------------------------------------------------------------------ page

const ACTIVITY_LABEL: Record<string, string> = {
  farming: "Farming",
  herding: "Herding",
  travelling: "Travelling",
  collecting: "Collecting wood, food or scrap",
  playing: "Playing",
  handling: "Handling an item",
  demining: "Demining",
  other: "Other",
  unknown: "Unknown",
};

function Sadd({ grid }: { grid: Record<string, number> }) {
  const sexes = ["female", "male", "unknown"] as const;
  const ages = ["child", "adult", "unknown"] as const;
  const total = (s: string) => ages.reduce((n, a) => n + (grid[`${s}_${a}`] ?? 0), 0);
  return (
    <table className="sadd">
      <thead>
        <tr>
          <th>Sex \ age</th>
          <th className="num">Child (&lt;18)</th>
          <th className="num">Adult</th>
          <th className="num">Age unknown</th>
          <th className="num">Total</th>
        </tr>
      </thead>
      <tbody>
        {sexes.map((s) => (
          <tr key={s}>
            <td>{s === "unknown" ? "Sex unknown" : s[0].toUpperCase() + s.slice(1)}</td>
            {ages.map((a) => (
              <td key={a} className="num">
                {grid[`${s}_${a}`] ?? 0}
              </td>
            ))}
            <td className="num">
              <strong>{total(s)}</strong>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function DashboardPage({
  onOpenChecks,
  onOpenHazard,
}: {
  onOpenChecks?: () => void;
  onOpenHazard?: (hazardId: number) => void;
}) {
  const [region, setRegion] = useState<string>("");
  const [data, setData] = useState<Dashboard | null>(null);
  const [areas, setAreas] = useState<GeoJSON.FeatureCollection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminAreas()
      .then(setAreas)
      .catch(() => setAreas(null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchDashboard(region || undefined)
      .then((d) => !cancelled && setData(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [region]);

  if (error) return <div className="page"><p className="error">Could not load dashboard: {error}</p></div>;
  if (!data) return <div className="page"><p className="muted">Loading…</p></div>;

  const statusTotal = STATUS_ORDER.reduce((sum, s) => sum + data.area_by_status[s], 0);
  const maxRegion = Math.max(1, ...data.by_region.map((r) => r.total_area_m2));
  const maxClass = Math.max(1, ...data.hazards_by_class.map((c) => c.area_m2));
  const maxOrg = Math.max(1, ...data.organisations.map((o) => o.cleared_area_m2));
  const openTasks = data.tasks_by_status.planned + data.tasks_by_status.active + data.tasks_by_status.suspended;
  const cumulative = data.monthly_clearance.reduce((s, m) => s + m.cleared_area_m2, 0);
  const recent = fillMonths(data.monthly_clearance).slice(-6); // last 6 calendar months, gaps count as 0
  const pace = recent.length ? recent.reduce((s, m) => s + m.cleared_area_m2, 0) / recent.length : 0;
  const monthsLeft = pace > 0 ? Math.ceil(data.remaining_area_m2 / pace) : null;
  const scope = data.region ?? "all regions";

  return (
    <div className="page wide">
      <div className="dash-head">
        <div>
          <h1>Progress dashboard</h1>
          <p className="muted">
            Public overview for {scope}. Areas are geodesic; “contaminated” excludes cancelled hazards.
          </p>
        </div>
        <label className="filter">
          Region
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">All regions</option>
            {data.regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="kpis">
        <Kpi value={`${data.release_percent}%`} label="of contaminated land released">
          <div className="progress" role="progressbar" aria-valuenow={data.release_percent} aria-valuemin={0} aria-valuemax={100}>
            <div style={{ width: `${data.release_percent}%`, background: STATUS_COLOR.released }} />
          </div>
        </Kpi>
        <Kpi value={fmtArea(data.outstanding_area_m2)} label={`still to release · ${data.open_hazard_count} open hazards`} />
        <Kpi value={fmtArea(data.land_release.total_m2)} label="land released (all methods)" />
        <Kpi value={fmtInt(data.items_destroyed)} label={`items destroyed (${fmtInt(data.items_found)} found)`} />
        <Kpi value={fmtInt(data.casualties.casualties)} label={`casualties · ${data.casualties.killed} killed, ${data.casualties.injured} injured`} />
        <Kpi value={fmtInt(data.risk_education.total)} label={`people reached by risk education · ${data.risk_education.sessions} sessions`} />
        <Kpi value={fmtInt(openTasks)} label="open tasks" />
        <Kpi
          value={data.qa.pass_rate === null ? "–" : `${data.qa.pass_rate}%`}
          label={`QA pass rate · ${data.qa.inspections} inspections`}
        />
      </div>

      <div className="two-col">
        <section className="card">
          <h3>Land released per year, by method</h3>
          <StackedBars
            rows={data.land_release.by_year}
            x={(r) => String(r.year)}
            series={RELEASE_ORDER.map((m) => ({ key: m, label: RELEASE_LABEL[m], color: RELEASE_COLOR[m] }))}
            value={(r, k) => r[k as "cancelled" | "reduced" | "cleared"]}
            format={fmtArea}
            ariaLabel="Land released per year by method"
          />
          <p className="muted note">
            Land release (IMAS 07.11): survey that finds no evidence <em>cancels</em> land, technical survey{" "}
            <em>reduces</em> it, clearance <em>clears</em> it. Releasing land by survey is far cheaper than clearing it.
          </p>
        </section>
        <section className="card">
          <h3>Land released, all years</h3>
          {RELEASE_ORDER.map((m) => (
            <Bar
              key={m}
              label={m[0].toUpperCase() + m.slice(1)}
              value={data.land_release[`${m}_m2` as "cancelled_m2"]}
              max={Math.max(1, data.land_release.total_m2)}
              text={`${fmtArea(data.land_release[`${m}_m2` as "cancelled_m2"])} · ${
                data.land_release.total_m2 ? Math.round((100 * data.land_release[`${m}_m2` as "cancelled_m2"]) / data.land_release.total_m2) : 0
              }%`}
              color={RELEASE_COLOR[m]}
            />
          ))}
          <p className="muted note">
            Cancelled by non-technical survey, reduced by technical survey, cleared by clearance.{" "}
            {fmtArea(data.outstanding_area_m2)} remains inside open hazards after the land already released from them.
          </p>
        </section>
      </div>

      <div className="two-col even">
        <section className="card">
          <h3>Where contamination remains</h3>
          {areas ? (
            <Choropleth areas={areas} selected={data.region} onSelect={(r) => setRegion(r ?? "")} />
          ) : (
            <p className="muted">Loading map…</p>
          )}
        </section>
        <section className="card">
          <h3>Top priorities{data.region ? ` in ${data.region}` : ""}</h3>
          <p className="muted note">
            Explainable score (0–100) from casualties nearby, recent field reports, threat, evidence and size. Weights
            are illustrative and published at <code>/api/priorities/weights</code>.
          </p>
          <table className="priorities">
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Hazard</th>
                <th>Score</th>
                <th>Main reason</th>
              </tr>
            </thead>
            <tbody>
              {data.top_priorities.map((p) => {
                const top = Object.entries(p.components).sort((a, b) => b[1].points - a[1].points)[0];
                return (
                  <tr key={p.hazard_id}>
                    <td className="num">{p.rank}</td>
                    <td>
                      {onOpenHazard ? (
                        <button className="link" onClick={() => onOpenHazard(p.hazard_id)}>
                          {p.code}
                        </button>
                      ) : (
                        p.code
                      )}
                      <div className="muted">
                        {p.name} · {STATUS_LABEL[p.status]}
                      </div>
                    </td>
                    <td>
                      <Bar label="" value={p.score} max={100} text={p.score.toFixed(0)} color={SERIES} />
                    </td>
                    <td className="muted">{top?.[1].why}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      </div>

      <div className="two-col">
        <section className="card">
          <h3>Casualties per year</h3>
          <StackedBars
            rows={data.casualties.by_year}
            x={(r) => String(r.year)}
            series={[
              { key: "injured", label: "Injured", color: OUTCOME_COLOR.injured },
              { key: "killed", label: "Killed", color: OUTCOME_COLOR.killed },
            ]}
            value={(r, k) => r[k as "killed" | "injured"]}
            format={fmtInt}
            ariaLabel="Casualties per year"
          />
          <p className="muted note">
            {data.casualties.accidents} accidents. {data.casualties.deminers} casualties were deminers, reported separately
            from civilians. Victims are recorded without names: sex, age and outcome only.
          </p>
        </section>
        <section className="card">
          <h3>Who is hurt</h3>
          <Sadd grid={data.casualties.sadd} />
          <h3>What they were doing</h3>
          {Object.entries(data.casualties.by_activity)
            .sort((a, b) => b[1] - a[1])
            .map(([a, n]) => (
              <Bar
                key={a}
                label={ACTIVITY_LABEL[a] ?? a}
                value={n}
                max={Math.max(1, ...Object.values(data.casualties.by_activity))}
                text={String(n)}
                color={SERIES}
              />
            ))}
        </section>
      </div>

      <section className="card">
        <h3>Explosive ordnance risk education</h3>
        <div className="eore">
          {(["girls", "boys", "women", "men"] as const).map((k, i) => (
            <Bar
              key={k}
              label={k[0].toUpperCase() + k.slice(1)}
              value={data.risk_education[k]}
              max={Math.max(1, data.risk_education.girls, data.risk_education.boys, data.risk_education.women, data.risk_education.men)}
              text={fmtInt(data.risk_education[k])}
              color={i < 2 ? CATEGORICAL[0] : CATEGORICAL[1]}
            />
          ))}
        </div>
        <p className="muted note">
          {fmtInt(data.risk_education.total)} people in {data.risk_education.sessions} sessions
          {data.risk_education.by_year.length > 0 &&
            ` (${data.risk_education.by_year.map((y) => `${y.year}: ${fmtInt(y.people)}`).join(", ")})`}
          . Children are shown in blue, adults in orange. Risk education targets the activities in which people are
          hurt.
        </p>
      </section>

      <section className="card">
        <h3>Land by hazard status</h3>
        <div className="stack gapped" role="img" aria-label="Area by hazard status">
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
              <span className="swatch" style={{ background: STATUS_COLOR[s] }} />
              {STATUS_LABEL[s]} <strong>{fmtArea(data.area_by_status[s])}</strong>{" "}
              <span className="muted">({data.hazards_by_status[s]} hazards)</span>
            </span>
          ))}
        </div>
      </section>

      <div className="two-col">
        <section className="card">
          <h3>Clearance per month</h3>
          <MonthlyChart data={data.monthly_clearance} />
          <p className="muted note">
            {fmtArea(cumulative)} cleared in total.
            {monthsLeft !== null &&
              ` At the average pace of the last ${recent.length} months (${fmtArea(pace)}/month), the remaining area would take about ${monthsLeft} months. A rough planning figure, not a forecast.`}
          </p>
        </section>
        <section className="card">
          <h3>Contamination by threat type</h3>
          {data.hazards_by_class.length === 0 && <p className="muted">No open contamination.</p>}
          {data.hazards_by_class.map((c) => (
            <HBar
              key={c.hazard_class}
              label={CLASS_LABEL[c.hazard_class] ?? c.hazard_class}
              value={c.area_m2}
              max={maxClass}
              text={`${fmtArea(c.area_m2)} · ${c.hazard_count}`}
            />
          ))}
          <h3>Tasks</h3>
          <div className="mini-stats">
            {Object.entries(data.tasks_by_type).map(([t, n]) => (
              <span key={t}>
                <strong>{n}</strong> {t}
              </span>
            ))}
          </div>
          <div className="mini-stats">
            {Object.entries(data.tasks_by_status).map(([s, n]) => (
              <span key={s}>
                <strong>{n}</strong> {s}
              </span>
            ))}
          </div>
        </section>
      </div>

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
                <td>
                  {data.region ? (
                    r.region
                  ) : (
                    <button className="link" onClick={() => setRegion(r.region)} title="Filter the dashboard to this region">
                      {r.region}
                    </button>
                  )}
                </td>
                <td className="num">{r.hazard_count}</td>
                <td>
                  <div className="stack small gapped" style={{ width: `${(100 * r.total_area_m2) / maxRegion}%` }}>
                    <div style={{ flex: r.released_area_m2, background: STATUS_COLOR.released }} />
                    <div style={{ flex: r.remaining_area_m2, background: STATUS_COLOR.confirmed }} />
                  </div>
                </td>
                <td className="num">{fmtArea(r.released_area_m2)}</td>
                <td className="num">{fmtArea(r.remaining_area_m2)}</td>
                <td className="num">{fmtArea(r.cleared_area_m2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="legend-row">
          <span>
            <span className="swatch" style={{ background: STATUS_COLOR.released }} /> Released
          </span>
          <span>
            <span className="swatch" style={{ background: STATUS_COLOR.confirmed }} /> Remaining
          </span>
        </div>
      </section>

      <section className="card">
        <h3>Operators</h3>
        {data.organisations.length === 0 ? (
          <p className="muted">No tasks in {scope}.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Organisation</th>
                <th className="num">Tasks</th>
                <th className="num">Open</th>
                <th className="num">Completed</th>
                <th>Area cleared</th>
                <th className="num">Items destroyed</th>
              </tr>
            </thead>
            <tbody>
              {data.organisations.map((o) => (
                <tr key={o.organisation}>
                  <td>{o.organisation}</td>
                  <td className="num">{o.tasks}</td>
                  <td className="num">{o.active_tasks}</td>
                  <td className="num">{o.completed_tasks}</td>
                  <td>
                    <HBar label="" value={o.cleared_area_m2} max={maxOrg} text={fmtArea(o.cleared_area_m2)} />
                  </td>
                  <td className="num">{o.items_destroyed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <div className="three-col">
        <section className="card">
          <h3>Quality assurance</h3>
          <div className="mini-stats big-nums">
            <span>
              <strong>{data.qa.passed}</strong> passed
            </span>
            <span>
              <strong>{data.qa.failed}</strong> failed
            </span>
            <span>
              <strong>{data.qa.residual_items}</strong> residual items
            </span>
          </div>
          <p className="muted note">
            A failed inspection means items were found in ground already cleared; the task must be re-cleared
            before the hazard can be released.
          </p>
        </section>
        <section className="card">
          <h3>Field reports</h3>
          <div className="mini-stats big-nums">
            {Object.entries(data.field_reports.by_status).map(([s, n]) => (
              <span key={s}>
                <strong>{n}</strong> {s === "submitted" ? "awaiting review" : s}
              </span>
            ))}
          </div>
          <div className="mini-stats">
            {Object.entries(data.field_reports.by_finding_type)
              .filter(([, n]) => n > 0)
              .map(([t, n]) => (
                <span key={t}>
                  <strong>{n}</strong> {FINDING_LABEL[t] ?? t}
                </span>
              ))}
          </div>
          <p className="muted note">
            {data.field_reports.median_review_hours === null
              ? "No reports reviewed yet."
              : `Median time to review: ${data.field_reports.median_review_hours} h.`}{" "}
            All regions; counts only.
          </p>
        </section>
        <section className="card">
          <h3>Data quality</h3>
          <div className="mini-stats big-nums">
            <span className={data.data_quality.errors ? "bad-num" : ""}>
              <strong>{data.data_quality.errors}</strong> errors
            </span>
            <span>
              <strong>{data.data_quality.warnings}</strong> warnings
            </span>
          </div>
          <div className="mini-stats">
            {Object.entries(data.data_quality.by_rule).map(([r, n]) => (
              <span key={r}>
                <strong>{n}</strong> {RULE_LABEL[r] ?? r}
              </span>
            ))}
          </div>
          {onOpenChecks && (
            <button className="link" onClick={onOpenChecks}>
              Open spatial checks →
            </button>
          )}
        </section>
      </div>

      <div className="two-col">
        <section className="card">
          <h3>Recent activity</h3>
          {data.recent_activity.length === 0 && <p className="muted">Nothing yet.</p>}
          <ul className="activity">
            {data.recent_activity.map((a, i) => (
              <li key={i}>
                <span>{a.summary}</span>
                <span className="muted">
                  {ago(a.at)} · <span className="badge">{a.source}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h3>Reports and data exports</h3>
          <p className="muted">Public downloads, all regions. CSV opens in Excel; formulas in text cells are neutralised.</p>
          <div className="downloads">
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
      </div>
    </div>
  );
}
