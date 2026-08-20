# Mapa de la Costa Caribe — Adherencia (para que las figuras se rendericen bien)

Instrucciones **cortas y obligatorias**. Objetivo único: que las geometrías de los
**195 municipios** de los 7 departamentos de la Costa Caribe **se desplieguen
correctamente** (sin deformarse, sin municipios faltantes, sin quedar en el lugar
equivocado).

> **Foco principal: SUCRE.** El mapa es de Sucre (departamento `70`, 26 municipios): es
> el protagonista — es lo que se colorea, se etiqueta y responde a la interacción y a los
> datos. Los otros 6 departamentos (Atlántico, Bolívar, Cesar, Córdoba, La Guajira,
> Magdalena) se dibujan **solo como contorno departamental de contexto**: la **silueta
> completa del departamento** (sin las líneas internas entre sus municipios), atenuada,
> sin datos ni interacción destacada. Sirven para ubicar a Sucre dentro de la región, no
> para robarle protagonismo.

> **Reemplazo del dataset:** antes esta guía usaba `Sucre.geojson` (solo 26 municipios
> del departamento de Sucre). **Queda reemplazado por `DepartamentosCostaCaribe.min.geojson`**,
> que cubre toda la Costa Caribe. Usa este archivo de aquí en adelante; el de Sucre
> es un subconjunto y ya no es la referencia.

**Fuente de verdad:** el archivo `DepartamentosCostaCaribe.min.geojson` que acompaña a
esta guía. No inventes ni reemplaces datos.

- **GeoJSON (foco, detalle municipal):** `DepartamentosCostaCaribe.min.geojson` — los 195
  municipios; de aquí sale Sucre con todo su detalle. Cópialo tal cual; no lo regeneres.
- **GeoJSON (contexto, contorno):** `Departamentos.dissolve.geojson` — las 7 siluetas
  departamentales (municipios disueltos por `DPTO_CNMBR`). Úsalo para dibujar los
  departamentos vecinos como contorno, sin sus divisiones internas. Es opcional: si tu
  librería puede disolver al vuelo, puedes derivarlo del archivo de municipios.
- **Cobertura:** 195 municipios · 7 departamentos — Atlántico (23), Bolívar (46),
  Cesar (25), Córdoba (30), La Guajira (15), Magdalena (30), Sucre (26).
- **Guía completa:** `MapaSucre_Referencia.md` (junto a este archivo). La metodología de
  homologación de nombres y cruce por código DANE aplica igual a todos los municipios.
- **Origen del dato:** procesado en **QGIS** a partir de los datos geoestadísticos
  oficiales del **DANE** ([geoportal](https://geoportal.dane.gov.co/servicios/descarga-y-metadatos/datos-geoestadisticos/)).
  Por eso es la referencia confiable de contornos: úsalo tal cual, no lo sustituyas.
- **Ya viene compactado:** se simplificó la geometría (~6% de vértices) preservando las
  fronteras compartidas, se redondeó a 5 decimales y se minificó — de ~42 MB a ~1.3 MB
  para que cargue rápido en el navegador. Sigue siendo GeoJSON estándar.

---

## Modos de uso (el usuario elige uno)

Estas instrucciones aplican a cualquiera de estos modos. **Di explícitamente cuál usas.**

| Modo | Qué se dibuja | Archivo(s) |
|---|---|---|
| **1. Detalle municipal** | Los municipios individuales (nivel fino). | `DepartamentosCostaCaribe.min.geojson` |
| **2. Solo contornos departamentales** | Las 7 siluetas de departamento, sin municipios. Sucre **también** queda como un contorno más, sin foco (vista regional pareja). | `Departamentos.dissolve.geojson` |
| **3. Híbrido (recomendado para "mapa de Sucre")** | Sucre con **detalle municipal** (foco, coloreado/interactivo) **+** los otros 6 departamentos como **contorno** de contexto. | Los **dos** archivos a la vez |

- El **modo 3 (híbrido)** es el del ejemplo de referencia y el que asume el resto de esta
  guía cuando habla de "foco en Sucre": el detalle municipal sale de `...min.geojson`
  (filtrando `MPIO_CDPMP` que empieza por `70`) y el contorno de los vecinos sale de
  `Departamentos.dissolve.geojson` (las siluetas con `DPTO_CNMBR != "SUCRE"`).
- En el **modo 2**, Sucre NO se dibuja por municipios; si aun así quieres resaltarlo,
  pinta la silueta `DPTO_CNMBR == "SUCRE"` con color/borde más fuerte y las otras 6 tenues.
- Las reglas de abajo aplican en los tres modos; las que hablan de "195 municipios" o de
  "foco en Sucre" solo aplican a los modos que dibujan municipios (1 y 3).

---

## Reglas de adherencia (no las cambies)

1. **Usa el mismo `DepartamentosCostaCaribe.min.geojson`.** No lo sustituyas por otro
   dataset ni lo regeneres con otra herramienta: podría traer otros nombres de
   propiedades o menos municipios. Cópialo tal cual.

2. **Deben renderizarse 195 figuras (una por municipio).** Las geometrías son `Polygon`
   o `MultiPolygon` (algunos municipios costeros/insulares tienen varias partes). Si
   aparecen menos o más de 195, algo se filtró, duplicó o corrompió. Verifícalo siempre.

3. **Orden de coordenadas = `[longitud, latitud]`.** Es como viene el GeoJSON. Para
   capas de polígonos NO inviertas el orden. Solo si pones un marcador puntual con una
   librería que use `[lat, lng]` (Leaflet/Folium) haces el intercambio ahí.

4. **CRS = WGS84 (CRS84 / EPSG:4326). No reproyectes para dibujar.** Reproyectar "para
   arreglarlo" es el error típico que manda las figuras a otro lugar. Solo reproyecta
   (EPSG:9377 / UTM) si vas a **medir** áreas o distancias, nunca para el render.

5. **Respeta las propiedades:** `MPIO_CDPMP` (código DANE, texto de 5 dígitos),
   `MPIO_CNMBR` (nombre del municipio) y `DPTO_CNMBR` (nombre del departamento).
   **Une tus datos por `MPIO_CDPMP`.** No trates el código como número (perdería ceros;
   p. ej. Atlántico empieza en `08`). Los 2 primeros dígitos son el departamento
   (08 Atlántico, 13 Bolívar, 20 Cesar, 23 Córdoba, 44 La Guajira, 47 Magdalena,
   70 Sucre).

6. **No simplifiques ni "limpies" la geometría.** Ya viene simplificada de forma
   topológica; no la vuelvas a redondear, reordenar anillos ni cerrar/abrir polígonos a
   mano: deforma los contornos y abre huecos entre municipios vecinos.

7. **Encoding UTF-8.** Los nombres traen tildes y `ñ` (`CÓRDOBA`, `PIOJÓ`, `COVEÑAS`,
   `MANATÍ`). Si ves `C�RDOBA`, corrige el encoding — no el dato.

8. **Aspecto correcto.** Si proyectas a SVG a mano, escala la longitud por
   `cos(latitud_media)` para que las figuras no salgan estiradas. Con librerías de mapa
   (MapLibre/Leaflet/Folium) esto ya está resuelto: no lo toques.

9. **Encuadre centrado en Sucre (el foco).** Al entrar, encuadra sobre **Sucre**, no
   sobre toda la región: `fitBounds` al bbox de Sucre `[-75.70603, 8.27788, -74.53271, 10.14548]`
   (o centra en `lat 9.0, lon -75.10`, zoom ~8.5), con algo de `padding` para que los
   departamentos vecinos asomen alrededor como contexto. El bbox completo de la región
   es `[-76.51453, 6.99916, -71.11306, 12.45944]` (úsalo solo si quieres una vista general
   de referencia, no como vista por defecto).

10. **Estilo: foco vs. contexto.** Distingue los dos grupos por `DPTO_CNMBR == "SUCRE"`
    (o `MPIO_CDPMP` que empiece por `70`):
    - **Sucre (foco):** los 26 municipios con relleno de color/coropleta, etiquetas,
      tooltips, clic e interacción. Es el único que recibe los datos del usuario.
    - **Resto (contexto):** el **contorno departamental disuelto** (una silueta por
      departamento, sin líneas internas entre municipios), relleno neutro/tenue, sin
      interacción ni datos. Usa `Departamentos.dissolve.geojson`, o disuelve los
      municipios por `DPTO_CNMBR`. Dibújalo en una capa **por debajo** de Sucre.

---

## Verificación rápida (antes de dar por bueno el mapa)

- [ ] **Sucre es el foco:** se dibujan sus **26 municipios** resaltados/coloreados.
- [ ] Los otros 6 departamentos se ven como **silueta departamental** de contexto (una
      por departamento, sin las divisiones municipales internas), en tono tenue.
- [ ] La vista inicial está **centrada en Sucre**, con los vecinos asomando alrededor.
- [ ] La silueta de la región se ve **proporcionada** (no achatada ni estirada).
- [ ] Los nombres con tilde/`ñ` se leen bien.
- [ ] Un municipio conocido está donde debe (p. ej. **Sincelejo** `70001` en el foco;
      **Barranquilla** `08001` o **Santa Marta** `47001` como referencia).
- [ ] El join de datos (solo Sucre) es por **`MPIO_CDPMP`** y no hay figuras "sin dato"
      inesperadas.
