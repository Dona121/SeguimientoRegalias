# Mapa de Sucre — Starter (React + MapLibre)

SPA de una sola página que dibuja los 26 municipios de Sucre y permite **cargar un
archivo (CSV/Excel) del usuario** para colorear el mapa (*choropleth*) por municipio.
Implementa el stack de referencia y las reglas descritas en
`../docs/MapaSucre_Referencia.md`.

## Stack

- **React + Vite + TypeScript** — SPA.
- **MapLibre GL JS** (vía `react-map-gl`) — motor de mapa vectorial, sin token.
- **PapaParse** (CSV) + **SheetJS/xlsx** (Excel) — carga de archivos.
- **Tailwind v4** (plugin de Vite) — disponible para tu diseño; el layout base va en
  `src/index.css` como CSS plano.

## Cómo correr

```bash
npm install
npm run dev      # abre http://localhost:5173
```

Build de producción:

```bash
npm run build && npm run preview
```

## Cómo usarlo

1. Arranca la app: verás los 26 municipios en gris (sin datos).
2. Sube `ejemplo.csv` (incluido) o tu propio archivo con **una columna de municipio o
   código DANE** y **una columna de valor**.
3. La app detecta las columnas, **homologa** los nombres (§6 de la guía) y colorea el
   mapa. Haz clic en un municipio para ver su valor.
4. Los municipios que **no se pudieron homologar con certeza** se listan en el panel
   para que los confirmes (no se asignan a ciegas).

## Estructura

```
public/Sucre.geojson          # geometría real (26 municipios)
src/
├── data/municipios.ts        # tabla maestra §5 (código, nombre, centroide) + ALIAS
├── lib/homologar.ts          # protocolo §6: código > nombre > alias > fuzzy > preguntar
├── lib/parseArchivo.ts       # CSV/Excel → tabla + heurística de columnas
├── components/MapaSucre.tsx  # react-map-gl + MapLibre: Source geojson + choropleth
├── components/PanelDatos.tsx # uploader + selección de columnas + avisos
├── components/Leyenda.tsx
└── App.tsx                   # una sola página: panel + mapa
```

## Notas

- **Unión por código DANE** (`MPIO_CDPMP`) siempre que exista en el archivo: es exacta.
- Para escalar (muchos puntos, nivel nacional): teselas vectoriales, simplificación de
  geometría, o backend FastAPI + GeoPandas para geoprocesamiento pesado.
- El estilo base usa teselas de OpenStreetMap. Para producción con alto tráfico,
  considera un proveedor de teselas propio o vectoriales.
