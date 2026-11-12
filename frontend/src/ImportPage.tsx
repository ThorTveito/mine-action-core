import { useRef, useState } from "react";
import { importHazards } from "./api";
import type { ImportOptions, ImportReport, ImportRowReport } from "./types";

const CRS_PRESETS = ["EPSG:4326", "EPSG:32634", "EPSG:3857"];

function csvEscape(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

function reportToCsv(report: ImportReport): string {
  const lines = [["row", "label", "code", "outcome", "action", "issue_type", "issue_code", "message"]];
  for (const r of report.rows) {
    const issues = [
      ...r.errors.map((i) => ({ type: "error", ...i })),
      ...r.warnings.map((i) => ({ type: "warning", ...i })),
    ];
    if (issues.length === 0) {
      lines.push([String(r.row), r.label, r.code ?? "", r.outcome, r.action ?? "", "", "", ""]);
    }
    for (const i of issues) {
      lines.push([String(r.row), r.label, r.code ?? "", r.outcome, r.action ?? "", i.type, i.code, i.message]);
    }
  }
  return lines.map((l) => l.map(csvEscape).join(",")).join("\n");
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function RowLine({ row }: { row: ImportRowReport }) {
  return (
    <tr className={row.outcome}>
      <td className="num">{row.row}</td>
      <td>
        {row.label}
        {row.code && row.code !== row.label && <div className="muted">{row.code}</div>}
      </td>
      <td>
        <span className={`badge ${row.outcome}`}>{row.outcome}</span>
        {row.action && <span className="muted"> {row.action}</span>}
      </td>
      <td>
        {row.errors.map((e, i) => (
          <div key={`e${i}`} className="issue err">
            <code>{e.code}</code> {e.message}
          </div>
        ))}
        {row.warnings.map((w, i) => (
          <div key={`w${i}`} className="issue warn">
            <code>{w.code}</code> {w.message}
          </div>
        ))}
      </td>
    </tr>
  );
}

export default function ImportPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [opts, setOpts] = useState<Omit<ImportOptions, "dryRun">>({
    sourceCrs: "EPSG:4326",
    onError: "skip",
    rejectOverlaps: false,
  });
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [onlyProblems, setOnlyProblems] = useState(false);

  const run = async (dryRun: boolean) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setReport(await importHazards(file, { ...opts, dryRun }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const changeFile = (f: File | null) => {
    setFile(f);
    setReport(null);
    setError(null);
  };

  const rows = report
    ? report.rows.filter((r) => !onlyProblems || r.outcome === "rejected" || r.warnings.length > 0)
    : [];
  const blockedByAbort = report !== null && opts.onError === "abort" && report.rejected > 0;

  return (
    <div className="page">
      <h1>Import hazards</h1>
      <p className="muted">
        Upload a CSV (<code>wkt</code> or <code>geometry</code> column) or GeoJSON file. Always run a
        dry run first: nothing is written until you commit. Rows with a <code>code</code> update that
        hazard; rows without one create a new hazard. Try the files in <code>samples/</code>.
      </p>

      <section className="card form">
        <label>
          File
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.geojson,.json"
            onChange={(e) => changeFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          Source CRS
          <input
            list="crs-presets"
            value={opts.sourceCrs}
            onChange={(e) => setOpts({ ...opts, sourceCrs: e.target.value })}
          />
          <datalist id="crs-presets">
            {CRS_PRESETS.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label>
          If rows are rejected
          <select
            value={opts.onError}
            onChange={(e) => setOpts({ ...opts, onError: e.target.value as "skip" | "abort" })}
          >
            <option value="skip">Import the valid rows, report the rest</option>
            <option value="abort">Import nothing</option>
          </select>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={opts.rejectOverlaps}
            onChange={(e) => setOpts({ ...opts, rejectOverlaps: e.target.checked })}
          />
          Reject rows that overlap other hazards (otherwise only warn)
        </label>
        <div className="actions">
          <button className="primary" disabled={!file || busy} onClick={() => run(true)}>
            {busy ? "Working…" : "Dry run"}
          </button>
        </div>
      </section>

      {error && <p className="error">{error}</p>}

      {report && (
        <section className="card">
          <div className="summary">
            <h2>{report.committed ? "Import committed" : "Dry run result"}</h2>
            <div className="chips">
              <span className="chip">{report.total} rows</span>
              <span className="chip ok">{report.accepted} accepted</span>
              <span className="chip bad">{report.rejected} rejected</span>
              <span className="chip warn">{report.warning_count} warnings</span>
              <span className="chip">
                {report.created} {report.committed ? "created" : "to create"}
              </span>
              <span className="chip">
                {report.updated} {report.committed ? "updated" : "to update"}
              </span>
            </div>
            {report.committed && (
              <p className="success">
                Applied. Audit entries carry source <code>import:{report.import_id.slice(0, 8)}…</code>
              </p>
            )}
            {!report.dry_run && !report.committed && (
              <p className="error">Nothing was imported: “Import nothing” is selected and some rows were rejected.</p>
            )}
          </div>

          <div className="actions">
            {report.dry_run && !report.committed && (
              <button
                className="primary"
                disabled={busy || report.accepted === 0 || blockedByAbort}
                onClick={() => run(false)}
                title={blockedByAbort ? "Fix the rejected rows or switch to “Import the valid rows”" : undefined}
              >
                Commit {report.accepted} accepted row{report.accepted === 1 ? "" : "s"}
              </button>
            )}
            <button onClick={() => download(`import-report-${report.filename || "file"}.csv`, reportToCsv(report))}>
              Download report (CSV)
            </button>
            <label className="check inline">
              <input type="checkbox" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />
              Show only rejected / warnings
            </label>
          </div>

          <table className="report">
            <thead>
              <tr>
                <th className="num">Row</th>
                <th>Record</th>
                <th>Outcome</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <RowLine key={r.row} row={r} />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
