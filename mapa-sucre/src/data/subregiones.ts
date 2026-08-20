// Subregiones fisiográficas oficiales de Sucre (5). Confirmadas con el usuario.
// Fuente: clasificación departamental / DANE.
export const SUBREGIONES: Record<string, string[]> = {
  "Golfo de Morrosquillo": ["70221", "70523", "70820", "70823", "70713"],
  "Montes de María":       ["70001", "70473", "70508", "70230", "70204"],
  "Sabanas":               ["70215", "70418", "70670", "70702", "70110",
                            "70742", "70717", "70235", "70233"],
  "San Jorge":             ["70708", "70678", "70124", "70400"],
  "La Mojana":             ["70771", "70429", "70265"],
};

// Colores categóricos, legibles sobre fondo blanco.
export const SUB_COLOR: Record<string, string> = {
  "Golfo de Morrosquillo": "#0ea5a4",
  "Montes de María":       "#5a9e2f",
  "Sabanas":               "#e08b12",
  "San Jorge":             "#2f6bd6",
  "La Mojana":             "#8a5cf0",
};

export const CODE2SUB: Record<string, string> = {};
for (const [sub, codes] of Object.entries(SUBREGIONES)) {
  for (const c of codes) CODE2SUB[c] = sub;
}

// Expresión MapLibre 'match' para colorear cada municipio por su subregión.
export function subregionMatchExpr(): unknown[] {
  const expr: unknown[] = ["match", ["get", "MPIO_CDPMP"]];
  for (const [code, sub] of Object.entries(CODE2SUB)) {
    expr.push(code, SUB_COLOR[sub]);
  }
  expr.push("#dfe6f0"); // fallback (sin subregión)
  return expr;
}
