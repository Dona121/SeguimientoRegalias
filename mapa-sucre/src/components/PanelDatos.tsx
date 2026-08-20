import type { Tabla } from "../lib/parseArchivo";
import type { Resultado } from "../App";
import type { Modo } from "./MapaSucre";

interface Props {
  modo: Modo;
  onModo: (m: Modo) => void;
  tabla: Tabla | null;
  colMun: number;
  colVal: number;
  onFile: (f: File) => void;
  onColMun: (i: number) => void;
  onColVal: (i: number) => void;
  resultado: Resultado | null;
}

export function PanelDatos({
  modo,
  onModo,
  tabla,
  colMun,
  colVal,
  onFile,
  onColMun,
  onColVal,
  resultado,
}: Props) {
  return (
    <div className="panel">
      <div className="eyebrow">Departamento de Sucre · 26 municipios</div>
      <h1>Mapa municipal</h1>

      <div className="seg" role="tablist">
        <button
          className={modo === "sub" ? "on" : ""}
          role="tab"
          aria-selected={modo === "sub"}
          onClick={() => onModo("sub")}
        >
          Por subregión
        </button>
        <button
          className={modo === "dat" ? "on" : ""}
          role="tab"
          aria-selected={modo === "dat"}
          onClick={() => onModo("dat")}
        >
          Datos (CSV)
        </button>
      </div>

      {modo === "sub" && (
        <p className="muted">
          El mapa se colorea por subregión fisiográfica oficial. Pasa el cursor por un
          municipio para ver su nombre y subregión.
        </p>
      )}

      {modo === "dat" && (
        <>
          <label className="field">
            <span>Archivo (CSV / Excel)</span>
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onFile(f);
              }}
            />
          </label>

          {tabla && (
            <div className="cols">
              <label className="field">
                <span>Columna municipio / código</span>
                <select value={colMun} onChange={(e) => onColMun(+e.target.value)}>
                  {tabla.head.map((h, i) => (
                    <option key={i} value={i}>
                      {h || `(col ${i + 1})`}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Columna valor</span>
                <select value={colVal} onChange={(e) => onColVal(+e.target.value)}>
                  {tabla.head.map((h, i) => (
                    <option key={i} value={i}>
                      {h || `(col ${i + 1})`}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}

          {resultado && (
            <div className="status">
              <div className="ok">
                Ubicados: <b>{resultado.ubicados}/26</b> municipios.
              </div>

              {resultado.dudas.length > 0 && (
                <div className="warn">
                  <b>Por revisar (no homologados con certeza):</b>
                  <ul>
                    {resultado.dudas.map((d, i) => (
                      <li key={i}>
                        "{d.original}" → ¿
                        {d.candidatos.map((c) => `${c.nombre} (${c.code})`).join(" / ")}?
                      </li>
                    ))}
                  </ul>
                  <p>Confírmame estos casos y ajusto el mapa.</p>
                </div>
              )}

              {resultado.sin.length > 0 && (
                <div className="warn">
                  <b>Sin coincidencia:</b> {resultado.sin.join(", ")}
                </div>
              )}
            </div>
          )}

          <p className="hint">
            Si tu archivo trae el código DANE (p. ej. 70001), la unión es exacta. Une por
            código siempre que puedas.
          </p>
        </>
      )}
    </div>
  );
}
