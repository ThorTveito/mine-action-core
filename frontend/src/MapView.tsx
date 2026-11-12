import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import { STATUS_COLOR } from "./status";
import type { HazardCollection, HazardStatus, MapFocus, TopologyIssue } from "./types";

interface Props {
  data: HazardCollection | null;
  visible: Set<HazardStatus>;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  issues: TopologyIssue[] | null; // null hides the topology layer
  focus: MapFocus | null; // fly here when it changes
  terrain: TerrainSettings;
  reports: GeoJSON.FeatureCollection | null; // field reports; null hides the layer
}

export interface TerrainSettings {
  enabled: boolean;
  exaggeration: number;
}

const ISSUE_COLOR = { error: "#c0262d", warning: "#e08a00", info: "#667085" } as const;

const SOURCE = "hazards";
const DEM = "terrain-dem";
// Free, keyless elevation tiles (Terrarium encoding) from the AWS Open Data terrain tiles.
const DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const ISSUES = "issues";
const REPORTS = "field-reports";
const REPORT_COLOR = { submitted: "#7c3aed", accepted: "#1f2937", rejected: "#9ca3af" } as const;

export default function MapView({
  data,
  visible,
  selectedId,
  onSelect,
  issues,
  focus,
  terrain,
  reports,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loaded = useRef(false);
  const fitted = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const latest = useRef({ data, visible, selectedId, issues, focus, terrain, reports });
  latest.current = { data, visible, selectedId, issues, focus, terrain, reports };
  const appliedTerrain = useRef<string>("off");

  // Switch 3D terrain on/off. Hazard polygons are draped on the surface automatically.
  const applyTerrain = (map: maplibregl.Map, t: TerrainSettings) => {
    const key = t.enabled ? `on:${t.exaggeration}` : "off";
    if (key === appliedTerrain.current || !map.getSource(DEM)) return;
    const wasOff = appliedTerrain.current === "off";
    appliedTerrain.current = key;
    if (t.enabled) {
      map.setTerrain({ source: DEM, exaggeration: t.exaggeration });
      map.setLayoutProperty("hillshade", "visibility", "visible");
      if (wasOff) map.easeTo({ pitch: 62, bearing: -20, duration: 900 });
    } else {
      map.setTerrain(null);
      map.setLayoutProperty("hillshade", "visibility", "none");
      map.easeTo({ pitch: 0, bearing: 0, duration: 700 });
    }
  };

  const sync = () => {
    const map = mapRef.current;
    if (!map || !loaded.current) return;
    const { data, visible, selectedId, issues, focus, terrain, reports } = latest.current;
    (map.getSource(REPORTS) as maplibregl.GeoJSONSource | undefined)?.setData(
      reports ?? { type: "FeatureCollection", features: [] },
    );
    const source = map.getSource(SOURCE) as maplibregl.GeoJSONSource | undefined;
    if (source && data) source.setData(data as unknown as GeoJSON.FeatureCollection);
    map.setFilter("hazards-fill", ["in", ["get", "status"], ["literal", [...visible]]]);
    map.setFilter("hazards-line", ["in", ["get", "status"], ["literal", [...visible]]]);
    map.setFilter("hazards-selected", ["==", ["get", "id"], selectedId ?? -1]);
    applyTerrain(map, terrain);
    const issueSource = map.getSource(ISSUES) as maplibregl.GeoJSONSource | undefined;
    issueSource?.setData({
      type: "FeatureCollection",
      features: (issues ?? [])
        .filter((i) => i.location !== null)
        .map((i) => ({
          type: "Feature" as const,
          geometry: i.location as GeoJSON.Point,
          properties: { severity: i.severity, rule: i.rule, hazardId: i.hazard_ids[0] ?? -1 },
        })),
    });
    if (data && data.features.length > 0 && !fitted.current) {
      fitted.current = true;
      if (focus?.lon !== undefined) return; // a focus request wins over fitting to all hazards
      const bounds = new maplibregl.LngLatBounds();
      for (const f of data.features) {
        for (const polygon of f.geometry.coordinates) {
          for (const [lng, lat] of polygon[0]) bounds.extend([lng, lat]);
        }
      }
      map.fitBounds(bounds, { padding: 60, animate: false });
      fitted.current = true;
    }
  };

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      center: [8.2, 61.5],
      zoom: 9,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
    });
    mapRef.current = map;
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }),
      "top-right",
    );

    map.on("load", () => {
      map.addSource(DEM, {
        type: "raster-dem",
        tiles: [DEM_TILES],
        encoding: "terrarium",
        tileSize: 256,
        maxzoom: 15,
        attribution: "Terrain: Mapzen / AWS Open Data (SRTM, NED, GMTED)",
      });
      map.addLayer({
        id: "hillshade",
        type: "hillshade",
        source: DEM,
        layout: { visibility: "none" },
        paint: { "hillshade-exaggeration": 0.6, "hillshade-shadow-color": "#3b4252" },
      });
      map.addSource(SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        promoteId: "id",
      });
      const colorExpr: maplibregl.ExpressionSpecification = [
        "match",
        ["get", "status"],
        ...Object.entries(STATUS_COLOR).flat(),
        "#888888",
      ] as unknown as maplibregl.ExpressionSpecification;
      map.addLayer({
        id: "hazards-fill",
        type: "fill",
        source: SOURCE,
        paint: { "fill-color": colorExpr, "fill-opacity": 0.5 },
      });
      map.addLayer({
        id: "hazards-line",
        type: "line",
        source: SOURCE,
        paint: { "line-color": colorExpr, "line-width": 1.5 },
      });
      map.addLayer({
        id: "hazards-selected",
        type: "line",
        source: SOURCE,
        paint: { "line-color": "#111111", "line-width": 3 },
      });
      map.addSource(ISSUES, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "issues-circle",
        type: "circle",
        source: ISSUES,
        paint: {
          "circle-radius": 7,
          "circle-color": [
            "match",
            ["get", "severity"],
            "error",
            ISSUE_COLOR.error,
            "warning",
            ISSUE_COLOR.warning,
            ISSUE_COLOR.info,
          ],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });
      map.addSource(REPORTS, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "reports-circle",
        type: "circle",
        source: REPORTS,
        paint: {
          "circle-radius": 6,
          "circle-color": [
            "match",
            ["get", "status"],
            "submitted",
            REPORT_COLOR.submitted,
            "accepted",
            REPORT_COLOR.accepted,
            REPORT_COLOR.rejected,
          ],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });
      map.on("click", "reports-circle", (e) => {
        const f = e.features?.[0];
        if (!f || f.geometry.type !== "Point") return;
        const p = f.properties as { code: string; status: string; finding_type: string; reported_by: string };
        const box = document.createElement("div");
        box.className = "popup";
        const title = document.createElement("strong");
        title.textContent = p.code; // textContent, never innerHTML: report data is user input
        const meta = document.createElement("div");
        meta.textContent = `${p.finding_type.replace("_", " ")} · ${p.status} · by ${p.reported_by}`;
        box.append(title, meta);
        new maplibregl.Popup({ closeButton: true })
          .setLngLat(f.geometry.coordinates as [number, number])
          .setDOMContent(box)
          .addTo(map);
      });
      map.on("click", "issues-circle", (e) => {
        const id = e.features?.[0]?.properties?.hazardId as number | undefined;
        if (id !== undefined && id >= 0) onSelectRef.current(id);
      });
      map.on("click", "hazards-fill", (e) => {
        const id = e.features?.[0]?.properties?.id as number | undefined;
        onSelectRef.current(id ?? null);
      });
      map.on("click", (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ["hazards-fill", "issues-circle", "reports-circle"] }).length === 0) {
          onSelectRef.current(null);
        }
      });
      map.on("mouseenter", "hazards-fill", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "hazards-fill", () => (map.getCanvas().style.cursor = ""));
      loaded.current = true;
      sync();
    });

    return () => {
      loaded.current = false;
      fitted.current = false;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(sync, [data, visible, selectedId, issues, terrain.enabled, terrain.exaggeration, reports]);

  useEffect(() => {
    const map = mapRef.current;
    if (map && focus && focus.lon !== undefined && focus.lat !== undefined) {
      map.flyTo({ center: [focus.lon, focus.lat], zoom: 16, duration: 600 });
    }
  }, [focus]);

  return <div ref={container} className="map" />;
}
