import { useCallback, useEffect, useState } from "react";
import { acceptReport, ApiError, createFieldReport, fetchFieldReports, fetchNearby, rejectReport } from "./api";
import { useAuth } from "./AuthContext";
import { discard, enqueue, flushOutbox, isRetryable, loadOutbox, newClientId } from "./outbox";
import type { QueuedReport } from "./outbox";
import { STATUS_COLOR, STATUS_LABEL } from "./status";
import type {
  FieldReport,
  FieldReportInput,
  FindingType,
  ItemCategory,
  MapFocus,
  NearbyHazard,
  ReportSource,
  ReportStatus,
} from "./types";

const FINDING_LABEL: Record<FindingType, string> = {
  item_found: "Item found",
  suspected_area: "Suspected area",
  accident: "Accident",
  other: "Other",
};
const ITEM_LABEL: Record<ItemCategory, string> = {
  ap_mine: "Anti-personnel mine",
  av_mine: "Anti-vehicle mine",
  uxo: "Unexploded ordnance (UXO)",
  submunition: "Cluster submunition",
  ied: "Improvised device (IED)",
  unknown: "Unknown / not sure",
};
const SOURCE_LABEL: Record<ReportSource, string> = {
  direct_observation: "I saw it myself",
  local_informant: "Local informant",
  authority: "Police / authorities",
};

const localNow = () => {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16); // value for <input type="datetime-local">
};

// ------------------------------------------------------------------------- the form

function ReportForm({ onQueued, onSent }: { onQueued: () => void; onSent: () => void }) {
  const [finding, setFinding] = useState<FindingType>("item_found");
  const [item, setItem] = useState<ItemCategory | "">("");
  const [quantity, setQuantity] = useState("1");
  const [source, setSource] = useState<ReportSource>("direct_observation");
  const [description, setDescription] = useState("");
  const [observed, setObserved] = useState(localNow());
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const [gpsState, setGpsState] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const locate = () => {
    if (!("geolocation" in navigator)) {
      setGpsState("This device has no location service. Enter coordinates by hand.");
      return;
    }
    setGpsState("Getting position…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLat(pos.coords.latitude.toFixed(6));
        setLon(pos.coords.longitude.toFixed(6));
        setAccuracy(Math.round(pos.coords.accuracy));
        setGpsState(null);
      },
      (err) => setGpsState(`Could not get a position (${err.message}). Enter it by hand.`),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
    );
  };

  const reset = () => {
    setItem("");
    setQuantity("1");
    setDescription("");
    setObserved(localNow());
    setAccuracy(null);
  };

  const submit = async () => {
    setError(null);
    setDone(null);
    const latN = Number(lat);
    const lonN = Number(lon);
    if (!lat || !lon || Number.isNaN(latN) || Number.isNaN(lonN)) {
      setError("A location is required: use GPS or type latitude and longitude.");
      return;
    }
    const payload: FieldReportInput = {
      client_id: newClientId(),
      observed_at: new Date(observed).toISOString(),
      finding_type: finding,
      item_category: item || null,
      quantity: finding === "item_found" || item ? Number(quantity) || null : null,
      source,
      description: description.trim(),
      lat: latN,
      lon: lonN,
      gps_accuracy_m: accuracy,
    };
    setBusy(true);
    try {
      if (!navigator.onLine) throw new TypeError("offline");
      const saved = await createFieldReport(payload);
      setDone(`Sent as ${saved.code}. Thank you.`);
      reset();
      onSent();
    } catch (e) {
      if (isRetryable(e)) {
        if (enqueue(payload, "Waiting for connection")) {
          setDone("No connection: saved on this device and will be sent automatically.");
          reset();
          onQueued();
        } else {
          setError("No connection, and this browser cannot store the report. Try again later.");
        }
      } else {
        setError((e as Error).message); // the server refused it: fix and resend
      }
    } finally {
      setBusy(false);
    }
  };

  const needsItem = finding === "item_found";

  return (
    <section className="card field-form">
      <h2>Register a finding</h2>
      <p className="safety">⚠ Do not touch or move anything. Mark the spot from a safe distance, then report.</p>

      <div className="segmented" role="radiogroup" aria-label="What did you find?">
        {(Object.keys(FINDING_LABEL) as FindingType[]).map((f) => (
          <button
            key={f}
            type="button"
            role="radio"
            aria-checked={finding === f}
            className={finding === f ? "active" : ""}
            onClick={() => setFinding(f)}
          >
            {FINDING_LABEL[f]}
          </button>
        ))}
      </div>

      <label>
        Item {needsItem ? "(required)" : "(if known)"}
        <select value={item} onChange={(e) => setItem(e.target.value as ItemCategory | "")}>
          <option value="">Choose…</option>
          {(Object.keys(ITEM_LABEL) as ItemCategory[]).map((c) => (
            <option key={c} value={c}>
              {ITEM_LABEL[c]}
            </option>
          ))}
        </select>
      </label>
      {(needsItem || item) && (
        <label>
          How many
          <input type="number" min="1" inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        </label>
      )}

      <fieldset className="location">
        <legend>Location</legend>
        <button type="button" className="primary big" onClick={locate}>
          📍 Use my GPS position
        </button>
        {gpsState && <p className="muted">{gpsState}</p>}
        <div className="two">
          <label>
            Latitude
            <input inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="61.512345" />
          </label>
          <label>
            Longitude
            <input inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="8.312345" />
          </label>
        </div>
        {accuracy !== null && (
          <p className={accuracy > 30 ? "warn-text" : "muted"}>
            GPS accuracy ±{accuracy} m{accuracy > 30 ? " (poor: wait for a better fix if it is safe)" : ""}
          </p>
        )}
      </fieldset>

      <label>
        Source
        <select value={source} onChange={(e) => setSource(e.target.value as ReportSource)}>
          {(Object.keys(SOURCE_LABEL) as ReportSource[]).map((s) => (
            <option key={s} value={s}>
              {SOURCE_LABEL[s]}
            </option>
          ))}
        </select>
      </label>
      <label>
        When
        <input type="datetime-local" value={observed} onChange={(e) => setObserved(e.target.value)} />
      </label>
      <label>
        What you saw
        <textarea
          rows={3}
          maxLength={2000}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Size, condition, markings, landmarks, who else knows…"
        />
      </label>

      {error && <p className="error">{error}</p>}
      {done && <p className="success">{done}</p>}
      <button className="primary big" disabled={busy || (needsItem && !item)} onClick={submit}>
        {busy ? "Sending…" : "Send report"}
      </button>
    </section>
  );
}

// ----------------------------------------------------------------- outbox and history

function Outbox({ items, onChange }: { items: QueuedReport[]; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  if (items.length === 0) return null;
  const sendNow = async () => {
    setBusy(true);
    const r = await flushOutbox();
    setNote(
      r.needsLogin
        ? "Log in again to send the rest."
        : r.sent
          ? `Sent ${r.sent}.`
          : "Still no connection.",
    );
    setBusy(false);
    onChange();
  };
  return (
    <section className="card outbox">
      <h3>Waiting to send ({items.length})</h3>
      {items.map((q) => (
        <div key={q.payload.client_id} className="report-row">
          <div>
            <strong>{FINDING_LABEL[q.payload.finding_type]}</strong>
            {q.payload.item_category && ` · ${ITEM_LABEL[q.payload.item_category]}`}
            <div className="muted">
              Saved {new Date(q.queuedAt).toLocaleString()} · {q.payload.lat.toFixed(5)}, {q.payload.lon.toFixed(5)}
            </div>
            {q.lastError && <div className={q.needsAttention ? "error" : "muted"}>{q.lastError}</div>}
          </div>
          {q.needsAttention && (
            <button
              className="small"
              onClick={() => {
                discard(q.payload.client_id);
                onChange();
              }}
            >
              Discard
            </button>
          )}
        </div>
      ))}
      <div className="actions">
        <button className="primary small" disabled={busy} onClick={sendNow}>
          {busy ? "Sending…" : "Send now"}
        </button>
        {note && <span className="muted">{note}</span>}
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: ReportStatus }) {
  const cls = status === "accepted" ? "accepted" : status === "rejected" ? "rejected" : "pending";
  return <span className={`badge ${cls}`}>{status}</span>;
}

// --------------------------------------------------------------------------- triage

function Triage({ report, onDone, onShow }: { report: FieldReport; onDone: () => void; onShow: (f: Omit<MapFocus, "nonce">) => void }) {
  const { can } = useAuth();
  const [nearby, setNearby] = useState<NearbyHazard[] | null>(null);
  const [radius, setRadius] = useState("50");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchNearby(report.id)
      .then(setNearby)
      .catch(() => setNearby([]));
  }, [report.id]);

  const act = async (fn: () => Promise<{ warnings: string[] }>) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fn();
      setWarnings(res.warnings);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const inReleased = nearby?.find((h) => h.contains_point && h.status === "released");
  const open = report.status === "submitted" && can("write");

  return (
    <div className="triage">
      <h4>Hazards within 500 m</h4>
      {nearby === null && <p className="muted">Looking…</p>}
      {nearby?.length === 0 && <p className="muted">None. This may be a new area.</p>}
      {inReleased && (
        <p className="error">
          Inside released hazard {inReleased.code}. A finding in released land points to residual
          contamination and needs investigation.
        </p>
      )}
      {nearby?.map((h) => (
        <div key={h.id} className="report-row">
          <div>
            <span className="dot" style={{ background: STATUS_COLOR[h.status] }} />
            <strong>{h.code}</strong> {h.name}
            <div className="muted">
              {STATUS_LABEL[h.status]} · {h.contains_point ? "point is inside" : `${Math.round(h.distance_m)} m away`}
            </div>
          </div>
          <div className="row-actions">
            <button className="small" onClick={() => onShow({ hazardId: h.id })}>
              Map
            </button>
            {open && (
              <button className="small" disabled={busy} onClick={() => act(() => acceptReport(report.id, { mode: "link", hazard_id: h.id }))}>
                Link
              </button>
            )}
          </div>
        </div>
      ))}
      {open && (
        <div className="decide">
          <div className="inline">
            <label>
              New suspected area, radius (m)
              <input type="number" min="5" max="2000" value={radius} onChange={(e) => setRadius(e.target.value)} />
            </label>
            <button
              className="primary small"
              disabled={busy}
              onClick={() => act(() => acceptReport(report.id, { mode: "new_hazard", radius_m: Number(radius) || 50 }))}
            >
              Create SHA
            </button>
          </div>
          <div className="inline">
            <label>
              Reject, reason
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Duplicate of…" />
            </label>
            <button className="small" disabled={busy || reason.trim().length < 3} onClick={() => act(() => rejectReport(report.id, reason.trim()))}>
              Reject
            </button>
          </div>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {warnings.map((w, i) => (
        <p key={i} className="warn-text">
          ⚠ {w}
        </p>
      ))}
    </div>
  );
}

function ReportCard({
  report,
  staff,
  onChanged,
  onShow,
}: {
  report: FieldReport;
  staff: boolean;
  onChanged: () => void;
  onShow: (f: Omit<MapFocus, "nonce">) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card report-card">
      <div className="report-row">
        <div>
          <strong>{report.code}</strong> · {FINDING_LABEL[report.finding_type]}
          {report.item_category && ` · ${ITEM_LABEL[report.item_category]}`}
          {report.quantity ? ` × ${report.quantity}` : ""}
          <div className="muted">
            {new Date(report.observed_at).toLocaleString()} · by {report.reported_by}
            {report.gps_accuracy_m !== null && ` · ±${Math.round(report.gps_accuracy_m)} m`}
          </div>
        </div>
        <StatusBadge status={report.status} />
      </div>
      {report.description && <p className="desc">{report.description}</p>}
      {report.status !== "submitted" && (
        <p className="muted">
          {report.status === "accepted" ? `Accepted${report.hazard_code ? ` as ${report.hazard_code}` : ""}` : "Rejected"} by{" "}
          {report.reviewed_by}
          {report.review_note ? `: ${report.review_note}` : ""}
        </p>
      )}
      <div className="actions">
        <button className="small" onClick={() => onShow({ hazardId: report.hazard_id ?? undefined, lon: report.lon, lat: report.lat })}>
          Show on map
        </button>
        {staff && (
          <button className="small" onClick={() => setOpen(!open)}>
            {open ? "Hide review" : report.status === "submitted" ? "Review" : "Details"}
          </button>
        )}
      </div>
      {open && <Triage report={report} onDone={onChanged} onShow={onShow} />}
    </div>
  );
}

// ----------------------------------------------------------------------------- page

export default function FieldPage({ onShow }: { onShow: (f: Omit<MapFocus, "nonce">) => void }) {
  const { user, can } = useAuth();
  const staff = can("view_reports");
  const [reports, setReports] = useState<FieldReport[] | null>(null);
  const [filter, setFilter] = useState<ReportStatus | "">(staff ? "submitted" : "");
  const [outbox, setOutbox] = useState<QueuedReport[]>(loadOutbox());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setOutbox(loadOutbox());
    if (!user) return;
    fetchFieldReports(filter || undefined)
      .then(setReports)
      .catch((e: Error) => setError(e instanceof ApiError ? e.message : "Offline: showing nothing new"));
  }, [user, filter]);

  // Send queued reports on load and whenever the connection comes back.
  useEffect(() => {
    const sync = () => {
      if (loadOutbox().length) void flushOutbox().then(refresh);
    };
    sync();
    window.addEventListener("online", sync);
    return () => window.removeEventListener("online", sync);
  }, [refresh]);

  useEffect(refresh, [refresh]);

  if (!user) {
    return (
      <div className="page narrow">
        <h1>Field reports</h1>
        <p className="notice">Log in as a field surveyor (or editor) to register findings.</p>
      </div>
    );
  }
  if (!can("report") && !staff) {
    return (
      <div className="page narrow">
        <h1>Field reports</h1>
        <p className="notice">Your role ({user.role}) cannot use field reports.</p>
      </div>
    );
  }

  return (
    <div className={staff ? "page" : "page narrow"}>
      <h1>{staff ? "Field reports" : "Report a finding"}</h1>
      <div className={staff && can("report") ? "field-grid" : ""}>
        {can("report") && (
          <div>
            <ReportForm onQueued={refresh} onSent={refresh} />
            <Outbox items={outbox} onChange={refresh} />
          </div>
        )}
        <div>
          <div className="list-head">
            <h2>{staff ? "Inbox" : "My reports"}</h2>
            {staff && (
              <select value={filter} onChange={(e) => setFilter(e.target.value as ReportStatus | "")}>
                <option value="submitted">Waiting for review</option>
                <option value="accepted">Accepted</option>
                <option value="rejected">Rejected</option>
                <option value="">All</option>
              </select>
            )}
          </div>
          {error && <p className="muted">{error}</p>}
          {reports === null && <p className="muted">Loading…</p>}
          {reports?.length === 0 && <p className="muted">Nothing here.</p>}
          {reports?.map((r) => (
            <ReportCard key={r.id} report={r} staff={staff} onChanged={refresh} onShow={onShow} />
          ))}
        </div>
      </div>
    </div>
  );
}
