import { useMemo, useState } from "react";
import { fmtArea } from "./format";
import { STATUS_COLOR, STATUS_LABEL } from "./status";
import type { HazardCollection, HazardStatus, MapFocus } from "./types";

type Bounds = [number, number, number, number]; // west, south, east, north
type Kind = "hazards" | "reports";
type Sort = "code" | "name" | "area" | "status";

const PAGE = 50;
const STATUS_RANK: Record<HazardStatus, number> = {
  confirmed: 0,
  in_clearance: 1,
  suspected: 2,
  released: 3,
  cancelled: 4,
};
const REPORT_COLOR: Record<string, string> = { submitted: "#7c3aed", accepted: "#1f2937", rejected: "#9ca3af" };

function bboxOf(coords: number[][][][]): Bounds {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity; // prettier-ignore
  for (const poly of coords) for (const ring of poly) for (const [x, y] of ring) {
    if (x < w) w = x;
    if (x > e) e = x;
    if (y < s) s = y;
    if (y > n) n = y;
  } // prettier-ignore
  return [w, s, e, n];
}

const intersects = (a: Bounds, b: Bounds) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

interface Props {
  hazards: HazardCollection | null;
  reports: GeoJSON.FeatureCollection | null;
  visible: Set<HazardStatus>;
  view: Bounds | null;
  selectedId: number | null;
  onPick: (focus: Omit<MapFocus, "nonce">) => void;
}

/** Every item on the map as a searchable, sortable list, so nothing is missed by eye. */
export default function ItemList({ hazards, reports, visible, view, selectedId, onPick }: Props) {
  const [kind, setKind] = useState<Kind>("hazards");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("code");
  const [inView, setInView] = useState(false);
  const [limit, setLimit] = useState(PAGE);

  const hazardRows = useMemo(
    () =>
      (hazards?.features ?? []).map((f) => ({
        ...f.properties,
        bounds: bboxOf(f.geometry.coordinates),
      })),
    [hazards],
  );

  const q = query.trim().toLowerCase();

  const hazardList = useMemo(() => {
    const rows = hazardRows.filter(
      (h) =>
        visible.has(h.status) &&
        (!inView || !view || intersects(h.bounds, view)) &&
        (!q || [h.code, h.name, h.region, h.hazard_class, h.status].some((v) => v.toLowerCase().includes(q))),
    );
    const by: Record<Sort, (a: (typeof rows)[number], b: (typeof rows)[number]) => number> = {
      code: (a, b) => a.code.localeCompare(b.code),
      name: (a, b) => a.name.localeCompare(b.name) || a.code.localeCompare(b.code),
      area: (a, b) => b.area_m2 - a.area_m2,
      status: (a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || a.code.localeCompare(b.code),
    };
    return rows.sort(by[sort]);
  }, [hazardRows, visible, inView, view, q, sort]);

  const reportList = useMemo(() => {
    const rows = (reports?.features ?? [])
      .filter((f) => f.geometry.type === "Point")
      .map((f) => {
        const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
        const p = f.properties as { id: number; code: string; status: string; finding_type: string; item_category: string | null };
        return { ...p, lon, lat };
      })
      .filter(
        (r) =>
          (!inView || !view || (r.lon >= view[0] && r.lon <= view[2] && r.lat >= view[1] && r.lat <= view[3])) &&
          (!q || [r.code, r.status, r.finding_type, r.item_category ?? ""].some((v) => v.toLowerCase().includes(q))),
      );
    return rows.sort((a, b) => b.code.localeCompare(a.code));
  }, [reports, inView, view, q]);

  const total = kind === "hazards" ? hazardList.length : reportList.length;

  return (
    <section className="card item-list">
      {reports && (
        <div className="segmented small" role="tablist">
          <button role="tab" aria-selected={kind === "hazards"} className={kind === "hazards" ? "active" : ""} onClick={() => setKind("hazards")}>
            Hazards
          </button>
          <button role="tab" aria-selected={kind === "reports"} className={kind === "reports" ? "active" : ""} onClick={() => setKind("reports")}>
            Field reports
          </button>
        </div>
      )}
      <input
        className="search"
        type="search"
        placeholder={kind === "hazards" ? "Search code, name, region, type…" : "Search code, status, type…"}
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setLimit(PAGE);
        }}
        aria-label="Search the list"
      />
      <div className="list-controls">
        <label className="check inline-check">
          <input type="checkbox" checked={inView} onChange={(e) => setInView(e.target.checked)} />
          Only in map view
        </label>
        {kind === "hazards" && (
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort by">
            <option value="code">Code</option>
            <option value="name">Name</option>
            <option value="area">Largest first</option>
            <option value="status">Status</option>
          </select>
        )}
      </div>
      <p className="muted count-line">
        {total} {kind === "hazards" ? (total === 1 ? "hazard" : "hazards") : total === 1 ? "field report" : "field reports"}
        {kind === "hazards" && visible.size < 5 ? " (status filter on)" : ""}
      </p>

      <ul className="items">
        {kind === "hazards" &&
          hazardList.slice(0, limit).map((h) => (
            <li key={h.id}>
              <button
                className={h.id === selectedId ? "item selected" : "item"}
                onClick={() => onPick({ hazardId: h.id, bounds: h.bounds })}
              >
                <span className="dot" style={{ background: STATUS_COLOR[h.status] }} />
                <span className="item-main">
                  <span>
                    <strong>{h.code}</strong> {h.name}
                  </span>
                  <span className="muted">
                    {STATUS_LABEL[h.status]} · {h.region} · {fmtArea(h.area_m2)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        {kind === "reports" &&
          reportList.slice(0, limit).map((r) => (
            <li key={r.id}>
              <button className="item" onClick={() => onPick({ lon: r.lon, lat: r.lat })}>
                <span className="dot" style={{ background: REPORT_COLOR[r.status] ?? "#9ca3af" }} />
                <span className="item-main">
                  <span>
                    <strong>{r.code}</strong> {r.finding_type.replace("_", " ")}
                  </span>
                  <span className="muted">
                    {r.status}
                    {r.item_category ? ` · ${r.item_category.replace("_", " ")}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
      </ul>
      {total > limit && (
        <button className="small" onClick={() => setLimit(limit + PAGE)}>
          Show {Math.min(PAGE, total - limit)} more
        </button>
      )}
      {total === 0 && <p className="muted">Nothing matches.</p>}
    </section>
  );
}
