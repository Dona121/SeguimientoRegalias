# Mapa del Departamento de Sucre — Guía de referencia reutilizable

Documento **independiente de framework** para construir un mapa del Departamento de
Sucre (Colombia) con **datos reales**, en cualquier proyecto futuro y con cualquier
herramienta (Leaflet, Folium, GeoPandas, Plotly, Mapbox, D3, QGIS, etc.).

Todos los valores de este documento (contornos, códigos DANE, centroides, encuadre)
están **verificados contra el archivo real** `Sucre.geojson` usado en producción por
el proyecto "Seguimiento Regalías". No son aproximaciones ni placeholders: cópialos
tal cual.

Esta guía funciona en **dos modos** (ver §2): como *complemento* de un proyecto que
ya existe, o como *arranque desde cero* con un mapa de muestra listo para correr. En
ambos casos el mapa resultante debe ser **interactivo, capaz de cargar y procesar un
archivo de datos del usuario, responsive y escalable** (ver §7).

> **Stack de referencia elegido: React (Vite) + MapLibre GL JS**, en una sola página
> (SPA). Es la opción recomendada por defecto para proyectos nuevos y la que se
> detalla en **§10.1**. Los datos y las reglas de este documento son agnósticos, así
> que las **alternativas** (Streamlit, Folium, GeoPandas, QGIS…) siguen documentadas en
> §10.2+ por si tu contexto lo exige.

---

## 1. Cómo usar este documento

1. Identifica tu escenario (§2): ¿ya tienes un proyecto o partes de cero?
2. Copia el archivo `Sucre.geojson` a tu proyecto (ver §3).
3. Usa el **encuadre recomendado** (§4) para centrar el mapa.
4. Usa la **tabla maestra de municipios** (§5) para marcadores, *joins* o *choropleth*.
5. Antes de cruzar los datos del usuario con el mapa, aplica el **protocolo de
   homologación de nombres** (§6). **Si un nombre no se puede homologar con
   confianza, pregúntale al usuario — no adivines.**
6. Garantiza los **requisitos transversales** (§7): interactividad, carga de archivo,
   responsive y escalabilidad.
7. Sigue la ruta de tu escenario: **§8 (integración)** o **§9 (muestra desde cero)**.
8. Apóyate en las **recetas por herramienta** (§10) y revisa el **checklist de
   errores** (§11).

---

## 2. Dos escenarios de adopción

### Escenario A — Ya existe un proyecto (esta guía es un *complemento*)

La persona ya construyó algo (una app, un dashboard, un backend). Aquí **no se
reemplaza nada**: estas instrucciones se integran para **potenciar** lo existente.

- Respeta el framework, el diseño y las convenciones que ya haya.
- Aporta únicamente lo que falte: el `Sucre.geojson`, la tabla de códigos/centroides,
  la capa de mapa y la lógica de homologación de nombres.
- Encaja el mapa como un módulo/componente más, reutilizando los estilos y el sistema
  de estado que el proyecto ya tenga.
- Ruta detallada en **§8**.

### Escenario B — No existe nada aún (arrancar con una *muestra genérica*)

La persona parte de cero. Entrega un **proyecto de muestra funcional** que dibuja el
mapa de Sucre con los datos del `geojson`, para que **sepa desde el inicio qué
esperar** del resultado: cómo se ve, cómo se interactúa y cómo se cargan datos.

- **Antes de construir, pregunta el stack** — no asumas uno por defecto. Ofrece las
  **dos opciones** y decide con el usuario **según funcionalidades y diseño**:
  **React (Vite) + MapLibre** (máximo control de diseño, interactividad y escala;
  requiere JS/React) vs. **Streamlit + pydeck** (rápido, Python-native, carga de datos
  inmejorable; diseño más acotado). Ver el cuadro comparativo en §10.
- La muestra ya trae los 26 municipios, es interactiva, acepta un archivo del usuario,
  es responsive, usa **tema blanco** y arranca mostrando el mapa **completo y coloreado
  por subregión** (ver §9 para el proyecto completo, copiable).
- A partir de esa base, la persona reemplaza los datos de ejemplo por los suyos y
  ajusta el diseño.
- Ruta detallada y código completo en **§9**.

> **Regla común a A y B:** los nombres de municipios que traiga el usuario casi nunca
> vienen exactamente como el DANE. **Siempre** pasa por el protocolo de homologación
> (§6) y, ante la duda, **pregunta** antes de asignar.

---

## 3. El archivo fuente: `Sucre.geojson`

- **Ubicación en este proyecto:** `regalias/Sucre.geojson` (vive junto a `mapa.py`,
  que lo carga con `os.path.dirname(__file__)`).
- **Tamaño:** ~178 KB (geometría DANE simplificada; suficientemente ligera para
  cargarla completa en el navegador).
- **Formato:** GeoJSON `FeatureCollection` con **26 features**, una por municipio.
- **Tipo de geometría:** todas `Polygon` (contornos municipales).
- **CRS declarado:** `urn:ogc:def:crs:EPSG::4686` (**MAGNA-SIRGAS**, sistema oficial
  de Colombia). Es un CRS **geográfico en grados lat/lon**; para visualización web
  equivale a **WGS84 / EPSG:4326** — la práctica totalidad de librerías lo dibujan
  correctamente sin reproyectar. Solo necesitas reproyectar si vas a hacer cálculos
  métricos (áreas, distancias en metros): en ese caso usa una proyección en metros,
  p. ej. EPSG:9377 (CTM12) o una UTM local.

### Propiedades de cada feature

| Propiedad     | Ejemplo       | Descripción                                              |
|---------------|---------------|---------------------------------------------------------|
| `MPIO_CNMBR`  | `SINCELEJO`   | Nombre oficial DANE, **en mayúsculas y con tildes**.     |
| `MPIO_CDPMP`  | `70001`       | Código DANE de 5 dígitos. El prefijo `70` = Sucre.       |

```json
{
  "type": "Feature",
  "properties": { "MPIO_CNMBR": "SINCELEJO", "MPIO_CDPMP": "70001" },
  "geometry": { "type": "Polygon", "coordinates": [ [ [-75.5131, 9.4056], ... ] ] }
}
```

> **Orden de coordenadas:** GeoJSON usa **`[longitud, latitud]`** (X, Y). Muchas
> librerías (Leaflet incluido) esperan **`[latitud, longitud]`** al poner marcadores.

---

## 4. Encuadre del mapa (valores reales)

| Parámetro                 | Valor                                        |
|---------------------------|----------------------------------------------|
| Longitud (bbox)           | `-75.70603` a `-74.53271`                     |
| Latitud (bbox)            | `8.27788` a `10.14548`                        |
| Centro geográfico (bbox)  | lat `9.21168`, lon `-75.11937`                |
| **Encuadre práctico**     | centro `lat 9.0, lon -75.10` · **zoom 9**     |

- Bounding box `[minLon, minLat, maxLon, maxLat]`:
  `[-75.70603, 8.27788, -74.53271, 10.14548]`.
- Alternativa robusta: deja que la librería ajuste con `fitBounds(bbox)`.

---

## 5. Tabla maestra de los 26 municipios

Fuente de verdad para marcadores, *joins* y *choropleths*. El **centroide** es la
cabecera municipal (lat, lng), ideal para un marcador puntual por municipio.

| Código DANE | Nombre oficial (DANE)     | Lat (cabecera) | Lng (cabecera) |
|-------------|---------------------------|----------------|----------------|
| 70001 | SINCELEJO                       |  9.3047 | -75.3978 |
| 70110 | BUENAVISTA                      |  9.3197 | -74.9706 |
| 70124 | CAIMITO                         |  8.7892 | -75.1144 |
| 70204 | COLOSÓ                          |  9.4961 | -75.3531 |
| 70215 | COROZAL                         |  9.3211 | -75.2939 |
| 70221 | COVEÑAS                         |  9.4011 | -75.6800 |
| 70230 | CHALÁN                          |  9.5450 | -75.3147 |
| 70233 | EL ROBLE                        |  9.1014 | -75.1003 |
| 70235 | GALERAS                         |  9.1639 | -75.0497 |
| 70265 | GUARANDA                        |  8.4675 | -74.5378 |
| 70400 | LA UNIÓN                        |  8.8500 | -75.2833 |
| 70418 | LOS PALMITOS                    |  9.3792 | -75.2675 |
| 70429 | MAJAGUAL                        |  8.5419 | -74.6286 |
| 70473 | MORROA                          |  9.3406 | -75.3097 |
| 70508 | OVEJAS                          |  9.5247 | -75.2294 |
| 70523 | PALMITO                         |  9.3372 | -75.5358 |
| 70670 | SAMPUÉS                         |  9.1814 | -75.3814 |
| 70678 | SAN BENITO ABAD                 |  8.9311 | -75.0339 |
| 70702 | SAN JUAN DE BETULIA             |  9.2667 | -75.2417 |
| 70708 | SAN MARCOS                      |  8.6597 | -75.1330 |
| 70713 | SAN ONOFRE                      |  9.7361 | -75.5283 |
| 70717 | SAN PEDRO                       |  9.3956 | -75.0567 |
| 70742 | SAN LUIS DE SINCÉ               |  9.2433 | -75.1450 |
| 70771 | SUCRE                           |  8.8094 | -74.7211 |
| 70820 | SANTIAGO DE TOLÚ                |  9.5236 | -75.5828 |
| 70823 | SAN JOSÉ DE TOLUVIEJO           |  9.4500 | -75.4400 |

> Los códigos y nombres coinciden **1:1** con `MPIO_CDPMP` / `MPIO_CNMBR` del
> `Sucre.geojson`. Los centroides provienen del visor en producción.

### Subregiones (clasificación fisiográfica oficial · para agrupar/colorear por zona)

Los 26 municipios se agrupan en **5 subregiones**. Esta es la clasificación
fisiográfica oficial (confirmada con el cliente). Color sugerido para cada una entre
paréntesis (legible sobre fondo blanco):

- **Golfo de Morrosquillo** (5 · `#0ea5a4`): Coveñas, Palmito, Santiago de Tolú,
  San José de Toluviejo, San Onofre.
- **Montes de María** (5 · `#5a9e2f`): Sincelejo, Morroa, Ovejas, Chalán, Colosó.
- **Sabanas** (9 · `#e08b12`): Corozal, Los Palmitos, Sampués, San Juan de Betulia,
  Buenavista, San Luis de Sincé, San Pedro, Galeras, El Roble.
- **San Jorge** (4 · `#2f6bd6`): San Marcos, San Benito Abad, Caimito, La Unión.
- **La Mojana** (3 · `#8a5cf0`): Sucre, Majagual, Guaranda.

> **Regla de creación (obligatoria):** al construir el mapa, **muestra esta lista al
> usuario y pregúntale si quiere cambiar alguna subregión** antes de colorear. Las
> asignaciones de Sincelejo, Morroa y Los Palmitos varían entre fuentes, así que no las
> des por sentadas. Cuando el usuario confirme, usa esa clasificación.

> **Presentación por defecto:** al entrar, el mapa se muestra **completo, con tema
> blanco y coloreado por subregión**; la vista de datos (choropleth por valor) es un
> segundo modo.

---

## 6. Protocolo de homologación de nombres

Los nombres que trae el usuario **casi nunca** llegan como el DANE: vienen en
minúsculas, sin tildes, con la forma corta/histórica, con espacios de más o con
pequeños errores de tipeo. Este protocolo los reconcilia de forma **segura**.

### 6.1 Orden de intentos (de más a menos confiable)

Para cada municipio de los datos del usuario, intenta en cascada y **detente en el
primer acierto**:

1. **Por código DANE** — si los datos traen `MPIO_CDPMP` (o cualquier código de 5
   dígitos), une por ahí. Es el método más seguro; sáltate el resto.
2. **Nombre normalizado exacto** — normaliza (§6.2) ambos lados y compara igualdad.
3. **Alias conocido** — aplica la tabla de aliases (§6.3).
4. **Coincidencia aproximada (*fuzzy*, opcional)** — solo si sigue sin match: compara
   contra los 26 nombres normalizados con una métrica de similitud (Levenshtein /
   `difflib`). Acepta **únicamente** si la similitud es muy alta (**≥ 0.90**) y el
   segundo candidato queda claramente por debajo. En cualquier otro caso, NO asignes.
5. **Sin resolver → preguntar** (§6.4).

### 6.2 Normalización (misma que usa producción)

`trim` + colapsar espacios + MAYÚSCULAS + quitar tildes/diacríticos + quitar puntos.

```python
import unicodedata, re
def norm_municipio(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFKD", str(s).strip())
    s = "".join(c for c in s if not unicodedata.combining(c))  # sin tildes
    s = re.sub(r"\s+", " ", s).upper().strip(" .")
    return ALIAS.get(s, s)
```

### 6.3 Aliases: nombres coloquiales → nombre DANE

| Lo que puede venir en tus datos | Nombre DANE normalizado |
|---------------------------------|-------------------------|
| `SINCE`, `SAN LUIS SINCE`       | `SAN LUIS DE SINCE`     |
| `TOLU`                          | `SANTIAGO DE TOLU`      |
| `TOLU VIEJO`, `TOLUVIEJO`       | `SAN JOSE DE TOLUVIEJO` |
| `SAN ANTONIO DE PALMITO`        | `PALMITO`               |

```python
ALIAS = {
    "SINCE": "SAN LUIS DE SINCE",
    "SAN LUIS SINCE": "SAN LUIS DE SINCE",
    "TOLU": "SANTIAGO DE TOLU",
    "TOLU VIEJO": "SAN JOSE DE TOLUVIEJO",
    "TOLUVIEJO": "SAN JOSE DE TOLUVIEJO",
    "SAN ANTONIO DE PALMITO": "PALMITO",
}
```

### 6.4 Regla de oro: si no estás seguro, PREGUNTA

**Nunca asignes un municipio "a ojo".** Una asignación equivocada mueve datos al
lugar incorrecto del mapa y es difícil de detectar después. Por eso:

- Si un nombre **no resuelve** por código, exacto ni alias, y el *fuzzy* **no supera
  el umbral** (o hay empate entre candidatos), **no lo asignes**.
- Reúne todos los nombres sin resolver y **muéstraselos al usuario**, junto con el/los
  candidato(s) más parecido(s), y pídele que confirme o corrija. Ejemplo del mensaje:

  > No pude ubicar con certeza estos municipios de tu archivo:
  > - `"S. Onofre"` → ¿quisiste decir **SAN ONOFRE** (70713)?
  > - `"Tolu Viejo"` → ¿**SAN JOSÉ DE TOLUVIEJO** (70823)?
  > - `"Betulia"` → no encontré coincidencia clara. ¿A qué municipio corresponde?
  >
  > Confírmame cada uno y actualizo el mapa.

- Cuando el usuario confirme, **guarda esa equivalencia** (amplía la tabla de aliases)
  para no volver a preguntar por el mismo caso.

### 6.5 Cobertura departamental

Un registro con alcance a todo el departamento suele usar el centinela
**`TODO EL DEPARTAMENTO DE SUCRE`**. Al procesarlo, **expándelo a los 26 municipios**.

---

## 7. Requisitos transversales (interactivo · carga de archivo · responsive · escalable)

Aplican **en ambos escenarios**. El mapa debe cumplir los cuatro:

### 7.1 Interactivo

- Zoom y desplazamiento (*pan*).
- Al pasar el cursor / tocar un municipio: resaltarlo y mostrar su nombre + valor.
- Al hacer clic: abrir un popup / panel con el detalle (nombre, código, métricas).
- Filtros y/o buscador por municipio o subregión.
- Leyenda visible que explique la escala de color.

### 7.2 Carga y procesamiento de un archivo del usuario

- Aceptar **CSV** y/o **Excel (.xlsx)** subido por el usuario.
- Detectar de forma flexible la **columna de municipio** (por nombre `MUNICIPIO`,
  `MPIO`, etc.) o la **columna de código** DANE, y la **columna de valor** a graficar.
- Pasar cada fila por el **protocolo de homologación (§6)**.
- Reportar al usuario: cuántas filas se ubicaron, cuántas quedaron **sin resolver**
  (y preguntar por ellas, §6.4), y refrescar el mapa con los datos cargados.
- Recomendado: unir **por código DANE** siempre que exista en el archivo.

### 7.3 Responsive

- Layout fluido (flexbox/grid); el mapa ocupa el alto disponible (`100dvh` o
  contenedor con altura definida) y ancho `100%`.
- En pantallas angostas: los paneles (filtros/leyenda) se colapsan, se apilan o pasan
  a un *drawer*; nada debe provocar *scroll* horizontal.
- Unidades relativas, `max-width:100%` en imágenes/paneles, y puntos de quiebre
  (`@media`) para móvil/tablet/escritorio.

### 7.4 Escalable

- **Separa datos de geometría.** El `geojson` es el mapa base; los valores viven en
  una tabla aparte y se unen por **código DANE** (no por nombre). Así puedes cambiar o
  crecer los datos sin tocar la geometría.
- **Muchos puntos** → usa *clustering* (p. ej. Leaflet.markercluster) o agrega por
  municipio antes de dibujar.
- **Geometrías pesadas** → simplifica (TopoJSON o `mapshaper`) y/o sirve **teselas
  vectoriales** si algún día pasas a nivel nacional.
- **Parametriza el departamento.** El mismo patrón sirve para otros departamentos DANE
  cambiando el `geojson` y el prefijo del código (Sucre = `70`); deja el código
  agnóstico al valor concreto.
- **Cachea** la lectura del `geojson` (memoria/HTTP) y evita recalcular en cada
  interacción.
- **Componentiza:** aísla "capa de datos", "capa de mapa" y "capa de UI" para poder
  reemplazar cualquiera sin reescribir el resto.

---

## 8. Escenario A — Integrar en un proyecto existente (complemento)

Objetivo: **sumar** el mapa sin romper lo que ya funciona.

1. **Ubica el archivo.** Copia `Sucre.geojson` a una carpeta de assets del proyecto
   (p. ej. `static/`, `assets/`, `public/`, o junto al módulo del mapa). Cárgalo con
   una ruta relativa robusta.
2. **Reutiliza lo que ya exista.** Si el proyecto ya tiene sistema de estilos,
   componentes de UI, manejo de estado o carga de archivos, **engánchate a eso** en
   lugar de introducir dependencias nuevas.
3. **Elige la librería según el stack actual** (§10). Si ya usan React, usa
   `react-leaflet`; si es Streamlit, replica el patrón de `components.html` + Leaflet;
   si es Python/servidor, Folium o Plotly.
4. **Inserta la capa de datos** (tabla de §5) y la **homologación** (§6) como un módulo
   utilitario independiente y testeable.
5. **Cumple los requisitos transversales (§7)** con los medios del proyecto.
6. **Verifica la integración:** los 26 municipios se dibujan, la carga de archivo del
   usuario ubica las filas y los nombres no homologables se le consultan al usuario.

> Referencia interna: en este repositorio el patrón vive en `regalias/mapa.py`
> (Leaflet embebido en Streamlit, tema oscuro, marcadores + choropleth por conteo de
> proyectos). Sirve de ejemplo de integración avanzada.

---

## 9. Escenario B — Proyecto de muestra desde cero

Objetivo: entregar algo **funcional en un solo archivo** para que el usuario vea de
inmediato qué esperar. Es interactivo, acepta un CSV, homologa nombres y es
responsive. Luego se puede migrar a un framework mayor.

### 9.1 Estructura mínima

```
mapa-sucre/
├── index.html          # la muestra completa (abajo)
└── Sucre.geojson       # cópialo desde regalias/Sucre.geojson
```

Ábrelo con un servidor estático (por `fetch` del geojson):
`python -m http.server` y visita `http://localhost:8000`.

### 9.2 `index.html` (copiar/pegar)

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Mapa de Sucre — Muestra</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root { --bg:#0b1220; --panel:#0f172a; --line:#1e293b; --txt:#e5e7eb; --accent:#2563eb; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; font-family: system-ui, sans-serif;
               background:var(--bg); color:var(--txt); }
  .app { display:flex; height:100dvh; }
  .side { width:300px; min-width:260px; background:var(--panel);
          border-right:1px solid var(--line); padding:14px; overflow-y:auto; }
  .side h1 { font-size:1rem; margin:0 0 4px; }
  .side p  { font-size:.75rem; color:#94a3b8; margin:.3rem 0; }
  .side input[type=file] { width:100%; font-size:.75rem; margin:.4rem 0; }
  .side select { width:100%; padding:6px; margin:.2rem 0 .6rem; background:var(--bg);
                 color:var(--txt); border:1px solid var(--line); border-radius:6px; }
  #status { font-size:.72rem; line-height:1.5; white-space:pre-wrap; }
  #status .warn { color:#fbbf24; }
  .map-wrap { flex:1; position:relative; }
  #map { position:absolute; inset:0; }
  .legend { background:rgba(15,23,42,.9); padding:8px 10px; border-radius:8px;
            border:1px solid var(--line); font-size:.72rem; line-height:1.6; }
  .legend i { display:inline-block; width:12px; height:12px; margin-right:6px;
              border-radius:2px; vertical-align:-1px; }
  /* Responsive: en móvil el panel pasa arriba y se apila */
  @media (max-width: 720px) {
    .app { flex-direction:column; }
    .side { width:100%; min-width:0; max-height:42vh; border-right:none;
            border-bottom:1px solid var(--line); }
  }
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <h1>Mapa de Sucre</h1>
    <p>Muestra genérica con los 26 municipios. Sube un CSV para colorear el mapa.</p>
    <label>Archivo CSV
      <input id="file" type="file" accept=".csv,text/csv"/>
    </label>
    <p>Columnas esperadas: una de <b>municipio</b> o <b>código DANE</b>, y una de
       <b>valor</b> (numérico).</p>
    <label>Columna municipio/código <select id="colMun"></select></label>
    <label>Columna valor <select id="colVal"></select></label>
    <div id="status">Cargando geometría…</div>
  </aside>
  <div class="map-wrap"><div id="map"></div></div>
</div>

<script>
// ── Datos de referencia (§5): código DANE -> nombre normalizado ──────────────
const MUN = {
 "70001":"SINCELEJO","70110":"BUENAVISTA","70124":"CAIMITO","70204":"COLOSO",
 "70215":"COROZAL","70221":"COVENAS","70230":"CHALAN","70233":"EL ROBLE",
 "70235":"GALERAS","70265":"GUARANDA","70400":"LA UNION","70418":"LOS PALMITOS",
 "70429":"MAJAGUAL","70473":"MORROA","70508":"OVEJAS","70523":"PALMITO",
 "70670":"SAMPUES","70678":"SAN BENITO ABAD","70702":"SAN JUAN DE BETULIA",
 "70708":"SAN MARCOS","70713":"SAN ONOFRE","70717":"SAN PEDRO",
 "70742":"SAN LUIS DE SINCE","70771":"SUCRE","70820":"SANTIAGO DE TOLU",
 "70823":"SAN JOSE DE TOLUVIEJO"
};
const ALIAS = {
 "SINCE":"SAN LUIS DE SINCE","SAN LUIS SINCE":"SAN LUIS DE SINCE",
 "TOLU":"SANTIAGO DE TOLU","TOLU VIEJO":"SAN JOSE DE TOLUVIEJO",
 "TOLUVIEJO":"SAN JOSE DE TOLUVIEJO","SAN ANTONIO DE PALMITO":"PALMITO"
};
const NAME2CODE = Object.fromEntries(Object.entries(MUN).map(([c,n]) => [n, c]));

// ── Homologación (§6) ────────────────────────────────────────────────────────
function norm(s){
  if(!s) return "";
  s = s.toString().normalize("NFKD").replace(/[̀-ͯ]/g,""); // sin tildes
  return s.replace(/\s+/g," ").trim().toUpperCase().replace(/^[.\s]+|[.\s]+$/g,"");
}
function lev(a,b){ // distancia de edición para el fuzzy opcional
  const m=a.length,n=b.length,d=Array.from({length:m+1},(_,i)=>[i,...Array(n).fill(0)]);
  for(let j=0;j<=n;j++) d[0][j]=j;
  for(let i=1;i<=m;i++) for(let j=1;j<=n;j++)
    d[i][j]=Math.min(d[i-1][j]+1,d[i][j-1]+1,d[i-1][j-1]+(a[i-1]===b[j-1]?0:1));
  return d[m][n];
}
function homologar(raw){ // -> {code} | {ask:[candidatos]} | {none:true}
  const t = norm(raw);
  if(/^70\d{3}$/.test(t) && MUN[t]) return {code:t};        // 1. por código
  const dane = ALIAS[t] || t;
  if(NAME2CODE[dane]) return {code: NAME2CODE[dane]};       // 2-3. exacto/alias
  const cands = Object.keys(NAME2CODE)                       // 4. fuzzy
     .map(n => ({n, sim: 1 - lev(dane,n)/Math.max(dane.length,n.length)}))
     .sort((a,b)=>b.sim-a.sim);
  if(cands[0] && cands[0].sim>=0.90 && (!cands[1]||cands[0].sim-cands[1].sim>0.06))
     return {code: NAME2CODE[cands[0].n]};
  if(cands[0] && cands[0].sim>=0.6) return {ask: cands.slice(0,2)};
  return {none:true};                                        // 5. sin resolver
}

// ── CSV simple (sin dependencias). Para .xlsx añade SheetJS o procesa aparte ──
function parseCSV(text){
  const rows = text.trim().split(/\r?\n/).map(r=>r.split(/[,;]/).map(c=>c.trim()));
  const head = rows.shift();
  return {head, rows};
}

// ── Escala de color (choropleth) ─────────────────────────────────────────────
function color(v,min,max){
  if(v==null) return "#334155";
  const t = max>min ? (v-min)/(max-min) : 0.5;
  const stops = ["#dbeafe","#93c5fd","#3b82f6","#1d4ed8","#1e3a8a"];
  return stops[Math.min(stops.length-1, Math.floor(t*stops.length))];
}

// ── Mapa ─────────────────────────────────────────────────────────────────────
const map = L.map("map").setView([9.0,-75.10], 9);   // encuadre real (§4)
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  {attribution:"© OpenStreetMap"}).addTo(map);
const statusEl = document.getElementById("status");
let layer, valores = {};   // valores: code -> número

function pinta(){
  const vals = Object.values(valores);
  const min = Math.min(...vals), max = Math.max(...vals);
  layer.setStyle(f=>{
    const v = valores[f.properties.MPIO_CDPMP];
    return {color:"#0b1220", weight:1,
            fillColor: color(v==null?null:v,min,max), fillOpacity:.85};
  });
}

fetch("Sucre.geojson").then(r=>r.json()).then(gj=>{
  layer = L.geoJSON(gj, {
    style:{color:"#0b1220",weight:1,fillColor:"#334155",fillOpacity:.7},
    onEachFeature:(f,ly)=>{
      const p=f.properties;
      ly.on("mouseover",()=>ly.setStyle({weight:2,color:"#60a5fa"}));
      ly.on("mouseout", ()=>ly.setStyle({weight:1,color:"#0b1220"}));
      ly.bindPopup(()=>{
        const v = valores[p.MPIO_CDPMP];
        return `<b>${p.MPIO_CNMBR}</b> (${p.MPIO_CDPMP})<br>`+
               (v==null? "Sin dato" : `Valor: <b>${v}</b>`);
      });
    }
  }).addTo(map);
  map.fitBounds(layer.getBounds());
  const leg = L.control({position:"bottomright"});
  leg.onAdd = ()=>{ const d=L.DomUtil.create("div","legend");
    d.innerHTML = "<b>Escala</b><br><i style='background:#dbeafe'></i>bajo<br>"+
                  "<i style='background:#1e3a8a'></i>alto<br>"+
                  "<i style='background:#334155'></i>sin dato"; return d; };
  leg.addTo(map);
  statusEl.textContent = "Geometría lista (26 municipios). Sube un CSV.";
});

// ── Carga de archivo del usuario (§7.2) ──────────────────────────────────────
const colMun = document.getElementById("colMun"), colVal = document.getElementById("colVal");
let parsed = null;
document.getElementById("file").addEventListener("change", ev=>{
  const file = ev.target.files[0]; if(!file) return;
  const reader = new FileReader();
  reader.onload = e=>{
    parsed = parseCSV(e.target.result);
    colMun.innerHTML = colVal.innerHTML =
      parsed.head.map((h,i)=>`<option value="${i}">${h}</option>`).join("");
    // heurística: preselecciona columnas por nombre
    parsed.head.forEach((h,i)=>{
      const H = norm(h);
      if(/MUNICIP|MPIO|CODIGO|DANE/.test(H)) colMun.value=i;
      if(/VALOR|TOTAL|MONTO|CANT|AVANCE/.test(H)) colVal.value=i;
    });
    aplicar();
  };
  reader.readAsText(file, "utf-8");
});
[colMun,colVal].forEach(s=>s.addEventListener("change", aplicar));

function aplicar(){
  if(!parsed || !layer) return;
  valores = {}; const dudas = [], sin = [];
  const iM = +colMun.value, iV = +colVal.value;
  for(const row of parsed.rows){
    if(!row[iM]) continue;
    const r = homologar(row[iM]);
    const val = parseFloat((row[iV]||"").replace(",", "."));
    if(r.code){ if(!isNaN(val)) valores[r.code] = val; }
    else if(r.ask){ dudas.push([row[iM], r.ask.map(a=>a.n).join(" / ")]); }
    else { sin.push(row[iM]); }
  }
  pinta();
  let msg = `Ubicados: ${Object.keys(valores).length}/26 municipios.`;
  if(dudas.length) msg += `\n\n⚠ Revisa (no homologados con certeza):\n`+
      dudas.map(([o,c])=>`  • "${o}"  → ¿${c}?`).join("\n");
  if(sin.length) msg += `\n\n⚠ Sin coincidencia: ${sin.join(", ")}`;
  if(dudas.length||sin.length) msg += `\n\nConfírmame estos casos y ajusto el mapa.`;
  statusEl.innerHTML = msg.replace(/⚠[^\n]*/g, m=>`<span class="warn">${m}</span>`);
}
</script>
</body>
</html>
```

**Qué demuestra esta muestra frente a los requisitos (§7):**

- *Interactivo:* zoom/pan, *hover* que resalta, popup por municipio, leyenda.
- *Carga de archivo:* lee un CSV, detecta columnas, homologa nombres/códigos y pinta.
- *Responsive:* layout flexible con panel que se apila en móvil (`@media`).
- *Escalable:* datos y geometría separados, unión por código DANE, color por escala;
  para crecer solo cambias los datos o el `geojson`.
- *Homologación con pregunta:* los nombres dudosos o sin match se **listan para que el
  usuario los confirme** (no se asignan a ciegas).

> Notas: para leer **Excel (.xlsx)** en el navegador añade SheetJS (`xlsx`) o procesa
> el archivo en el backend. El *fuzzy* de la muestra es un extra de conveniencia: ante
> la duda, la muestra **pregunta** en vez de adivinar (§6.4).

---

## 10. Stack recomendado y recetas

Todas parten del **mismo** `Sucre.geojson` y de la **misma** tabla de §5. La **§10.1
es el stack de referencia**; el resto son alternativas.

### 10.1 ★ Stack de referencia — React (Vite) + MapLibre GL JS  ·  SPA de una sola página

Elegido por su equilibrio en los criterios clave: **interactividad, diseño, carga de
archivos, integración y soporte de librerías**, todo dentro de una **página única**.

**Dependencias**

| Rol | Paquete | Nota |
|---|---|---|
| App / bundler | `react`, `react-dom`, `vite` | SPA moderna, dev server con HMR. |
| Motor de mapa | `maplibre-gl` + `react-map-gl` | Vector, zoom fluido, *data-driven styling*. Open-source, **sin token**. |
| Geoprocesamiento | `@turf/turf` | Centroides, uniones, buffers en el cliente. |
| Carga de archivos | `papaparse` (CSV) + `xlsx` / SheetJS (Excel) | Parseo en el navegador. |
| Diseño / UI | `tailwindcss` (+ Radix/shadcn opcional) | Responsive real, estética propia (no plantilla). |

```bash
npm create vite@latest mapa-sucre -- --template react-ts
cd mapa-sucre
npm i maplibre-gl react-map-gl @turf/turf papaparse xlsx
npm i -D tailwindcss   # + configuración estándar de Tailwind
# Copia Sucre.geojson (de docs/) a  public/Sucre.geojson
```

**Estructura sugerida** (separa datos, mapa y UI para que sea escalable — §7.4):

```
mapa-sucre/
├── public/Sucre.geojson          # geometría (cópiala desde docs/)
├── src/
│   ├── data/municipios.ts        # tabla §5: code→{nombre,lat,lng} + ALIAS
│   ├── lib/homologar.ts          # protocolo §6 (norm + alias + fuzzy + "preguntar")
│   ├── lib/parseArchivo.ts       # CSV/Excel → filas → homologación
│   ├── components/MapaSucre.tsx   # react-map-gl: Source geojson + capas fill/line
│   ├── components/PanelDatos.tsx  # uploader + selección de columnas + avisos
│   ├── components/Leyenda.tsx
│   └── App.tsx                    # una sola página: <PanelDatos/> + <MapaSucre/>
└── index.html
```

**Componente de mapa (esqueleto `react-map-gl` + MapLibre):**

```tsx
import Map, { Source, Layer } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

// Estilo base sin token: teselas raster de OSM dentro de un style JSON de MapLibre
const STYLE = {
  version: 8,
  sources: { osm: { type: "raster",
    tiles: ["https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256 } },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

export function MapaSucre({ geojson, valores }) {
  // valores: Record<string, number>  (código DANE → valor); se inyecta al feature-state
  return (
    <Map initialViewState={{ longitude: -75.10, latitude: 9.0, zoom: 8 }}  // §4
         mapStyle={STYLE} style={{ position: "absolute", inset: 0 }}
         interactiveLayerIds={["mun-fill"]}
         onClick={e => {/* popup con properties.MPIO_CNMBR / MPIO_CDPMP */}}>
      <Source id="mun" type="geojson" data={geojson} promoteId="MPIO_CDPMP">
        {/* Choropleth data-driven: el color se resuelve por feature-state 'valor' */}
        <Layer id="mun-fill" type="fill" paint={{
          "fill-color": ["interpolate", ["linear"], ["coalesce", ["feature-state","valor"], 0],
            0,"#334155", 1,"#dbeafe", 50,"#3b82f6", 100,"#1e3a8a"],
          "fill-opacity": 0.85 }} />
        <Layer id="mun-line" type="line" paint={{ "line-color":"#0b1220","line-width":1 }} />
      </Source>
    </Map>
  );
}
```

**Cómo cubre los 5 criterios:**

- **Interactividad:** `hover`/`click` por capa, popups, `feature-state` para resaltar
  y colorear sin recrear la fuente.
- **Diseño:** Tailwind + estilo MapLibre propio; control total, responsive por defecto.
- **Carga de archivos:** `PapaParse`/SheetJS en `parseArchivo.ts` → homologación §6 →
  se inyecta a `valores` y el mapa reacciona.
- **Integración:** ecosistema React (estado, routing, tests). Si el geoprocesamiento
  crece, añade **FastAPI + GeoPandas** como backend y el front solo renderiza.
- **Soporte de librerías:** MapLibre + deck.gl + Turf son de primer nivel.
- **Una sola página:** `App.tsx` monta panel + mapa; nunca hay navegación entre vistas.

> **Unión de datos:** usa `promoteId: "MPIO_CDPMP"` en el `Source` y actualiza con
> `map.setFeatureState({source:"mun", id: code}, {valor})`. Une **siempre por código
> DANE** (§6.1); homologa antes con §6 y, si un nombre no resuelve, **pregunta** (§6.4).

### 10.2 Streamlit (alternativa Python-native)

Como en `regalias/mapa.py`: Leaflet embebido vía `st.components.v1.html`, o
`folium` + `streamlit-folium` / `pydeck`. Ventaja: `st.file_uploader` + Polars/Pandas/
GeoPandas nativo. Cachea el geojson con `@st.cache_data`.

### 10.3 Python + Folium (export a HTML estático)

```python
import folium, json
m = folium.Map(location=[9.0, -75.10], zoom_start=9, tiles="OpenStreetMap")
with open("Sucre.geojson", encoding="utf-8") as f: gj = json.load(f)
folium.GeoJson(gj, tooltip=folium.GeoJsonTooltip(fields=["MPIO_CNMBR","MPIO_CDPMP"]),
    style_function=lambda _: {"color":"#2563eb","weight":1,"fillOpacity":0.15}).add_to(m)
m.save("mapa_sucre.html")
```

### 10.4 Python + GeoPandas / Plotly (análisis / choropleth rápido)

```python
import geopandas as gpd, plotly.express as px
gdf = gpd.read_file("Sucre.geojson").to_crs(epsg=4326)   # 26 municipios
fig = px.choropleth_map(datos, geojson=gdf.__geo_interface__,
    locations="cod", featureidkey="properties.MPIO_CDPMP", color="valor",
    center={"lat":9.21,"lon":-75.12}, zoom=6.5, map_style="carto-positron")
fig.show()
# Para áreas/distancias en metros: gdf.to_crs(epsg=9377)
```

### 10.5 Leaflet vanilla / QGIS

- **Leaflet sin framework:** ver la muestra completa del **§9** (ideal para prototipos
  o para incrustar en apps sin build). Más simple que MapLibre; más plugins listos.
- **QGIS:** `Añadir capa vectorial → Sucre.geojson`; unión de tablas por `MPIO_CDPMP`.

---

## 11. Checklist de errores comunes

- [ ] **Orden lon/lat.** GeoJSON guarda `[lon, lat]`; Leaflet/Folium ponen marcadores
      en `[lat, lng]`; Mapbox usa `[lon, lat]`.
- [ ] **Encoding UTF-8.** Hay tildes y `ñ` (`COLOSÓ`, `COVEÑAS`). Si ves `COLOS�`, el
      encoding está mal.
- [ ] **Join por nombre sin normalizar / sin homologar.** `Coloso` ≠ `COLOSÓ`. Pasa
      por §6 o une por `MPIO_CDPMP`.
- [ ] **Asignar municipios "a ojo".** Si no hay match confiable, **pregunta** (§6.4).
- [ ] **Código DANE como número.** `70001` debe tratarse como **texto** (no pierdas
      ceros a la izquierda).
- [ ] **CRS para métricas.** Para dibujar, EPSG:4686 va bien; para medir en metros,
      reproyecta (EPSG:9377 / UTM).
- [ ] **Deben ser 26 municipios.** Si aparecen menos o más, algo se filtró o duplicó.
- [ ] **Responsive.** Verifica que en móvil no haya *scroll* horizontal y que el mapa
      conserve altura utilizable.

---

## 12. Resumen de datos clave (copiar/pegar)

```
Fuente:      Sucre.geojson  (FeatureCollection, 26 Polygon)
CRS:         EPSG:4686 (MAGNA-SIRGAS ~ WGS84 para visualización)
Propiedades: MPIO_CNMBR (nombre), MPIO_CDPMP (código DANE 5 díg., prefijo 70)
BBox:        [-75.70603, 8.27788, -74.53271, 10.14548]   (minLon,minLat,maxLon,maxLat)
Centro:      lat 9.0, lon -75.10   |   zoom 9
Municipios:  26   |   Centinela dpto: "TODO EL DEPARTAMENTO DE SUCRE"
Escenarios:  A = complemento de proyecto existente · B = muestra desde cero
Requisitos:  interactivo · carga archivo usuario · responsive · escalable
Stack ref.:  React (Vite) + MapLibre GL JS — SPA de una sola página (§10.1)
             +react-map-gl +@turf/turf +papaparse +xlsx +tailwindcss
Homologar:   código DANE > nombre normalizado > alias > fuzzy≥0.90 > PREGUNTAR
```
