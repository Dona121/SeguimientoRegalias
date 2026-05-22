# Proyecto: Seguimiento Regalías

App de Streamlit que visualiza el avance de proyectos de regalías del Departamento
de Sucre. Lee un Excel con 3 tablas y calcula hitos de gestión (semáforos verde/
naranja/rojo/negro) por proyecto, entidad y ejecutor.

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

```
Seguimiento Regalias/
├── app.py            # Orquestador principal (~2700 líneas): sidebar, header,
│                     #   routing por vista, render de KPIs, tabs y guía.
├── constants.py      # Paleta de colores (C), inyección de CSS+JS global
│                     #   (inject_css), INTERVALOS, SEMAFOROS, COLS_EVAL,
│                     #   TABLA_ESPERADA, TABLA_DESCENTRALIZADAS, TABLA_MUNICIPIOS.
├── data.py           # Lectura y procesamiento: _leer_tabla_robusta (fallback
│                     #   de estrategias), procesar(), procesar_descentralizadas_hitos(),
│                     #   procesar_municipios(), procesar_eval_sucre(),
│                     #   procesar_descentralizadas(), procesar_contratos(),
│                     #   validar_archivo(), _cargar_desde_github().
├── export.py         # Generación del Excel global consolidado (9 hojas).
├── render.py         # Helpers de presentación: badge_html, _pill, _fmt_date,
│                     #   _dias_tooltip, _estado_tooltip_html, eval_color,
│                     #   _clasificar_promedio, _contratos_panel, HITO_KEY_MAP, etc.
└── requirements.txt
```

---

## Fuentes de datos

El archivo Excel tiene **3 tablas/hojas**:

| Tabla / Hoja | Vista en la app | Filas típicas | Notas |
|---|---|---|---|
| `MatrizSeguimientoEvaluacion` | Departamento | ~56 proyectos | 49 columnas. Hitos 1-5. Tiene `FECHA DE FINALIZACIÓN`. |
| `OtrosEjecutoresDescentralizadas` | Descentralizadas | ~16 proyectos | 38 columnas. Hitos 1-4 (NO H5: no tiene fecha de finalización). |
| `OtrosEjecutoresMunicipios` | Municipios | ~102 proyectos | 18 columnas. Sin hitos (no tiene fechas de seguimiento ni CPI/SPI). |

**Default GitHub URL** (en `data.py`): `https://raw.githubusercontent.com/Dona121/Matriz-Evaluacion-Regalias/main/data/MatrizSeguimientoEvaluacion.xlsx`.
La app cae a este archivo si el usuario no sube uno manualmente.

### Columnas clave (comunes)

- `BPIN` — ID único del proyecto
- `ENTIDAD O SECRETARIA` (Departamento) / `EJECUTOR` (Descent + Munic) — agrupador
- `NOMBRE PROYECTO` (Departamento) / `NOMBRE DEL PROYECTO` (Descent + Munic)
- `ESTADO PROYECTO` — driver principal de los hitos: SIN CONTRATAR, CONTRATADO SIN ACTA DE INICIO, CONTRATADO EN EJECUCIÓN, TERMINADO, PARA CIERRE
- `ESTADO CONTRATO`
- `CPI`, `SPI` — indicadores de costo/cronograma (H4)
- 7 fechas: APROBACIÓN, APERTURA PRIMER PROCESO, SUSCRIPCION, ACTA INICIO, HORIZONTE, FINALIZACIÓN, CORTE GESPROY
- `AVANCE FISICO` (Depto, sin tilde) / `AVANCE FÍSICO` (Descent + Munic, con tilde) — gestionado por constantes `AVANCE_FISICO_DEPTO` y `AVANCE_FISICO_OTROS`
- `AVANCE FINANCIERO`
- `RESPONSABLE CARGUE EN GESPROY` (solo Departamento)
- `COMENTARIOS CALIFICACIÓN` (Depto + Descent) / `COMENTARIOS` (Munic — se renombra internamente al primero)
- 4 calificaciones (escala 0-100): `CALIFICACIÓN DESEMPEÑO EN LA CONTRATACIÓN`, `CALIFICACIÓN INFORMACIÓN A TIEMPO`, `CALIFICACIÓN EJECUCIÓN DEL PROYECTO`, `CALIFICACIÓN CALIDAD INFORMACIÓN`
- `SECTOR` (Munic + Depto)

### Lectura robusta

`_leer_tabla_robusta(file_bytes, nombre)` en `data.py` intenta en cascada:
1. Tabla nombrada (`Insertar → Tabla` en Excel) con ese nombre.
2. Hoja con ese nombre, header en fila 1.
3. Hoja con ese nombre, header en fila 2 (caso del archivo de Sucre: la fila 1 es título, la 2 son los encabezados).
4. Lectura raw sin headers, promoción manual del header.

Además, `_strip_columnas(df)` recorta automáticamente espacios al inicio/final de los nombres de columna (el archivo trae `"COMENTARIOS "` con un espacio extra). Cualquier código que busque por nombre exacto debe asumir que ya viene limpio.

---

## Lógica de hitos (CRÍTICA — viene del notebook del cliente)

Cada proyecto se evalúa contra hasta 5 hitos según su estado. Cada hito mide días (o meses para H4) entre dos fechas, y se clasifica en un nivel de alerta según rangos.

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
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA SUSCRIPCION` en días.
- **Semáforo (días):** verde 0-15, naranja 16-30, rojo 31-45, negro >45. (Actualizado por la entidad — versión más estricta.)

### H4 — En ejecución rezagado

- **Aplica:** `ESTADO PROYECTO == "CONTRATADO EN EJECUCIÓN"` **Y** `CPI == 0` **Y** `SPI == 0` **Y** `HORIZONTE DEL PROYECTO <= FECHA DE CORTE GESPROY` (horizonte vencido).
- **Cálculo:** `FECHA DE CORTE GESPROY - HORIZONTE DEL PROYECTO` en días, **mostrado en MESES** (días / 30).
- **Semáforo (meses):** verde 0-1, naranja 1.1-3, rojo 3.1-6, negro >6.
- **El valor interno se almacena en días** (`hito_4_val`), la conversión a meses pasa al mostrar.

### H5 — Terminados pendientes de cierre (SOLO Departamento)

- **Aplica:** tiene `FECHA DE FINALIZACIÓN` registrada.
- **Cálculo:** `FECHA DE CORTE GESPROY - FECHA DE FINALIZACIÓN` en días.
- **Semáforo (días):** verde 0-100, naranja 101-150, rojo 151-180, negro >180.
- **NO aplica a Descentralizadas** (su tabla no tiene `FECHA DE FINALIZACIÓN`).

### Otros indicadores

- **Suspendidos:** flag (1/null) cuando `ESTADO CONTRATO == "SUSPENDIDO"`. Se cuenta en el resumen, NO es un hito con semáforo.
- **Para cierre:** flag cuando `ESTADO PROYECTO == "PARA CIERRE"`. Igual.

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

El color interno (`green/yellow/orange/black`) NO coincide directamente con el nivel — son las claves CSS internas. El "nivel" usuario es Verde/Naranja/Rojo/Negro.

---

## UI — vistas y pestañas

El sidebar tiene un radio principal **Vista** con 4 opciones (en orden):

1. **Guía de hitos** (DEFAULT) — pantalla introductoria que explica cada hito.
   No muestra KPIs ni pestañas. Renderiza `render_guia_hitos(incluir_h5=True, ...)`
   y llama `st.stop()`. Toda la info se construye dinámicamente desde `HITOS_INFO`
   (en app.py) y `SEMAFOROS` (constants.py).
2. **Departamento** — 4 pestañas: Resumen por entidad, Todos los proyectos, Reporte
   semanal de alertas, Evaluación del modelo.
3. **Descentralizadas** — 4 pestañas: Resumen por entidad, Proyectos, Reporte semanal
   de alertas, Evaluación del modelo.
4. **Municipios** — 1 pestaña: Proyectos (sin hitos, sin evaluación, sin contratos).

Además del radio de vista, el sidebar tiene:
- **Fecha de corte** (filtro radio: archivo vs hoy).
- **Datos** (botón "Recargar datos del repositorio" + uploader manual).
- **Contratos** (uploader del CG-cttos.xlsx — opcional).
- **Exportar** (botón global que descarga el Excel consolidado, INDEPENDIENTE del filtro de vista).

### Patrones de UI

- **Estados de proyecto** usan `_estado_tooltip_html` (de render.py) que genera un tooltip rico con: descripción del estado, situación actual contextual basada en hitos, avance físico/financiero, fechas en GESPROY, paso para avanzar. Posicionado dinámicamente con JS desde `inject_css()`.
- **Comentarios de calificación** (`COMENTARIOS CALIFICACIÓN`) se muestran como tooltip oscuro al pasar el cursor sobre el estado en:
  - Departamento → Resumen → Detalle por hito
  - Descentralizadas → Resumen → Detalle por hito
  - Municipios → Proyectos
  El wrapper es `.coment-wrap` con `.coment-tip-box` dentro. JS en `inject_css()` los inicializa.
- **Semáforo de hitos** se muestra como `<span class="badge badge-{green/yellow/orange/black}">` con punto + tooltip flotante.
- **Días por hito** se muestra como `dias-val-link` con tooltip que explica el cálculo (`_dias_tooltip`).

### Exportable

`generar_excel()` en `export.py` produce hasta **9 hojas**:
1. Resumen Departamento (entidad × hitos 1-5 + Susp + Cierre + Total). H4 en meses.
2. Detalle Departamento (proyectos × fechas × hitos × alertas × mensajes).
3. Reporte Semanal Dpto (dependencia × estado × alertas).
4. Resumen Descentralizadas (ejecutor × hitos 1-4 + Susp + Cierre + Total).
5. Detalle Descentralizadas.
6. Reporte Semanal Descent.
7. Detalle Municipios (proyectos básicos, sin hitos).
8. Evaluación Sucre.
9. Evaluación Descentralizadas.

Cada hoja se omite si no hay datos. Las celdas de semáforo van con color de fondo + comentario emergente con el mensaje del hito. Las fechas en formato `DD/MM/YYYY`. Los avances como porcentaje (normalizado si vienen como 0-1).

---

## Quirks importantes

1. **Streamlit cache_data**: `procesar_descentralizadas_hitos`, `procesar_municipios`, `procesar_descentralizadas`, `procesar_eval_sucre`, `procesar_contratos` están decoradas con `@st.cache_data`. Para forzar recálculo, el botón "Recargar datos del repositorio" llama `st.cache_data.clear()`.

2. **Polars binary**: requiere `polars>=1.20` + `fastexcel>=0.12`. Versiones antiguas no soportan `read_excel(table_name=...)` correctamente.

3. **Sidebar limpio**: ya NO hay emojis en los títulos del sidebar (se removieron por pedido del cliente). NO los reintroduzcas.

4. **Diseño "no AI"**: el cliente pidió explícitamente menos gradientes, menos sombras pesadas, look más institucional/gobierno. Las tarjetas de KPI son azul sólido (Total proyectos) + blanca con borde azul (Entidades). NO uses degradés.

5. **`fecha_corte_override`** se propaga solo a `procesar()` y `procesar_descentralizadas_hitos()`. La evaluación y los datos de municipios (que no calculan hitos) NO lo reciben.

6. **Reporte semanal de alertas**: solo cuenta semáforo naranja/rojo/negro (no verde). El bug del doble-conteo de H1 + H2 (que comparten clave ">180" en SIN CONTRATAR) ya está corregido — leer la clave UNA sola vez.

7. **Hito 1 vs Hito 2 — regla de no-duplicidad**: H1 requiere que `FECHA DE APERTURA DEL PRIMER PROCESO` sea NULL. Si la tiene, va solo a H2. Esto evita contar el mismo proyecto en ambos.

8. **Columnas con espacios extra**: el lector las limpia automáticamente con `_strip_columnas`. No necesitas mantener variantes en el código.

9. **`@st.cache_data` y argumentos hashables**: si pasas `fecha_corte_override=date(...)`, polars/Streamlit cachea bien. Pero NO uses `datetime` con timezone — date sin tz funciona mejor.

---

## Estado actual de funcionalidades

✅ **Completadas:**

- Vista Guía de hitos (default landing) con cards dinámicas.
- 3 vistas adicionales (Dpto, Descent, Munic) con sus pestañas.
- Cálculo de hitos con regla de no-duplicidad H1/H2.
- Filtro de fecha de corte (archivo vs hoy).
- Tooltips de COMENTARIOS CALIFICACIÓN en Detalle por hito (Dpto + Descent) y en Proyectos de Municipios.
- Tooltip rico de estado con avance físico/financiero.
- Drilldown por hito en Resumen (Dpto + Descent).
- Reporte semanal de alertas como pestaña dedicada (Dpto + Descent).
- Evaluación del modelo (4 criterios + promedio coloreado).
- Filtro RESPONSABLE CARGUE EN GESPROY en proyectos de Dpto.
- Sector como columna en Municipios.
- Export Excel global consolidado (9 hojas).
- Botón de export en sidebar (siempre disponible, independiente de la vista).
- Lectura robusta del Excel con fallback de 4 estrategias.
- Strip automático de espacios en nombres de columna.

🚧 **PRÓXIMO PASO (donde quedó la conversación): Sistema de comentarios persistente con Supabase**

El cliente quiere que los usuarios puedan **agregar comentarios a proyectos directamente desde la app** y que esos comentarios se mantengan entre sesiones. Decisión tomada: **Streamlit + Supabase** (NO usar Django).

### Diseño propuesto

**Tabla en Supabase:**

```sql
create table comentarios_proyecto (
  id          bigserial primary key,
  bpin        text not null,
  fuente      text not null,                        -- 'departamento' | 'descentralizadas' | 'municipios'
  autor_id    uuid not null references auth.users,
  autor_email text not null,                        -- denormalizado para evitar joins
  comentario  text not null,
  creado_en   timestamptz default now()
);
create index on comentarios_proyecto (bpin);
alter table comentarios_proyecto enable row level security;
```

**Policies RLS:**

```sql
create policy "leer_todos_logueados" on comentarios_proyecto for select
  using (auth.uid() is not null);

create policy "insertar_propios" on comentarios_proyecto for insert
  with check (autor_id = auth.uid());

create policy "modificar_propios" on comentarios_proyecto for update
  using (autor_id = auth.uid());

create policy "borrar_propios" on comentarios_proyecto for delete
  using (autor_id = auth.uid());
```

**Auth:** Supabase Auth con email+password (admin invita usuarios desde el dashboard) o Google OAuth si todos tienen Google Workspace.

**Cambios en la app:**

1. Agregar `supabase-py` a `requirements.txt`.
2. Crear `auth.py` con un wrapper de login (form de email/password) que guarda la session en `st.session_state`.
3. Crear `comentarios.py` con helpers: `get_comentarios(bpin, fuente)`, `add_comentario(bpin, fuente, texto)`, `delete_comentario(id)`.
4. Bloquear el resto de la app con `if "user" not in st.session_state: render_login(); st.stop()`.
5. En cada vista de proyectos, agregar un `st.expander("Comentarios")` con la lista existente + un `st.form` para agregar uno nuevo.
6. Variables de entorno: `SUPABASE_URL`, `SUPABASE_ANON_KEY` (en Railway → Variables).

### Lo que el cliente preguntó (y respuestas dadas)

- **"¿Desde dónde doy permisos?"** → Supabase dashboard → Authentication (provider, lista de usuarios) + Database → Policies (RLS).
- **"¿Quién puede ver qué?"** → Cualquier logueado lee TODOS los comentarios, pero solo puede insertar/editar/borrar los suyos. Roles admin se manejan con `auth.users.raw_user_meta_data.role`.

---

## Cómo correr

### Local

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
2. **Hito 4 se muestra en MESES, no en días.** Internamente está en días.
3. **Hito 5 NO aplica a Descentralizadas.**
4. **La pestaña de Evaluación del modelo NO se afecta por el filtro de fecha de corte.**
5. **El export del Excel es GLOBAL** — no depende de la vista activa.
6. **La Guía es la pantalla por defecto** al entrar a la app.
7. **Sin emojis en el sidebar.** Sin degradés en KPIs.
8. **Reporte semanal solo cuenta semáforos NRN** (naranja/rojo/negro), no verde.

---

## Convenciones de código

- HTML inline en `st.markdown(unsafe_allow_html=True)` para tablas custom.
- CSS centralizado en `inject_css()` en constants.py.
- JS global (tooltips, toggle de contratos) en `components.html()` dentro de `inject_css()` — usa MutationObserver para reinit en cada rerender de Streamlit.
- Helpers de datos en `data.py` con `@st.cache_data` cuando sea seguro.
- Nombres de columnas Excel se referencian como strings literales — usar `.strip()` no es necesario porque el lector ya lo hace.
- Polars expressions: `pl.col(...)`, `pl.when().then().otherwise()`, `pl.lit()`.

---

## Archivos de referencia para entender el dominio

- `ReporteRegaliasHitos.ipynb` (en uploads) — notebook original del cliente con las fórmulas de cálculo de hitos. Fuente de verdad para la lógica.
- El Excel de Sucre (en uploads) — estructura real de los datos.
