// Protocolo de homologación de nombres (§6 de la guía).
// Orden: código DANE > nombre normalizado > alias > fuzzy (≥0.90) > PREGUNTAR.
import { MUNICIPIOS, ALIAS } from "../data/municipios";

/** Normaliza: trim + colapsar espacios + MAYÚSCULAS + sin tildes + sin puntos. */
export function norm(s: string): string {
  if (!s) return "";
  const t = s.toString().normalize("NFKD").replace(/[̀-ͯ]/g, "");
  return t.replace(/\s+/g, " ").trim().toUpperCase().replace(/^[.\s]+|[.\s]+$/g, "");
}

const NAME2CODE: Record<string, string> = {};
const CODE2NOMBRE: Record<string, string> = {};
for (const m of MUNICIPIOS) {
  NAME2CODE[norm(m.nombre)] = m.code;
  CODE2NOMBRE[m.code] = m.nombre;
}
const NORM_NAMES = Object.keys(NAME2CODE);

export function code2nombre(code: string): string {
  return CODE2NOMBRE[code] ?? code;
}

/** Distancia de edición (Levenshtein) para la coincidencia aproximada opcional. */
function lev(a: string, b: string): number {
  const m = a.length, n = b.length;
  const d: number[][] = Array.from({ length: m + 1 }, (_, i) => {
    const row = new Array<number>(n + 1).fill(0);
    row[0] = i;
    return row;
  });
  for (let j = 0; j <= n; j++) d[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      d[i][j] = Math.min(
        d[i - 1][j] + 1,
        d[i][j - 1] + 1,
        d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
    }
  }
  return d[m][n];
}

export interface Candidato {
  code: string;
  nombre: string;
  sim: number;
}

export type Homologacion =
  | { tipo: "match"; code: string }
  | { tipo: "duda"; candidatos: Candidato[] }
  | { tipo: "sin" };

/**
 * Intenta ubicar el municipio de un dato del usuario contra la tabla oficial.
 * Devuelve:
 *   - {tipo:"match"} cuando hay certeza (código, nombre exacto, alias o fuzzy alto).
 *   - {tipo:"duda"} con los candidatos más parecidos → PREGUNTAR al usuario (§6.4).
 *   - {tipo:"sin"} cuando no hay coincidencia razonable.
 */
export function homologar(raw: string): Homologacion {
  const t = norm(raw);

  // 1. Por código DANE (lo más seguro).
  if (/^70\d{3}$/.test(t) && CODE2NOMBRE[t]) return { tipo: "match", code: t };

  // 2-3. Nombre normalizado exacto o alias.
  const dane = ALIAS[t] ?? t;
  if (NAME2CODE[dane]) return { tipo: "match", code: NAME2CODE[dane] };

  // 4. Coincidencia aproximada (fuzzy).
  const cands: Candidato[] = NORM_NAMES
    .map((n) => {
      const code = NAME2CODE[n];
      return {
        code,
        nombre: CODE2NOMBRE[code],
        sim: 1 - lev(dane, n) / Math.max(dane.length, n.length || 1),
      };
    })
    .sort((a, b) => b.sim - a.sim);

  const best = cands[0];
  const second = cands[1];
  if (best && best.sim >= 0.90 && (!second || best.sim - second.sim > 0.06)) {
    return { tipo: "match", code: best.code };
  }

  // 5. Sin certeza → devolver candidatos para preguntar, o "sin" si nada se acerca.
  if (best && best.sim >= 0.6) return { tipo: "duda", candidatos: cands.slice(0, 2) };
  return { tipo: "sin" };
}
