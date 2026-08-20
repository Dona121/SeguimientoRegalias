import { useEffect, useMemo, useState } from "react";
import type { FeatureCollection } from "geojson";
import { MapaSucre, type Modo } from "./components/MapaSucre";
import { PanelDatos } from "./components/PanelDatos";
import { Leyenda } from "./components/Leyenda";
import { parseArchivo, adivinarColumnas, type Tabla } from "./lib/parseArchivo";
import { homologar, type Candidato } from "./lib/homologar";

export interface Resultado {
  valores: Record<string, number>;
  min: number;
  max: number;
  ubicados: number;
  dudas: { original: string; candidatos: Candidato[] }[];
  sin: string[];
}

export default function App() {
  const [geojson, setGeojson] = useState<FeatureCollection | null>(null);
  const [modo, setModo] = useState<Modo>("sub"); // al entrar: mapa por subregión
  const [tabla, setTabla] = useState<Tabla | null>(null);
  const [colMun, setColMun] = useState(0);
  const [colVal, setColVal] = useState(1);

  useEffect(() => {
    fetch("/Sucre.geojson")
      .then((r) => r.json())
      .then((gj: FeatureCollection) => setGeojson(gj))
      .catch(() => setGeojson(null));
  }, []);

  async function onFile(file: File) {
    const t = await parseArchivo(file);
    const { colMun: cm, colVal: cv } = adivinarColumnas(t.head);
    setColMun(cm);
    setColVal(cv);
    setTabla(t);
  }

  const resultado = useMemo<Resultado | null>(() => {
    if (!tabla) return null;
    const valores: Record<string, number> = {};
    const dudas: Resultado["dudas"] = [];
    const sin: string[] = [];

    for (const row of tabla.rows) {
      const rawMun = row[colMun];
      if (!rawMun) continue;
      const h = homologar(rawMun);
      const val = parseFloat((row[colVal] ?? "").toString().replace(",", "."));
      if (h.tipo === "match") {
        if (!Number.isNaN(val)) valores[h.code] = val;
      } else if (h.tipo === "duda") {
        dudas.push({ original: rawMun, candidatos: h.candidatos });
      } else {
        sin.push(rawMun);
      }
    }

    const vals = Object.values(valores);
    return {
      valores,
      min: vals.length ? Math.min(...vals) : 0,
      max: vals.length ? Math.max(...vals) : 0,
      ubicados: Object.keys(valores).length,
      dudas,
      sin,
    };
  }, [tabla, colMun, colVal]);

  return (
    <div className="app">
      <aside className="side">
        <PanelDatos
          modo={modo}
          onModo={setModo}
          tabla={tabla}
          colMun={colMun}
          colVal={colVal}
          onFile={onFile}
          onColMun={setColMun}
          onColVal={setColVal}
          resultado={resultado}
        />
      </aside>

      <div className="map-wrap">
        {geojson && (
          <MapaSucre
            geojson={geojson}
            modo={modo}
            datos={resultado?.valores ?? {}}
            min={resultado?.min ?? 0}
            max={resultado?.max ?? 0}
          />
        )}
        <Leyenda
          modo={modo}
          min={resultado?.min ?? 0}
          max={resultado?.max ?? 0}
          tieneDatos={!!resultado && resultado.ubicados > 0}
        />
      </div>
    </div>
  );
}
