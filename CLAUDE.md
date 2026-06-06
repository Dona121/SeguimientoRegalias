# Proyecto: Seguimiento Regalías

App de Streamlit que visualiza el avance de proyectos de regalías del Departamento
de Sucre. Lee un Excel con 3 tablas y calcula hitos de gestión (semáforos verde/
naranja/rojo/negro) por proyecto, entidad y ejecutor. Además incluye:
visor geográfico (Mapa) y panel del Índice de Gestión de Proyectos de Regalías
(IGPR, Resolución 4574 de 2025).

Deploy en Railway. Comando: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.

---

## Stack

- **Streamlit** ≥1.39 — UI
- **Polars** ≥1.20 (con `fastexcel`) — lectura Excel + procesamiento
- **Pandas** — para `to_pandas()` en algunos render
- **OpenPyXL** — escritura del Excel de exportación
- Python 3.10+

Ver `requirements.txt`.

---

## Estructura de archivos

El proyecto está empaquetado con **uv** (`pyproject.toml` + `uv.lock`). El
ejecutable principal (`app.py`) vive en la raíz y toda la lógica está en el
paquete `regalias/`. Los módulos se importan con prefijo absoluto del paquete
(`from regalias.constants import ...`).

```
Seguimiento Regalias/
├── app.py            # Orquestador principal (~3200 líneas): sidebar, header,
│                     #   routing por vista, render de KPIs, tabs, guía.
│                     #   Imports: from regalias.<modulo> import ...
├── pyproject.toml    # Metadata + dependencias (uv). package = false (es app).
├── uv.lock           # Lockfile reproducible de uv.
├── requirements.txt  # Espejo de las deps (para Railway). Sincronizar con pyproject.
├── .python-version   # Python fijado a 3.13 (uv).
├── CLAUDE.md
└── regalias/         # Paquete con toda la lógica
    ├── __init__.py
    ├── constants.py  # Paleta de colores (C), inyección de CSS+JS global
    │                 #   (inject_css), INTERVALOS, SEMAFOROS, COLS_EVAL,
    │                 #   TABLA_ESPERADA, TABLA_DESCENTRALIZADAS, TABLA_MUNICIPIOS.
    ├── data.py       # Lectura y procesamiento: _leer_tabla_robusta (fallback
    │                 #   de estrategias), procesar(), procesar_descentralizadas_hitos(),
    │                 #   procesar_municipios(), procesar_eval_sucre(),
    │                 #   procesar_descentralizadas(), procesar_contratos(),
    │                 #   aplicar_hito_4_en_ejecucion(), validar_archivo(),
    │                 #   _cargar_desde_github().
    ├── data_igpr.py  # Descarga y procesa los 5 Excel del IGPR (DNP). Aplica
    │                 #   limpieza de encabezados, filtra Sucre, calcula flags
    │                 #   de situación 2026 y agrega resumen por entidad/periodo
    │                 #   con el descuento de −10 puntos.
    ├── igpr.py       # Vista del IGPR: KPIs globales, evolución por trimestre,
    │                 #   matriz Entidad × Periodo, detalle por trimestre, detalle
    │                 #   por entidad, metodología (Res. 4574).
    ├── mapa.py       # Visor geográfico (Leaflet) de proyectos por municipio.
    │                 #   Carga el GeoJSON con os.path.dirname(__file__) → el
    │                 #   Sucre.geojson DEBE estar junto a este archivo.
    ├── export.py     # Generación del Excel global consolidado (9 hojas).
    ├── render.py     # Helpers de presentación: badge_html, _pill, _fmt_date,
    │                 #   _dias_tooltip, _estado_tooltip_html, eval_color,
    │                 #   _clasificar_promedio, _contratos_panel, HITO_KEY_MAP, etc.
    └── Sucre.geojson # Geometrías de los municipios para el visor de mapa.
```

---

## Fuentes de datos

El archivo Excel principal tiene **3 tablas/hojas**:

| Tabla / Hoja | Vista en la app | Filas típicas | Notas |
|---|---|---|---|
| `MatrizSeguimientoEvaluacion` | Departamento | ~56 proyectos | 49 columnas. Hitos 1, 2, 3, 4 (nuevo), 5 y 6. Tiene `FECHA DE FINALIZACIÓN`. |
| `OtrosEjecutoresDescentralizadas` | Descentralizadas | ~16 proyectos | 38 columnas. Hitos 1, 2, 3 y 5. NO tiene H4 (requiere contratos) ni H6 (sin fecha de finalización). |
| `OtrosEjecutoresMunicipios` | Otros ejecutores (label) / Municipios (interno) | ~102 proyectos | 18 columnas. Sin hitos. |

**Default GitHub URLs** (en `regalias/data.py` / `regalias/data_igpr.py`):
- Matriz principal: `https://raw.githubusercontent.com/Dona121/Matriz-Evaluacion-Regalias/main/data/MatrizSeguimientoEvaluacion.xlsx`
- Contratos: `https://raw.githubusercontent.com/Dona121/Matriz-Evaluacion-Regalias/main/data/CG-cttos.xlsx`
- IGPR (5 archivos): `https://raw.githubusercontent.com/Dona121/Matriz-Evaluacion-Regalias/main/data/IGPR/...`

La app cae al archivo del repo si el usuario no sube uno manualmente.

### Columnas clave (comunes)

- `BPIN` — ID único del proyecto
- `ENTIDAD O SECRETARIA` (Departamento) / `EJECUTOR` (Descent + Munic) — agrupador
- `NOMBRE PROYECTO` (Departamento) / `NOMBRE DEL PROYECTO` (Descent + Munic)
- `ESTADO PROYECTO` — driver principal de los hitos: SIN CONTRATAR, CONTRATADO SIN ACTA DE INICIO, CONTRATADO EN EJECUCIÓN, TERMINADO, PARA CIERRE
- `ESTADO CONTRATO`
- `CPI`, `SPI` — indicadores de costo/cronograma (H5 rezagado)
- 7 fechas: APROBACIÓN, APERTURA PRIMER PROCESO, SUSCRIPCION, ACTA INICIO, HORIZONTE, FINALIZACIÓN, CORTE GESPROY
- `AVANCE FISICO` (Depto, sin tilde) / `AVANCE FÍSICO` (Descent + Munic, con tilde) — gestionado por constantes `AVANCE_FISICO_DEPTO` y `AVANCE_FISICO_OTROS`
- `AVANCE FINANCIERO`
- `RESPONSABLE CARGUE EN GESPROY` (solo Departamento)
- `COMENTARIOS CALIFICACIÓN` (Depto + Descent) / `COMENTARIOS` (Munic — se renombra internamente al primero)
- 4 calificaciones (escala 0-100): `CALIFICACIÓN DESEMPEÑO EN LA CONTRATACIÓN`, `CALIFICACIÓN INFORMACIÓN A TIEMPO`, `CALIFICACIÓN EJECUCIÓN DEL PROYECTO`, `CALIFICACIÓN CALIDAD INFORMACIÓN`
- `SECTOR` (Munic + Depto + Descent)

### Lectura robusta

`_leer_tabla_robusta(file_bytes, nombre)` en `data.py` intenta en cascada:
1. Tabla nombrada (`Insertar → Tabla` en Excel) con ese nombre.
2. Hoja con ese nombre, header en fila 1.
3. Hoja con ese nombre, header en fila 2 (caso del archivo de Sucre: la fila 1 es título, la 2 son los encabezados).
4. Lectura raw sin headers, promoción manual del header.

Además, `_strip_columnas(df)` recorta automáticamente espacios al inicio/final de los nombres de columna (el archivo trae `"COMENTARIOS "` con un espacio extra). Cualquier código que busque por nombre exacto debe asumir que ya viene limpio.

### Contratos (CG-cttos.xlsx)

`procesar_contratos(file_bytes)` en `data.py` lee:
- `BPIN`, `NO. PROCESO PRECONTRACTUAL`, `MODALIDAD CONTRATACION`, `TIPO CONTRATO`, `CONTRATO OBJETO`, `CONTRATO VALOR TOTAL`, `ESTADO CONTRATO`
- `FECHA FINAL` (programada) — **opcional**, puede no existir en exports antiguos.
- `FECHA FINAL REAL` — fecha de terminación real.

Las fechas se parsean a `pl.Date` en múltiples formatos. En el panel de contratos
del Detalle de proyectos (Departamento) se muestra una columna **Diferencia meses
(real − prog.)** calculada como `(FECHA FINAL REAL − FECHA FINAL) / 30`.

---

## Lógica de hitos (CRÍTICA — viene del notebook del cliente)

Cada proyecto se evalúa contra hasta **7 hitos** según su estado. Los Hitos 0 y 4
son **informativos** (sin semáforo, solo días promedio); los demás clasifican el
tiempo entre dos fechas en un nivel de alerta.

### H0 — Sin contratar (general, sin semáforo)

- **Aplica:** `ESTADO PROYECTO` ∈ {SIN CONTRATAR, vacío, NULL} y tiene fecha de aprobación.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA APROBACIÓN PROYECTO` en días.
- **Sin semáforo** — solo se reporta el promedio.

### H1 — Sin contratar sin apertura

- **Aplica:** `ESTADO PROYECTO` ∈ {SIN CONTRATAR, vacío, NULL} **Y** sin apertura del primer proceso registrada **Y** tiene fecha de aprobación.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA APROBACIÓN PROYECTO` en días.
- **Importante (regla de no-duplicidad):** si el proyecto YA tiene `FECHA DE APERTURA DEL PRIMER PROCESO`, pasa a H2 y NO se cuenta también en H1.
- **Semáforo (días):** verde 0-100, naranja 101-150, rojo 151-180, negro >180.

### H2 — Sin contratar con apertura

- **Aplica:** `ESTADO PROYECTO` ∈ {SIN CONTRATAR, vacío, NULL} **Y** tiene fecha de apertura del primer proceso.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA DE APERTURA DEL PRIMER PROCESO` en días.
- **Semáforo (días):** verde 0-100, naranja 101-150, rojo 151-180, negro >180.

### H3 — Contratado sin acta de inicio

- **Aplica:** `ESTADO PROYECTO == "CONTRATADO SIN ACTA DE INICIO"` **Y** tiene fecha de suscripción.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA DE SUSCRIPCIÓN DEL CONTRATO PRINCIPAL` en días.
- **Semáforo (días):** verde 0-15, naranja 16-30, rojo 31-45, negro >45.
- **Nota (renombre):** la columna antes se llamaba `FECHA SUSCRIPCION`; en el Excel nuevo es `FECHA DE SUSCRIPCIÓN DEL CONTRATO PRINCIPAL`. Existe además `FECHA DE SUSCRIPCIÓN DEL PRIMER CONTRATO` (aún sin uso). H3 usa la del **contrato principal**.

### H4 — En ejecución (informativo, sin semáforo · SOLO Departamento)

- **Aplica:** `ESTADO PROYECTO == "CONTRATADO EN EJECUCIÓN"` **Y** `HORIZONTE DEL PROYECTO >= FECHA DE CORTE GESPROY` (horizonte vigente) **Y** ningún contrato del proyecto en estado SUSPENDIDO.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA ACTA INICIO` en días.
- **Sin semáforo** — solo reporta días.
- **Solo aplica al Departamento** porque depende de `df_contratos` (CG-cttos.xlsx) para descartar suspendidos. La función `aplicar_hito_4_en_ejecucion(df, df_contratos)` se invoca tras cargar contratos.
- Para Descentralizadas/Municipios la columna `hito_4_val` simplemente no se calcula.

### H5 — En ejecución rezagado

- **Aplica:** `ESTADO PROYECTO == "CONTRATADO EN EJECUCIÓN"` **Y** `HORIZONTE DEL PROYECTO <= FECHA DE CORTE GESPROY` (horizonte vencido). **Ya NO exige `CPI == 0` ni `SPI == 0`** (se eliminó esa condición — AjustesReporte punto 1).
- **Cálculo:** `FECHA DE CORTE GESPROY - HORIZONTE DEL PROYECTO` en días, **mostrado en MESES** (días / 30).
- **Semáforo (meses):** verde 0-1, naranja 1.1-3, rojo 3.1-6, negro >6.
- **El valor interno se almacena en días** (`hito_5_val`); la conversión a meses pasa al mostrar.
- La función `clasificar_hito4_meses(col)` en `data.py` clasifica este hito (el nombre conserva la convención histórica).
- **Exclusión de suspendidos (SOLO Departamento):** en `aplicar_hito_4_en_ejecucion` se anulan `hito_5_val` y `clasi_5` de los proyectos con ≥1 contrato suspendido (pasan a H7). Así H5 y H7 son mutuamente excluyentes. En Descentralizadas no hay archivo de contratos ni H7, así que ahí H5 solo pierde la condición CPI/SPI (no excluye suspendidos).

### H6 — Terminados pendientes de cierre (SOLO Departamento)

- **Aplica:** `ESTADO PROYECTO == "TERMINADO"` **Y** tiene `FECHA DE FINALIZACIÓN` registrada.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA DE FINALIZACIÓN` en días.
- **Semáforo (días):** verde 0-100, naranja 101-150, rojo 151-180, negro >180.
- **NO aplica a Descentralizadas** (su tabla no tiene `FECHA DE FINALIZACIÓN`).

### H7 — Proyectos suspendidos (informativo, sin semáforo · SOLO Departamento)

- **Aplica:** `ESTADO PROYECTO == "CONTRATADO EN EJECUCIÓN"` **Y** el proyecto tiene **al menos un contrato en estado SUSPENDIDO** (según `CG-cttos.xlsx`).
- **Cálculo:** conteo de proyectos (`hito_7_val = 1`), reportado como número de proyectos por dependencia. **Sin semáforo.**
- **Solo Departamento.** Se calcula en `aplicar_hito_4_en_ejecucion`, reusando el set `bpins_susp` (BPINs con contrato suspendido) que ya se construye para H4 — más eficiente que sumar contrato por contrato.
- En Descentralizadas/Municipios NO se calcula (no hay archivo de contratos consolidado).

### H8 — Proyecto para cierre (informativo, sin semáforo · SOLO Departamento)

- **Aplica:** `ESTADO PROYECTO == "PARA CIERRE"` **Y** tiene `FECHA EN LA QUE PASO A ESTADO PARA CIERRE` registrada.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA EN LA QUE PASO A ESTADO PARA CIERRE` en días, **promediado por dependencia**. **Sin semáforo.** El `/` de la fórmula original (corte/fecha actual) se resuelve solo: `FECHA DE CORTE GESPROY` ya refleja "hoy" cuando se elige ese filtro de corte.
- La columna `FECHA EN LA QUE PASO A ESTADO PARA CIERRE` solo existe en versiones nuevas del Excel; se trata como **opcional** (`hito_8_val` queda null si falta). En el archivo `20260526` la columna existe pero **viene vacía**, así que H8 muestra 0 hasta que se carguen las fechas.
- Se calcula en `procesar()` (no necesita contratos).

### Otros indicadores

- **Suspendidos:** flag (1/null) cuando `ESTADO CONTRATO == "SUSPENDIDO"` (de la propia Matriz). Se cuenta en el resumen, NO es un hito con semáforo. Es distinto de **H7** (que usa CG-cttos y exige estado en ejecución).
- **Para cierre:** flag cuando `ESTADO PROYECTO == "PARA CIERRE"`. Conteo. Es distinto de **H8** (que mide promedio de días).
- **CG-cttos obligatorio:** el archivo de contratos debe estar siempre disponible (repositorio o carga manual). Si falta, la app muestra un mensaje y hace `st.stop()` (la Guía de hitos sí se ve, porque hace `st.stop()` antes). De CG-cttos dependen H4 y H7.

### Fecha de corte configurable

Hay un filtro en el sidebar (`fecha_corte_override`) que permite usar:
- **"Del archivo (GESPROY)"** — la columna `FECHA DE CORTE GESPROY` del Excel (default).
- **"Hoy · DD/MM/YYYY"** — la fecha actual en zona horaria America/Bogota.

Cuando se elige "Hoy", `procesar(file_bytes, fecha_corte_override=hoy)` sobreescribe la columna antes de calcular hitos. La pestaña de **Evaluación del modelo** ignora este filtro a propósito — siempre usa la fecha del archivo (las calificaciones son pre-calculadas en el Excel).

### Mapeo de colores (SEMAFOROS en constants.py)

```python
"hito_X_val": {
    "0-100":   ("green",  "Verde",   "mensaje..."),
    "101-150": ("yellow", "Naranja", "mensaje..."),
    "151-180": ("orange", "Rojo",    "mensaje..."),
    ">180":    ("black",  "Negro",   "mensaje..."),
}
```

Solo `hito_1_val`, `hito_2_val`, `hito_3_val`, `hito_5_val` y `hito_6_val` tienen
entradas en SEMAFOROS. Los hitos 0 y 4 son informativos.

El color interno (`green/yellow/orange/black`) NO coincide directamente con el
nivel — son las claves CSS internas. El "nivel" usuario es Verde/Naranja/Rojo/Negro.

---

## UI — vistas y pestañas

El sidebar tiene un radio principal **Vista** con 6 opciones (en orden):

1. **Guía de hitos** (DEFAULT) — pantalla introductoria que explica cada hito.
   No muestra KPIs ni pestañas. Renderiza `render_guia_hitos(incluir_h5=True, ...)`
   y llama `st.stop()`. Toda la info se construye dinámicamente desde `HITOS_INFO`
   (en app.py) y `SEMAFOROS` (constants.py).
2. **Departamento** — 4 pestañas: Resumen por entidad, Todos los proyectos, Reporte
   semanal de alertas, Evaluación del modelo.
3. **Descentralizadas** — 4 pestañas: Resumen por entidad, Proyectos, Reporte semanal
   de alertas, Evaluación del modelo.
4. **Otros ejecutores** (label visible) / **Municipios** (valor interno) — 1 pestaña:
   Proyectos (sin hitos, sin evaluación, sin contratos).
5. **Mapa** — visor geográfico full-screen con Leaflet + GeoJSON de Sucre.
6. **IGPR** — Índice de Gestión de Proyectos de Regalías (Resolución 4574/2025).

El renombre Municipios → Otros ejecutores se hace **solo en el label** del
sidebar via `format_func` (línea ~310 de app.py). El valor interno `vista` sigue
siendo `"Municipios"` para no romper el resto del código.

Además del radio de vista, el sidebar tiene:
- **Fecha de corte** (filtro radio: archivo vs hoy).
- **Datos** (botón "Recargar datos del repositorio" + uploader manual).
- **Contratos** (uploader del CG-cttos.xlsx — opcional).
- **Exportar** (botón global que descarga el Excel consolidado, INDEPENDIENTE del filtro de vista).

### Filtros por pestaña

- **Departamento → Todos los proyectos:** búsqueda libre, entidad, estado proyecto,
  estado contrato, responsable cargue GESPROY, **Sector**.
- **Descentralizadas → Proyectos:** búsqueda libre, ejecutor, **Sector**.
- **Otros ejecutores → Proyectos:** búsqueda libre, municipio, **Sector**.

### Patrones de UI

- **Estados de proyecto** usan `_estado_tooltip_html` (de render.py) que genera un tooltip rico con: descripción del estado, situación actual contextual basada en hitos, avance físico/financiero, fechas en GESPROY. Posicionado dinámicamente con JS desde `inject_css()`.
- **Comentarios de calificación** (`COMENTARIOS CALIFICACIÓN`) se muestran como tooltip oscuro al pasar el cursor sobre el estado en:
  - Departamento → Resumen → Detalle por hito
  - Descentralizadas → Resumen → Detalle por hito
  - Otros ejecutores → Proyectos
  El wrapper es `.coment-wrap` con `.coment-tip-box` dentro. JS en `inject_css()` los inicializa.
- **Semáforo de hitos** se muestra como `<span class="badge badge-{green/yellow/orange/black}">` con punto + tooltip flotante.
- **Días por hito** se muestra como `dias-val-link` con tooltip que explica el cálculo (`_dias_tooltip`).
- **Panel de contratos** (Dpto → Todos los proyectos → toggle "Contratos"): tabla con No. proceso, modalidad, tipo, valor total (gradiente), estado, fecha de terminación, **Diferencia meses (real − prog.)**, objeto del contrato.

### Exportable

`generar_excel()` en `export.py` produce hasta **9 hojas**:
1. Resumen Departamento (entidad × hitos 1, 2, 3, 4, 5, 6 + Susp + Cierre + Total). H5 en meses. H4 sin semáforo.
2. Detalle Departamento (proyectos × fechas × hitos × alertas × mensajes).
3. Reporte Semanal Dpto (dependencia × estado × alertas).
4. Resumen Descentralizadas (ejecutor × hitos 1, 2, 3 y 5 + Susp + Cierre + Total).
5. Detalle Descentralizadas.
6. Reporte Semanal Descent.
7. Detalle Municipios (proyectos básicos, sin hitos).
8. Evaluación Sucre.
9. Evaluación Descentralizadas.

Cada hoja se omite si no hay datos. Las celdas de semáforo van con color de fondo
+ comentario emergente con el mensaje del hito. Las fechas en formato
`DD/MM/YYYY`. Los avances como porcentaje (normalizado si vienen como 0-1).

---

## IGPR (Índice de Gestión de Proyectos de Regalías, Res. 4574/2025)

Módulo dedicado: `data_igpr.py` (procesamiento) + `igpr.py` (vista). Aislado
del resto para no contaminar la lógica de hitos.

### Fuentes

5 Excel publicados por el DNP (en GitHub Raw, bajo `data/IGPR/`), uno por
trimestre. Cada uno tiene una tabla nombrada `IGPR_<TRIMESTRE>_<AÑO>`:

| Trimestre | Tabla | Columna del puntaje |
|---|---|---|
| I 2025 | `IGPR_I_Trimestre_2025` | `IGPR FINAL PROYECTO I TRIM 2025` |
| II 2025 | `IGPR_II_Trimestre_2025` | `IGPR FINAL PROYECTO II TRIM 2025` |
| III 2025 | `IGPR_III_Trimestre_2025` | `IGPR FINAL PROYECTO III TRIM 2025` |
| IV 2025 | `IGPR_IV_Trimestre_2025` | `IGPR PROYECTO FINAL IV TRIM 2025` |
| I 2026 | `IGPR_I_Trimestre_2026` | `IGPR PROYECTO FINAL` |

Cada archivo se descarga con caché de 1 hora (`@st.cache_data ttl=3600`).

### Pipeline

`cargar_igpr(matriz_bytes)` → `_cargar_igpr_impl_v2(matriz_bytes, _CARGAR_IGPR_CACHE_VERSION)`:

1. Construye el catálogo `BPIN → ENTIDAD` a partir de las 3 tablas de la Matriz
   de Seguimiento (Dpto, Descent, Munic).
2. Para cada trimestre:
   a. Descarga el Excel.
   b. Aplica `_limpiar_encabezados()`: deshace `_x000a_` (saltos de línea Excel),
      colapsa dobles espacios, elimina fechas embebidas y asteriscos.
   c. Filtra por `ENTIDAD EJECUTORA O BENEFICIARIA (A MEDIR) == "DEPARTAMENTO DE SUCRE"`.
   d. Selecciona columnas (BPIN, NOMBRE DEL PROYECTO, puntaje + extras del trimestre).
   e. Castea PUNTAJE a Float64.
   f. **Para vigencia ≥ 2026:** detecta columnas de situación por substring
      (case-insensitive, sin tildes) — patrones `INCONSISTENCIA`, `IRREGULARIDAD`,
      `MODIFICAC` + `REPORTE`. Computa el flag `PRESENTA ALGUNA SITUACION QUE AFECTA PUNTAJE`
      como `max(SI/NO en cada flag)` (acepta SI/Sí/S/1/X/TRUE/...).
   g. Hace join con el catálogo de entidades.
3. Concatena todos los trimestres con `pl.concat(how="diagonal")`.
4. Genera columnas auxiliares `_orden_trim` (1-4) y `PERIODO` ("I 2025", "II 2025"...).
5. Categoriza cada PUNTAJE en `ADECUADO` / `NO ADECUADO` / `SIN DATO` con el
   umbral `UMBRAL_ADECUADO_DEPARTAMENTO = 60.0` (Sucre, Capacidad 2).

### Descuento por situaciones (vigencia ≥ 2026)

**Importante**: el descuento NO se aplica por proyecto. Se aplica al **PROMEDIO
del periodo de la entidad** cuando AL MENOS UN proyecto de esa entidad
presentó situación. Esta lógica vive en `resumen_por_periodo()` y
`resumen_por_entidad_periodo()`:

```python
PROMEDIO = clip(PROMEDIO_BRUTO − 10, 0, 100)   si hay_situacion == 1 y vigencia ≥ 2026
         = PROMEDIO_BRUTO                       en otro caso
```

Esto produce: para Sucre I 2026 con 1 proyecto en situación, `PROMEDIO_BRUTO=68.2 → PROMEDIO=58.2`.

### Vista IGPR (igpr.py)

Pestañas:
- **Resumen general** — evolución del promedio por trimestre + matriz Entidad ×
  Periodo. Incluye un expander **"Diagnóstico · Descuento por situaciones (vigencia 2026)"**
  con `Promedio_bruto`, `Proyectos_con_situacion`, `Total_proyectos`, `Promedio_ajustado`.
- **Detalle por trimestre** — selector de trimestre + tabla de proyectos con
  desplegables por entidad.
- **Detalle por entidad** — selector de entidad + evolución y tabla de sus
  proyectos a lo largo de todos los trimestres.
- **Metodología** — resumen visual de la Resolución 4574 (estados, indicadores,
  escala diferencial, descuentos, bonificaciones, ponderador de reporte oportuno).

### Cache busting

`_CARGAR_IGPR_CACHE_VERSION = "v4-descuento-a-nivel-entidad-periodo"`. Bump este
string en cualquier cambio que afecte el resultado de `cargar_igpr` — esto
invalida el caché de Streamlit sin requerir que el usuario toque "Recargar".

---

## Quirks importantes

1. **Streamlit cache_data**: `procesar_descentralizadas_hitos`, `procesar_municipios`, `procesar_descentralizadas`, `procesar_eval_sucre`, `procesar_contratos` y `_cargar_igpr_impl_v2` están decoradas con `@st.cache_data`. Para forzar recálculo, el botón "Recargar datos del repositorio" llama `st.cache_data.clear()`. Para `cargar_igpr` también basta con cambiar `_CARGAR_IGPR_CACHE_VERSION`.

2. **Polars binary**: requiere `polars>=1.20` + `fastexcel>=0.12`. Versiones antiguas no soportan `read_excel(table_name=...)` correctamente.

3. **Sidebar limpio**: ya NO hay emojis en los títulos del sidebar (se removieron por pedido del cliente). NO los reintroduzcas.

4. **Diseño "no AI"**: el cliente pidió explícitamente menos gradientes, menos sombras pesadas, look más institucional/gobierno. Las tarjetas de KPI son azul sólido (Total proyectos) + blanca con borde azul (Entidades). NO uses degradés.

5. **`fecha_corte_override`** se propaga solo a `procesar()` y `procesar_descentralizadas_hitos()`. La evaluación, los datos de municipios y el IGPR (que no calculan hitos) NO lo reciben.

6. **Reporte semanal de alertas**: solo cuenta semáforo naranja/rojo/negro (no verde). El bug del doble-conteo de H1 + H2 ya está corregido — leer la clave UNA sola vez.

7. **Hito 1 vs Hito 2 — regla de no-duplicidad**: H1 requiere que `FECHA DE APERTURA DEL PRIMER PROCESO` sea NULL. Si la tiene, va solo a H2.

8. **Hito 4 vs Hito 5 — mutuamente excluyentes**: H4 requiere horizonte VIGENTE (`HORIZONTE >= CORTE`) y sin contratos suspendidos. H5 requiere horizonte VENCIDO (`HORIZONTE <= CORTE`) con CPI=SPI=0.

9. **Hito 4 SOLO en Departamento**: el cálculo necesita la tabla de contratos para descartar proyectos con al menos un contrato suspendido. Descentralizadas y Otros ejecutores NO tienen archivo de contratos consolidado.

10. **Columnas con espacios extra**: el lector las limpia automáticamente con `_strip_columnas`. No necesitas mantener variantes en el código.

11. **`@st.cache_data` y argumentos hashables**: si pasas `fecha_corte_override=date(...)`, polars/Streamlit cachea bien. Pero NO uses `datetime` con timezone — date sin tz funciona mejor.

12. **Vista Mapa**: se renderiza en modo "full-viewport" con CSS especial que neutraliza el padding-top de Streamlit. NO modificar el bloque CSS de la vista Mapa sin entender el contexto (transforms/contain rompen el position:fixed del iframe).

13. **Edit tool con app.py / regalias/igpr.py / regalias/data_igpr.py**: el Edit tool ha truncado estos archivos grandes en ediciones anteriores. Para cambios complejos, usar un Python script atómico con `Path.read_text()` + `str.replace()` + `Path.write_text()` y verificar con `wc -l` antes/después + `py_compile`.

---

## Estado actual de funcionalidades

Completadas:

- Vista Guía de hitos (default landing) con cards dinámicas.
- 5 vistas adicionales (Dpto, Descent, Otros ejecutores, Mapa, IGPR) con sus pestañas.
- 7 hitos: H0 informativo, H1-H3 con semáforo (días), H4 informativo (En ejecución, sin semáforo, depende de contratos), H5 rezagado (meses), H6 terminados.
- Regla de no-duplicidad H1/H2.
- H4 nuevo: días desde acta de inicio para proyectos en ejecución con horizonte vigente y sin contratos suspendidos.
- Filtro de fecha de corte (archivo vs hoy).
- Tooltips de COMENTARIOS CALIFICACIÓN en Detalle por hito (Dpto + Descent) y en Proyectos de Otros ejecutores.
- Tooltip rico de estado con avance físico/financiero.
- Drilldown por hito en Resumen (Dpto + Descent).
- Reporte semanal de alertas como pestaña dedicada (Dpto + Descent).
- Evaluación del modelo (4 criterios + promedio coloreado).
- Filtro RESPONSABLE CARGUE EN GESPROY en proyectos de Dpto.
- Filtro y columna SECTOR en proyectos de Dpto, Descent y Otros ejecutores.
- Panel de contratos con columna Diferencia meses (real − prog.).
- Visor de mapa (Leaflet + Sucre.geojson) por municipio.
- IGPR (5 trimestres) con descuento de −10 al promedio entidad/periodo para vigencia 2026 cuando hay situaciones.
- Export Excel global consolidado (9 hojas).
- Botón de export en sidebar (siempre disponible, independiente de la vista).
- Lectura robusta del Excel con fallback de 4 estrategias.
- Strip automático de espacios en nombres de columna.
- Detección flexible de columnas IGPR 2026 (match por substring).

Próximo paso pendiente: sistema de comentarios persistente con Supabase
(Streamlit + Supabase, no Django). Diseño preliminar disponible (tabla,
policies RLS, auth email+password) — ver historial de conversación.

---

## Cómo correr

### Local (uv — recomendado)

```bash
uv sync                        # crea .venv e instala desde uv.lock
uv run streamlit run app.py
```

`uv add <paquete>` / `uv remove <paquete>` para gestionar dependencias (actualizan
`pyproject.toml` + `uv.lock`). Si cambias deps, regenera el espejo para Railway con
`uv export --no-hashes -o requirements.txt`.

### Local (pip clásico)

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Railway

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

Variables de entorno futuras (cuando se integre Supabase):
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

---

## Decisiones de diseño que NO debes cambiar sin pedir

1. **Hito 1 vs Hito 2 son mutuamente excluyentes** (si tiene apertura, va solo a H2).
2. **Hito 4 vs Hito 5 son mutuamente excluyentes** (H4 = horizonte vigente sin susp; H5 = horizonte vencido con CPI=SPI=0).
3. **Hito 5 se muestra en MESES, no en días.** Internamente está en días.
4. **Hito 4 (nuevo) y Hito 0 son informativos** — no tienen semáforo.
5. **Hito 4 SOLO aplica a Departamento.** Requiere df_contratos para descartar suspendidos.
6. **Hito 6 NO aplica a Descentralizadas.**
7. **IGPR — descuento por situaciones:** se aplica al PROMEDIO del periodo de la entidad, NO por proyecto. Y solo si hay AL MENOS UN proyecto con situación SI en alguno de los 3 flags (Inconsistencias / Irregularidades graves / Modificación de reporte).
8. **La pestaña de Evaluación del modelo NO se afecta por el filtro de fecha de corte.**
9. **El export del Excel es GLOBAL** — no depende de la vista activa.
10. **La Guía es la pantalla por defecto** al entrar a la app.
11. **Sin emojis en el sidebar.** Sin degradés en KPIs.
12. **Reporte semanal solo cuenta semáforos NRN** (naranja/rojo/negro), no verde.
13. **El label "Otros ejecutores"** del sidebar es solo visual — internamente sigue siendo `vista == "Municipios"`.

---

## Convenciones de código

- HTML inline en `st.markdown(unsafe_allow_html=True)` para tablas custom.
- CSS centralizado en `inject_css()` en constants.py.
- JS global (tooltips, toggle de contratos) en `components.html()` dentro de `inject_css()` — usa MutationObserver para reinit en cada rerender de Streamlit.
- Helpers de datos en `data.py` con `@st.cache_data` cuando sea seguro.
- Nombres de columnas Excel se referencian como strings literales — usar `.strip()` no es necesario porque el lector ya lo hace.
- Polars expressions: `pl.col(...)`, `pl.when().then().otherwise()`, `pl.lit()`.
- Para columnas IGPR variables entre versiones del Excel, usar match por substring case-insensitive sin tildes (ver `_buscar_col` en `data_igpr.py`).
- Para evitar el Edit-tool-truncates-large-files bug, usar Python scripts atómicos con `Path.read_text()` + `str.replace()` + `Path.write_text()` cuando se editen `app.py`, `regalias/igpr.py` o `regalias/data_igpr.py`.
- Imports internos: siempre con prefijo del paquete — `from regalias.constants import ...`, `from regalias.data import ...`. `app.py` (en la raíz) hace lo mismo. No usar imports planos (`from constants import`).

---

## Archivos de referencia para entender el dominio

- `contexto/ReporteRegaliasHitos.ipynb` — notebook original del cliente con las fórmulas de cálculo de hitos. Fuente de verdad para la lógica.
- `contexto/IGPR.ipynb` — notebook del cliente con la lógica de consolidación de IGPR y el descuento por situaciones para 2026.
- `contexto/MatrizSeguimientoEvaluacion_*.xlsx` — Excel real de Sucre con las 3 tablas.
- `contexto/Resultados IGPR - I trimestre 2026 *.xlsx` — Excel real del IGPR I 2026 con las columnas de situación.
- `contexto/resolucion-4574-2025-12-30.pdf` (en uploads del usuario) — Resolución 4574/2025 del DNP con el marco oficial del IGPR.
- `regalias/Sucre.geojson` — geometrías de los municipios del Departamento (vive junto a `mapa.py`, que lo carga vía `os.path.dirname(__file__)`).
