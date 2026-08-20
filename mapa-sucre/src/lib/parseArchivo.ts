// Carga y parseo del archivo del usuario (§7.2): CSV o Excel → tabla de strings.
import Papa from "papaparse";
import * as XLSX from "xlsx";

export interface Tabla {
  head: string[];
  rows: string[][];
}

/** Lee un File (CSV / XLSX / XLS) y devuelve encabezado + filas como texto. */
export async function parseArchivo(file: File): Promise<Tabla> {
  const ext = file.name.split(".").pop()?.toLowerCase();

  if (ext === "xlsx" || ext === "xls") {
    const buf = await file.arrayBuffer();
    const wb = XLSX.read(buf, { type: "array" });
    const ws = wb.Sheets[wb.SheetNames[0]];
    const aoa = XLSX.utils.sheet_to_json<unknown[]>(ws, {
      header: 1,
      raw: false,
      defval: "",
    });
    const rows = aoa.map((r) => r.map((c) => (c ?? "").toString().trim()));
    const head = rows.shift() ?? [];
    return { head, rows: rows.filter((r) => r.some((c) => c !== "")) };
  }

  // CSV / texto delimitado (coma o punto y coma).
  const text = (await file.text()).trim();
  const parsed = Papa.parse<string[]>(text, { skipEmptyLines: true });
  const data = (parsed.data as string[][]).map((r) => r.map((c) => (c ?? "").toString().trim()));
  const head = data.shift() ?? [];
  return { head, rows: data };
}

/** Heurística: adivina qué columnas son "municipio/código" y "valor". */
export function adivinarColumnas(head: string[]): { colMun: number; colVal: number } {
  let colMun = 0;
  let colVal = head.length > 1 ? 1 : 0;
  head.forEach((h, i) => {
    const H = h.normalize("NFKD").replace(/[̀-ͯ]/g, "").toUpperCase();
    if (/MUNICIP|MPIO|CODIGO|DANE/.test(H)) colMun = i;
    if (/VALOR|TOTAL|MONTO|CANT|AVANCE|PROYECT|PRESUP/.test(H)) colVal = i;
  });
  return { colMun, colVal };
}
