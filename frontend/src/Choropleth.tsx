import { useMemo, useState } from "react";
import { fmtArea } from "./format";
import type { AdminAreaProps } from "./types";
import { NO_DATA, SEQUENTIAL } from "./viz";

type Ring = number[][];

function rings(geometry: GeoJSON.Geometry): Ring[] {
  if (geometry.type === "Polygon") return geometry.coordinates;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.flat();
  return [];
}

/**
 * A small SVG choropleth of the administrative areas: binned single-hue ramp, direct labels,
 * hover details, click to filter. No map library needed, so it loads with the dashboard.
 */
export default function Choropleth({
  areas,
  selected,
  onSelect,
}: {
  areas: GeoJSON.FeatureCollection;
  selected: string | null;
  onSelect: (name: string | null) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const W = 520;

  const { paths, H, bins, max } = useMemo(() => {
    const all = areas.features.flatMap((f) => rings(f.geometry).flat());
    const lons = all.map((c) => c[0]);
    const lats = all.map((c) => c[1]);
    const [minX, maxX, minY, maxY] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
    const k = Math.cos((((minY + maxY) / 2) * Math.PI) / 180); // equirectangular, corrected for latitude
    const scale = (W - 20) / ((maxX - minX) * k || 1);
    const height = (maxY - minY) * scale + 20;
    const project = ([lon, lat]: number[]) => [10 + (lon - minX) * k * scale, 10 + (maxY - lat) * scale];
    const values = areas.features.map((f) => (f.properties as AdminAreaProps).contaminated_m2).filter((v) => v > 0);
    const maxValue = Math.max(0, ...values);
    const minValue = values.length ? Math.min(...values) : 0;
    // Equal-interval bins over the observed range, so the ramp's full contrast is used.
    const step = (maxValue - minValue) / SEQUENTIAL.length || 1;
    return {
      H: height,
      max: maxValue,
      bins: SEQUENTIAL.map((c, i) => ({ color: c, from: minValue + i * step, to: minValue + (i + 1) * step })),
      paths: areas.features.map((f) => {
        const p = f.properties as AdminAreaProps;
        const rs = rings(f.geometry).map((r) => r.map(project));
        const d = rs.map((r) => `M${r.map((pt) => pt.map((v) => v.toFixed(1)).join(",")).join("L")}Z`).join("");
        const pts = rs.flat();
        const cx = pts.reduce((s, q) => s + q[0], 0) / pts.length;
        const cy = pts.reduce((s, q) => s + q[1], 0) / pts.length;
        const bin =
          p.contaminated_m2 > 0 ? Math.min(SEQUENTIAL.length - 1, Math.floor((p.contaminated_m2 - minValue) / step)) : -1;
        return { p, d, cx, cy, fill: bin < 0 ? NO_DATA : SEQUENTIAL[bin], dark: bin >= 2 };
      }),
    };
  }, [areas]);

  const hovered = paths.find((x) => x.p.name === hover)?.p;

  return (
    <div className="choropleth">
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Contamination by administrative area" className="chart">
          {paths.map(({ p, d, cx, cy, fill, dark }) => (
            <g key={p.name}>
              <path
                d={d}
                fill={fill}
                stroke="#ffffff"
                strokeWidth={2}
                className={selected === p.name ? "area selected" : "area"}
                tabIndex={0}
                aria-label={`${p.name}: ${fmtArea(p.contaminated_m2)} contaminated, ${p.open_hazards} open hazards`}
                onMouseEnter={() => setHover(p.name)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(p.name)}
                onBlur={() => setHover(null)}
                onClick={() => onSelect(selected === p.name ? null : p.name)}
                onKeyDown={(e) => e.key === "Enter" && onSelect(selected === p.name ? null : p.name)}
              />
              <text x={cx} y={cy} textAnchor="middle" className={dark ? "area-label on-dark" : "area-label"}>
                {p.name}
              </text>
            </g>
          ))}
        </svg>
        {hovered && (
          <div className="tooltip" style={{ left: "50%" }}>
            <strong>{fmtArea(hovered.contaminated_m2)}</strong>
            <span>{hovered.name}</span>
            <span className="muted">{hovered.open_hazards} open hazards · click to filter</span>
          </div>
        )}
      </div>
      <div className="ramp-legend" aria-label="Legend: contaminated area">
        {bins.map((b) => (
          <span key={b.color}>
            <span className="swatch" style={{ background: b.color }} />
            {fmtArea(b.from)}–{fmtArea(b.to)}
          </span>
        ))}
        <span>
          <span className="swatch" style={{ background: NO_DATA }} />
          none
        </span>
      </div>
      {max === 0 && <p className="muted">No open contamination.</p>}
    </div>
  );
}
