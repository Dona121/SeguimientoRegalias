import type { Modo } from "./MapaSucre";
import { SUBREGIONES, SUB_COLOR } from "../data/subregiones";

interface Props {
  modo: Modo;
  min: number;
  max: number;
  tieneDatos: boolean;
}

const fmt = (n: number) => (Number.isInteger(n) ? n : +n.toFixed(1));

export function Leyenda({ modo, min, max, tieneDatos }: Props) {
  if (modo === "sub") {
    return (
      <div className="leyenda">
        <div className="titulo">Subregiones</div>
        {Object.entries(SUBREGIONES).map(([sub, codes]) => (
          <div className="row" key={sub}>
            <i style={{ background: SUB_COLOR[sub] }} />
            <span>{sub}</span>
            <span className="n">{codes.length}</span>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="leyenda">
      <div className="titulo">Escala de valor</div>
      <div className="barra" />
      <div className="barra-lbls">
        <span>{tieneDatos ? fmt(min) : "—"}</span>
        <span>{tieneDatos ? fmt(max) : "—"}</span>
      </div>
      <div className="nd">
        <i />
        <span>Sin dato</span>
      </div>
    </div>
  );
}
