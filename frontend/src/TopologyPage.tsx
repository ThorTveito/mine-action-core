import { useCallback, useEffect, useState } from "react";
import { fetchClusters, fetchTopology } from "./api";
import { fmtArea } from "./format";
import { STATUS_COLOR, STATUS_LABEL } from "./status";
import type { HazardStatus, MapFocus, TopologyClusters, TopologyIssue, TopologyReport } from "./types";

const RULE_HELP: Record<string, string> = {
  overlap: "Two hazards cover the same ground (10 m² or more).",
  minor_overlap: "A very small overlap (1–10 m²), usually a vertex that was not snapped.",
  release_conflict: "A released hazard overlaps ground that is still contaminated.",
  gap: "Two hazards end within the tolerance without touching (undershoot).",
  sliver: "A very thin shape, often a leftover strip between two polygons.",
  tiny_area: "Smaller than 25 m²; probably a digitising mistake.",
  tiny_hole: "An interior hole smaller than 25 m².",
  spike: "A vertex with an interior angle below 5°.",
  duplicate_vertices: "Consecutive vertices at the same position.",
};

export default function TopologyPage({ onShow }: { onShow: (focus: Omit<MapFocus, "nonce">) => void }) {
  const [report, setReport] = useState<TopologyReport | null>(null);
  const [clusters, setClusters] = useState<TopologyClusters | null>(null);
  const [tolerance, setTolerance] = useState("2");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async (tol: number) => {
    setBusy(true);
    setError(null);
    try {
      const [r, c] = await Promise.all([fetchTopology({ gapToleranceM: tol }), fetchClusters()]);
      setReport(r);
      setClusters(c);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void run(2);
  }, [run]);

  const show = (i: TopologyIssue) => {
    const [lon, lat] = i.location?.coordinates ?? [];
    onShow({ hazardId: i.hazard_ids[0], lon, lat });
  };

  return (
    <div className="page">
      <h1>Spatial checks</h1>
      <p className="muted">
        Topology rules that must hold between and within hazard polygons (overlaps, gaps, slivers). Errors block release; warnings
        point at digitising problems. Cancelled hazards are ignored. Rules are documented in{" "}
        <code>docs/topology.md</code>.
      </p>

      <section className="card form">
        <label>
          Gap tolerance (m)
          <input type="number" min="0.1" max="50" step="0.5" value={tolerance} onChange={(e) => setTolerance(e.target.value)} />
        </label>
        <div className="actions">
          <button className="primary" disabled={busy} onClick={() => run(Number(tolerance) || 2)}>
            {busy ? "Checking…" : "Run check"}
          </button>
        </div>
      </section>

      {error && <p className="error">{error}</p>}

      {report && (
        <section className="card">
          <div className="chips">
            <span className="chip">{report.checked_hazards} hazards checked</span>
            <span className="chip bad">{report.by_severity.error ?? 0} errors</span>
            <span className="chip warn">{report.by_severity.warning ?? 0} warnings</span>
            {report.by_severity.info ? <span className="chip">{report.by_severity.info} info</span> : null}
          </div>
          {report.issue_count === 0 ? (
            <p className="success">No topology issues found.</p>
          ) : (
            <table className="report">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th className="hide-sm">Rule</th>
                  <th>Issue</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {report.issues.map((i, idx) => (
                  <tr key={idx}>
                    <td>
                      <span className={`badge ${i.severity === "error" ? "rejected" : ""}`}>{i.severity}</span>
                    </td>
                    <td className="hide-sm">
                      <code title={RULE_HELP[i.rule]}>{i.rule}</code>
                    </td>
                    <td>{i.message}</td>
                    <td className="num">
                      <button className="small" onClick={() => show(i)}>
                        Show on map
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {clusters && (
        <section className="card">
          <h3>Contiguous clusters</h3>
          <p className="muted">
            Hazards that share a boundary form one contiguous block, usually planned as one operation.{" "}
            {clusters.clustered_hazards} hazards sit in {clusters.cluster_count} cluster
            {clusters.cluster_count === 1 ? "" : "s"}; {clusters.isolated_hazards} stand alone.
          </p>
          {clusters.clusters.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Hazards</th>
                  <th>Members</th>
                  <th className="num">Total area</th>
                  <th className="num hide-sm">Shared edge</th>
                  <th className="hide-sm">Status mix</th>
                </tr>
              </thead>
              <tbody>
                {clusters.clusters.map((c, idx) => (
                  <tr key={idx}>
                    <td>{c.hazard_count}</td>
                    <td>
                      {c.members.map((m) => (
                        <button key={m.id} className="link" onClick={() => onShow({ hazardId: m.id })}>
                          {m.code}
                        </button>
                      ))}
                    </td>
                    <td className="num">{fmtArea(c.total_area_m2)}</td>
                    <td className="num hide-sm">{Math.round(c.shared_boundary_m)} m</td>
                    <td className="hide-sm">
                      {Object.entries(c.status_counts).map(([s, n]) => (
                        <span key={s} className="legend-chip">
                          <span className="dot" style={{ background: STATUS_COLOR[s as HazardStatus] }} />
                          {n} {STATUS_LABEL[s as HazardStatus].toLowerCase()}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </div>
  );
}
