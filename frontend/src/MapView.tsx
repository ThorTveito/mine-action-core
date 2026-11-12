import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import { STATUS_COLOR } from "./status";
import type { HazardCollection, HazardStatus } from "./types";

interface Props {
  data: HazardCollection | null;
  visible: Set<HazardStatus>;
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}

const SOURCE = "hazards";

export default function MapView({ data, visible, selectedId, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const loaded = useRef(false);
  const fitted = useRef(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const latest = useRef({ data, visible, selectedId });
  latest.current = { data, visible, selectedId };

  const sync = () => {
    const map = mapRef.current;
    if (!map || !loaded.current) return;
    const { data, visible, selectedId } = latest.current;
    const source = map.getSource(SOURCE) as maplibregl.GeoJSONSource | undefined;
    if (source && data) source.setData(data as unknown as GeoJSON.FeatureCollection);
    map.setFilter("hazards-fill", ["in", ["get", "status"], ["literal", [...visible]]]);
    map.setFilter("hazards-line", ["in", ["get", "status"], ["literal", [...visible]]]);
    map.setFilter("hazards-selected", ["==", ["get", "id"], selectedId ?? -1]);
    if (data && data.features.length > 0 && !fitted.current) {
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
      center: [18.1, 15.05],
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
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
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
      map.on("click", "hazards-fill", (e) => {
        const id = e.features?.[0]?.properties?.id as number | undefined;
        onSelectRef.current(id ?? null);
      });
      map.on("click", (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ["hazards-fill"] }).length === 0) {
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

  useEffect(sync, [data, visible, selectedId]);

  return <div ref={container} className="map" />;
}
