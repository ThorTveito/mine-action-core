import { useEffect, useState } from "react";
import { fetchAnnualReport } from "./api";
import { fmtArea } from "./format";
import type { AnnualReport } from "./types";
import { RELEASE_LABEL, RELEASE_ORDER } from "./viz";

const thisYear = new Date().getFullYear();
const YEARS = Array.from({ length: 6 }, (_, i) => thisYear - i);
const n = (v: number) => v.toLocaleString();
const ha = (m2: number) => `${(m2 / 10_000).toLocaleString(undefined, { maximumFractionDigits: 1 })} ha`;

/** A printable annual summary, laid out like a treaty transparency report (e.g. APMBC Article 7). */
export default function ReportPage() {
  const [year, setYear] = useState(thisYear - 1);
  const [report, setReport] = useState<AnnualReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReport(null);
    fetchAnnualReport(year)
      .then(setReport)
      .catch((e: Error) => setError(e.message));
  }, [year]);

  if (error) return <div className="page"><p className="error">{error}</p></div>;

  return (
    <div className="page report-page">
      <div className="report-controls no-print">
        <label className="filter">
          Reporting year
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <button className="primary" onClick={() => window.print()}>
          Print / save as PDF
        </button>
      </div>

      {!report ? (
        <p className="muted">Loading…</p>
      ) : (
        <article className="report">
          <header>
            <p className="muted">Mine action annual report · synthetic demonstration data</p>
            <h1>
              {report.country.split(" (")[0]}: calendar year {report.year}
            </h1>
            <p className="muted">Generated {new Date(report.generated_at).toLocaleString()}</p>
          </header>

          <section>
            <h2>Summary</h2>
            <p>
              In {report.year}, {ha(report.land_release.total_m2)} of land was released:{" "}
              {RELEASE_ORDER.map((m) => `${ha(report.land_release[`${m}_m2` as "cancelled_m2"])} ${m}`).join(", ")}.{" "}
              {n(report.land_release.items_destroyed)} explosive items were destroyed. {n(report.casualties.casualties)}{" "}
              casualties were recorded in {n(report.casualties.accidents)} accidents ({n(report.casualties.killed)} killed,{" "}
              {n(report.casualties.injured)} injured). {n(report.risk_education.total)} people took part in{" "}
              {n(report.risk_education.sessions)} risk education sessions. At the time of reporting,{" "}
              {n(report.open_hazards)} hazardous areas covering {ha(report.outstanding_m2)} remain to be addressed.
            </p>
          </section>

          <section>
            <h2>1. Remaining contamination and land released, by area</h2>
            <table>
              <thead>
                <tr>
                  <th>Administrative area</th>
                  <th className="num">Open hazards</th>
                  <th className="num">Remaining</th>
                  {RELEASE_ORDER.map((m) => (
                    <th key={m} className="num">
                      {m[0].toUpperCase() + m.slice(1)} in {report.year}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.regions.map((r) => (
                  <tr key={r.region}>
                    <td>{r.region}</td>
                    <td className="num">{r.open_hazards}</td>
                    <td className="num">{fmtArea(r.outstanding_m2)}</td>
                    <td className="num">{fmtArea(r.cancelled_m2)}</td>
                    <td className="num">{fmtArea(r.reduced_m2)}</td>
                    <td className="num">{fmtArea(r.cleared_m2)}</td>
                  </tr>
                ))}
                <tr className="total">
                  <td>Total</td>
                  <td className="num">{report.open_hazards}</td>
                  <td className="num">{fmtArea(report.outstanding_m2)}</td>
                  <td className="num">{fmtArea(report.land_release.cancelled_m2)}</td>
                  <td className="num">{fmtArea(report.land_release.reduced_m2)}</td>
                  <td className="num">{fmtArea(report.land_release.cleared_m2)}</td>
                </tr>
              </tbody>
            </table>
            <p className="muted note">
              {RELEASE_ORDER.map((m) => RELEASE_LABEL[m]).join("; ")}. Remaining area is the area of open hazards minus land
              already released inside them, as of the report date.
            </p>
          </section>

          <section>
            <h2>2. Explosive ordnance</h2>
            <p>
              {n(report.land_release.items_found)} items found and {n(report.land_release.items_destroyed)} destroyed
              during land release in {report.year}.
            </p>
          </section>

          <section>
            <h2>3. Casualties</h2>
            <table>
              <thead>
                <tr>
                  <th />
                  <th className="num">Girls / boys (&lt;18)</th>
                  <th className="num">Women / men</th>
                  <th className="num">Age unknown</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {(["female", "male", "unknown"] as const).map((s) => {
                  const g = report.casualties.sadd;
                  const row = [g[`${s}_child`] ?? 0, g[`${s}_adult`] ?? 0, g[`${s}_unknown`] ?? 0];
                  return (
                    <tr key={s}>
                      <td>{s === "unknown" ? "Sex unknown" : s === "female" ? "Female" : "Male"}</td>
                      {row.map((v, i) => (
                        <td key={i} className="num">
                          {v}
                        </td>
                      ))}
                      <td className="num">{row.reduce((a, b) => a + b, 0)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="muted note">
              {report.casualties.killed} killed, {report.casualties.injured} injured; {report.casualties.deminers} deminer
              casualties included. No personal identifiers are held.
            </p>
          </section>

          <section>
            <h2>4. Explosive ordnance risk education</h2>
            <table>
              <thead>
                <tr>
                  <th className="num">Sessions</th>
                  <th className="num">Girls</th>
                  <th className="num">Boys</th>
                  <th className="num">Women</th>
                  <th className="num">Men</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="num">{report.risk_education.sessions}</td>
                  <td className="num">{n(report.risk_education.girls)}</td>
                  <td className="num">{n(report.risk_education.boys)}</td>
                  <td className="num">{n(report.risk_education.women)}</td>
                  <td className="num">{n(report.risk_education.men)}</td>
                  <td className="num">{n(report.risk_education.total)}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section>
            <h2>5. Quality management</h2>
            <p>
              {report.qa.inspections} QA/QC inspections: {report.qa.passed} passed, {report.qa.failed} failed
              {report.qa.pass_rate !== null && ` (pass rate ${report.qa.pass_rate}%)`}; {report.qa.residual_items} residual
              items found in sampled ground.
            </p>
          </section>

          <footer className="muted note">
            Format inspired by transparency reporting under the Anti-Personnel Mine Ban Convention (Article 7). Karvonia
            and all figures are fictional. Not affiliated with GICHD or IMSMA.
          </footer>
        </article>
      )}
    </div>
  );
}
