import { useEffect, useRef, useState } from "react";
import Map, { Source, Layer, Popup, type MapRef } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection } from "geojson";
import { MUNICIPIOS } from "../data/municipios";
import { CODE2SUB, subregionMatchExpr } from "../data/subregiones";

const ALL_CODES = MUNICIPIOS.map((m) => m.code);

// Mapa base blanco (institucional): sin teselas de calles, solo un fondo claro
// sobre el que resaltan los polígonos municipales.
const MAP_STYLE = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef3fa" } }],
} as unknown as maplibregl.StyleSpecification;

// Choropleth data-driven por feature-state 't' (0..1). Gris si no hay dato.
const dataFill = [
  "case",
  ["==", ["feature-state", "t"], null],
  "#dfe6f0",
  ["interpolate", ["linear"], ["feature-state", "t"],
    0, "#e2ecfb", 0.5, "#5a92e6", 1, "#123a86"],
];

const lineLayer = {
  id: "mun-line",
  type: "line",
  paint: { "line-color": "#ffffff", "line-width": 0.9 },
} as const;

export type Modo = "sub" | "dat";

interface Props {
  geojson: FeatureCollection;
  modo: Modo;
  datos: Record<string, number>;
  min: number;
  max: number;
}

interface PopupInfo {
  lng: number;
  lat: number;
  nombre: string;
  code: string;
  sub: string;
  valor?: number;
}

export function MapaSucre({ geojson, modo, datos, min, max }: Props) {
  const mapRef = useRef<MapRef>(null);
  const [loaded, setLoaded] = useState(false);
  const [popup, setPopup] = useState<PopupInfo | null>(null);
  const [cursor, setCursor] = useState("");

  // Cambia el color del relleno según el modo activo.
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !loaded) return;
    const expr = modo === "sub" ? subregionMatchExpr() : dataFill;
    map.setPaintProperty("mun-fill", "fill-color", expr as never);
  }, [modo, loaded]);

  // En modo datos, inyecta los valores como feature-state (unión por código DANE).
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !loaded || modo !== "dat") return;
    for (const code of ALL_CODES) {
      const v = datos[code];
      const t = v == null ? null : max > min ? (v - min) / (max - min) : 0.5;
      map.setFeatureState({ source: "mun", id: code }, { t });
    }
  }, [datos, min, max, loaded, modo]);

  return (
    <Map
      ref={mapRef}
      initialViewState={{ longitude: -75.1, latitude: 9.0, zoom: 8 }}
      mapStyle={MAP_STYLE}
      style={{ position: "absolute", inset: 0 }}
      interactiveLayerIds={["mun-fill"]}
      cursor={cursor}
      onLoad={() => setLoaded(true)}
      onMouseEnter={() => setCursor("pointer")}
      onMouseLeave={() => setCursor("")}
      onClick={(e) => {
        const f = e.features?.[0];
        if (!f) {
          setPopup(null);
          return;
        }
        const code = String(f.id);
        const props = (f.properties ?? {}) as Record<string, unknown>;
        setPopup({
          lng: e.lngLat.lng,
          lat: e.lngLat.lat,
          nombre: String(props.MPIO_CNMBR ?? ""),
          code,
          sub: CODE2SUB[code] ?? "",
          valor: datos[code],
        });
      }}
    >
      <Source id="mun" type="geojson" data={geojson} promoteId="MPIO_CDPMP">
        <Layer id="mun-fill" type="fill" paint={{ "fill-color": "#dfe6f0", "fill-opacity": 0.9 }} />
        <Layer {...lineLayer} />
      </Source>

      {popup && (
        <Popup
          longitude={popup.lng}
          latitude={popup.lat}
          anchor="bottom"
          onClose={() => setPopup(null)}
          closeOnClick={false}
        >
          <div>
            <b>{popup.nombre}</b> ({popup.code})
            <br />
            <span style={{ color: "#5b6b82" }}>{popup.sub}</span>
            {modo === "dat" && (
              <>
                <br />
                {popup.valor == null ? "Sin dato" : <>Valor: <b>{popup.valor}</b></>}
              </>
            )}
          </div>
        </Popup>
      )}
    </Map>
  );
}
