"""
mapa.py
Visor tipo mapa de los proyectos de regalías de Sucre. Se renderiza como
una vista aparte (no es una pestaña dentro de otra vista). El visor usa
Leaflet.js embebido vía streamlit.components.v1.html — así evitamos
agregar dependencias adicionales (folium/streamlit-folium/pydeck) al
requirements.txt.

Diseño:
  • Tema oscuro inspirado en dashboards tipo City Manager.
  • Sidebar interno con filtros y resumen general.
  • Mapa central de Sucre con marcadores agrupados por municipio.
  • Pop-up por marcador mostrando el listado de proyectos.

Reglas de negocio:
  • Cada proyecto tiene una columna MUNICIPIOS con valores separados por
    coma (ej: "SINCELEJO, COROZAL, SAMPUÉS").
  • El valor "TODO EL DEPARTAMENTO DE SUCRE" significa cobertura
    departamental — el proyecto se replica en los 26 municipios.
  • Proyectos sin valor en MUNICIPIOS (null o vacío) se OMITEN del visor.
"""
import streamlit as st
import streamlit.components.v1 as components
import polars as pl
import json
import html
import re
import unicodedata

from constants import C


# ─────────────────────────────────────────────────────────────────────────────
# COORDENADAS — cabeceras municipales del Departamento de Sucre (Colombia)
# ─────────────────────────────────────────────────────────────────────────────
# Las claves se almacenan ya normalizadas (sin tildes, mayúsculas, trim).
MUNICIPIOS_SUCRE = {
    # Nombres oficiales DANE (coinciden 1:1 con MPIO_CNMBR del GeoJSON).
    # Subregión Sabanas
    "SINCELEJO":              (9.3047, -75.3978),
    "COROZAL":                (9.3211, -75.2939),
    "MORROA":                 (9.3406, -75.3097),
    "LOS PALMITOS":           (9.3792, -75.2675),
    "SAMPUES":                (9.1814, -75.3814),
    "SAN JUAN DE BETULIA":    (9.2667, -75.2417),
    "BUENAVISTA":             (9.3197, -74.9706),
    "SAN LUIS DE SINCE":      (9.2433, -75.1450),   # ex "Sincé"
    "SAN PEDRO":              (9.3956, -75.0567),
    "GALERAS":                (9.1639, -75.0497),
    "EL ROBLE":               (9.1014, -75.1003),
    # Subregión Montes de María
    "OVEJAS":                 (9.5247, -75.2294),
    "CHALAN":                 (9.5450, -75.3147),
    "COLOSO":                 (9.4961, -75.3531),
    # Subregión Golfo de Morrosquillo
    "SANTIAGO DE TOLU":       (9.5236, -75.5828),   # ex "Tolú"
    "SAN JOSE DE TOLUVIEJO":  (9.4500, -75.4400),   # ex "Toluviejo"
    "COVENAS":                (9.4011, -75.6800),
    "SAN ONOFRE":             (9.7361, -75.5283),
    "PALMITO":                (9.3372, -75.5358),   # ex "San Antonio de Palmito"
    # Subregión San Jorge
    "SAN MARCOS":             (8.6597, -75.1330),
    "SAN BENITO ABAD":        (8.9311, -75.0339),
    "CAIMITO":                (8.7892, -75.1144),
    "LA UNION":               (8.8500, -75.2833),
    # Subregión Mojana
    "SUCRE":                  (8.8094, -74.7211),
    "MAJAGUAL":               (8.5419, -74.6286),
    "GUARANDA":               (8.4675, -74.5378),
}

# Centro geográfico aproximado del departamento (para encuadre inicial)
CENTRO_DEPTO = (9.0, -75.10)
ZOOM_INICIAL = 9

# Indicador textual de "cobertura total"
SENTINEL_TODO_DEPTO = "TODO EL DEPARTAMENTO DE SUCRE"

# Colores por ESTADO PROYECTO (acordes a la paleta institucional)
ESTADO_COLORES = {
    "SIN CONTRATAR":                 "#f59e0b",  # ámbar
    "CONTRATADO SIN ACTA DE INICIO": "#3b82f6",  # azul
    "CONTRATADO EN EJECUCIÓN":       "#10b981",  # verde
    "TERMINADO":                     "#9ca3af",  # gris
    "PARA CIERRE":                   "#8b5cf6",  # violeta
    "SUSPENDIDO":                    "#ef4444",  # rojo
}
COLOR_DEFAULT = "#64748b"

# Etiquetas amigables por fuente
FUENTES_LABEL = {
    "departamento":    "Departamento",
    "descentralizadas":"Descentralizadas",
    "municipios":      "Municipios",
}


# ─────────────────────────────────────────────────────────────────────────────
# NORMALIZACIÓN
# ─────────────────────────────────────────────────────────────────────────────
def _strip_acentos(s: str) -> str:
    """Elimina tildes y diacríticos para hacer match robusto de nombres."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c))


# Aliases coloquiales → nombre DANE oficial. Permite que el Excel siga
# funcionando aunque algún proyecto traiga el nombre corto/histórico.
# El match se hace después de _strip_acentos + upper + trim.
_ALIAS_MUNICIPIO = {
    "SINCE":                  "SAN LUIS DE SINCE",
    "SAN LUIS SINCE":         "SAN LUIS DE SINCE",
    "TOLU":                   "SANTIAGO DE TOLU",
    "TOLU VIEJO":             "SAN JOSE DE TOLUVIEJO",
    "TOLUVIEJO":              "SAN JOSE DE TOLUVIEJO",
    "SAN ANTONIO DE PALMITO": "PALMITO",
}


def _norm_municipio(s) -> str:
    """Normaliza un nombre de municipio: trim + mayúsculas + sin tildes + sin
    puntos. Aplica además aliases coloquiales → DANE oficial. Devuelve
    string vacío si la entrada es None/vacía."""
    if s is None:
        return ""
    txt = str(s).strip()
    if not txt:
        return ""
    txt = _strip_acentos(txt).upper()
    # eliminar puntos y caracteres redundantes
    txt = re.sub(r"\s+", " ", txt).strip(" .")
    # mapear nombre coloquial → DANE si aplica
    return _ALIAS_MUNICIPIO.get(txt, txt)


# Lista normalizada de TODOS los municipios (nombres DANE oficiales) para
# replicar "TODO EL DEPARTAMENTO DE SUCRE".
_TODOS_MUNICIPIOS_NORM = list(dict.fromkeys([
    "SINCELEJO", "COROZAL", "MORROA", "LOS PALMITOS", "SAMPUES",
    "SAN JUAN DE BETULIA", "BUENAVISTA", "SAN LUIS DE SINCE", "SAN PEDRO",
    "GALERAS", "EL ROBLE", "OVEJAS", "CHALAN", "COLOSO",
    "SANTIAGO DE TOLU", "SAN JOSE DE TOLUVIEJO", "COVENAS", "SAN ONOFRE",
    "PALMITO", "SAN MARCOS", "SAN BENITO ABAD", "CAIMITO", "LA UNION",
    "SUCRE", "MAJAGUAL", "GUARANDA",
]))


def _parse_municipios_cell(valor) -> list:
    """
    Recibe el contenido de la columna MUNICIPIOS de un proyecto y devuelve
    una lista de nombres normalizados de municipios.

    • None / vacío → []  (proyecto omitido)
    • "TODO EL DEPARTAMENTO DE SUCRE" → expande a los 26 municipios
    • "SINCELEJO, COROZAL" → ["SINCELEJO", "COROZAL"]
    """
    if valor is None:
        return []
    txt = str(valor).strip()
    if not txt:
        return []

    # Separar por coma (a veces vienen con ; o /)
    crudos = re.split(r"[,;/]+", txt)
    nombres = []
    expandir_todos = False
    for nombre in crudos:
        nm = _norm_municipio(nombre)
        if not nm:
            continue
        if nm == SENTINEL_TODO_DEPTO:
            expandir_todos = True
            continue
        nombres.append(nm)

    if expandir_todos:
        # Replicar en TODOS los municipios. Si además del marcador "todo el
        # departamento" venían municipios específicos, los unimos sin duplicar.
        union = list(dict.fromkeys(_TODOS_MUNICIPIOS_NORM + nombres))
        return union

    return nombres


def _resolver_coord(nombre_norm: str):
    """Devuelve (lat, lng) para un municipio normalizado, o None si no se
    reconoce."""
    return MUNICIPIOS_SUCRE.get(nombre_norm)


# ─────────────────────────────────────────────────────────────────────────────
# RECOLECCIÓN DE PROYECTOS DESDE LOS 3 DATAFRAMES
# ─────────────────────────────────────────────────────────────────────────────
def _bpin_str(v):
    if v is None:
        return ""
    try:
        return str(int(float(v))) if isinstance(v, (int, float)) else str(v).strip()
    except Exception:
        return str(v).strip()


def _coalesce(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _proyecto_desde_fila(row: dict, fuente: str) -> dict:
    """Construye el dict canónico de un proyecto desde una fila de cualquier
    fuente (depto / descent / municipios)."""
    nom    = _coalesce(row, "NOMBRE PROYECTO", "NOMBRE DEL PROYECTO") or "(Sin nombre)"
    entidad = _coalesce(row, "ENTIDAD O SECRETARIA", "EJECUTOR") or "(Sin entidad)"
    estado = (_coalesce(row, "ESTADO PROYECTO") or "").strip().upper() or "(Sin estado)"
    sector = _coalesce(row, "SECTOR")
    af     = _coalesce(row, "AVANCE FISICO", "AVANCE FÍSICO")
    afn    = _coalesce(row, "AVANCE FINANCIERO")

    def _pct(v):
        if v is None: return None
        try:
            f = float(v)
            if f <= 1.0001: f *= 100
            return round(f, 1)
        except Exception:
            return None

    return {
        "bpin":     _bpin_str(_coalesce(row, "BPIN")),
        "nombre":   str(nom)[:300],
        "entidad":  str(entidad)[:120],
        "estado":   estado,
        "sector":   (str(sector)[:80] if sector else None),
        "avance_fisico":     _pct(af),
        "avance_financiero": _pct(afn),
        "fuente":   fuente,
    }


def _detectar_col_municipios(cols) -> str:
    """Devuelve el nombre real de la columna de municipios que aparezca en
    `cols`. Acepta varias variantes que se han visto en archivos del cliente."""
    candidatos = [
        "MUNICIPIOS",
        "MUNICIPIO",
        "MUNICIPIOS BENEFICIADOS",
        "MUNICIPIO BENEFICIADO",
        "MUNICIPIOS BENEFICIARIOS",
        "MUNICIPIO BENEFICIARIO",
    ]
    cols_upper = {str(c).strip().upper(): c for c in cols}
    for c in candidatos:
        if c in cols_upper:
            return cols_upper[c]
    # Búsqueda flexible: cualquier columna que contenga "MUNICIPI"
    for c in cols:
        if "MUNICIPI" in str(c).upper():
            return c
    return None


def _clasificar_impacto(municipios: list) -> str:
    """
    Clasifica el alcance del proyecto en función del número de municipios a los
    que apunta. La lista de entrada ya viene normalizada y, en el caso de
    «TODO EL DEPARTAMENTO DE SUCRE», ya está expandida a los 26 municipios.

      • Departamental → llega a TODOS los municipios del departamento (26).
      • Subregional   → llega a más de un municipio pero no a todos.
      • Municipal     → llega a un único municipio.
    """
    if not municipios:
        return None
    n_unicos = len(set(municipios))
    if n_unicos >= len(_TODOS_MUNICIPIOS_NORM):
        return "Departamental"
    if n_unicos > 1:
        return "Subregional"
    return "Municipal"


def _recolectar_proyectos(df_depto, df_descent, df_municipios):
    """
    Itera los 3 DataFrames y devuelve una lista plana de tuplas
    (proyecto_dict, [municipios_normalizados]).
    Omite proyectos sin MUNICIPIOS.
    """
    salida = []
    diag   = []   # diagnóstico para mostrar al usuario si no hay datos
    fuentes = [
        (df_depto,      "departamento"),
        (df_descent,    "descentralizadas"),
        (df_municipios, "municipios"),
    ]
    for df, fuente in fuentes:
        if df is None or df.height == 0:
            diag.append(f"{fuente}: sin datos")
            continue
        col_mun = _detectar_col_municipios(df.columns)
        if not col_mun:
            diag.append(f"{fuente}: no se encontró columna de municipios "
                        f"(columnas disponibles: {list(df.columns)[:6]}…)")
            continue
        # Filtrar in-polars para minimizar el to_dicts(): solo filas con municipios
        try:
            df_f = df.filter(
                pl.col(col_mun).is_not_null() &
                (pl.col(col_mun).cast(pl.Utf8).str.strip_chars() != "")
            )
        except Exception:
            df_f = df
        n_con_mun = 0
        for r in df_f.to_dicts():
            municipios = _parse_municipios_cell(r.get(col_mun))
            if not municipios:
                continue
            p = _proyecto_desde_fila(r, fuente)
            p["impacto"] = _clasificar_impacto(municipios)
            salida.append((p, municipios))
            n_con_mun += 1
        diag.append(f"{fuente}: {df.height} filas, columna «{col_mun}», "
                    f"{n_con_mun} con municipio válido")
    return salida, diag


# ─────────────────────────────────────────────────────────────────────────────
# AGRUPACIÓN POR MUNICIPIO
# ─────────────────────────────────────────────────────────────────────────────
def _agrupar_por_municipio(proyectos_con_munic):
    """
    Devuelve dict {municipio_norm: {"lat":, "lng":, "proyectos":[...], "no_geo":bool}}.
    Los municipios no reconocidos (sin coordenada) van a un bucket especial
    'NO_GEOCODIFICADO' (no se muestran en el mapa pero sí en el panel lateral).
    """
    grupos = {}
    no_geo = []
    for p, municipios in proyectos_con_munic:
        for m in municipios:
            coord = _resolver_coord(m)
            if coord is None:
                no_geo.append((m, p))
                continue
            if m not in grupos:
                grupos[m] = {
                    "lat": coord[0], "lng": coord[1],
                    "nombre": m.title(),  # presentación: Title Case
                    "proyectos": [],
                }
            grupos[m]["proyectos"].append(p)
    return grupos, no_geo


# ─────────────────────────────────────────────────────────────────────────────
# GEOJSON — contorno de los municipios de Sucre (DANE, simplificado a ~178 KB)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _cargar_geojson_sucre() -> dict:
    """Lee el GeoJSON con los polígonos de los 26 municipios de Sucre.
    Devuelve {} si el archivo no existe (la app sigue funcionando sin contornos)."""
    import os
    ruta = os.path.join(os.path.dirname(__file__), "Sucre.geojson")
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# RENDER PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────
def render_mapa(df_depto, df_descent, df_municipios):
    """Renderiza la vista 'Mapa' como un componente HTML+Leaflet a pantalla
    completa, con tema oscuro y sidebar interno."""

    # CSS específico de la vista Mapa:
    #   1) Romper el block-container de Streamlit para usar todo el viewport.
    #   2) Colapsar la barra lateral nativa de Streamlit (el visor tiene su
    #      propio sidebar interno con los mismos filtros). El usuario puede
    #      reabrirla con el botón « del toggle de Streamlit cuando necesite
    #      cambiar de vista o subir un archivo.
    #   3) Bloquear el scroll vertical de la página — el mapa queda fijo
    #      ocupando el viewport, sin barras de scroll en el contenedor padre.
    # CSS de la vista Mapa.
    # Estrategia: en lugar de pelear con Streamlit por la altura del iframe,
    # lo sacamos del flujo del documento con position:fixed e inset:0. Así
    # el iframe SIEMPRE ocupa 100vw × 100vh del viewport del navegador,
    # responsive automático al zoom in/out, sin franjas blancas posibles.
    # (Casi todo este CSS también se inyecta desde app.py ANTES de render_mapa
    #  para evitar el flash del header de Streamlit; se duplica aquí por si
    #  alguien llama render_mapa directo.)
    st.markdown("""
    <style>
    /* ── Fondo oscuro en TODOS los ancestros (evita franjas blancas) ─── */
    html, body,
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"],
    section.main {
        background: #0b1220 !important;
        overflow: hidden !important;
    }

    /* ── Ocultar el header/toolbar de Streamlit en esta vista ────────── */
    header[data-testid="stHeader"],
    div[data-testid="stHeader"],
    [data-testid="stAppHeader"],
    header.stAppHeader,
    .stAppHeader,
    [data-testid="stDecoration"],
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    [data-testid="stDeployButton"],
    [data-testid="manage-app-button"],
    [data-testid="stHeaderActionElements"] {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        visibility: hidden !important;
    }

    /* Toggle para reabrir el sidebar nativo: SIEMPRE visible y encima del iframe */
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
        z-index: 1000002 !important;
    }
    /* Sidebar nativo: oscuro y por encima del iframe cuando se abre */
    section[data-testid="stSidebar"] {
        background: #0f172a !important;
        z-index: 1000001 !important;
    }

    /* ── Block-container sin padding ni márgenes ────────────────────── */
    section.main > div.block-container,
    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="stMainBlockContainer"] {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        width: 100% !important;
        height: 100vh !important;
        overflow: hidden !important;
        background: #0b1220 !important;
    }

    /* ── EL IFRAME: position:fixed total = full viewport siempre ────── */
    /* Se aplica al wrapper que Streamlit pone alrededor del iframe... */
    div[data-testid="stIFrame"] {
        position: fixed !important;
        top: 0 !important; left: 0 !important;
        right: 0 !important; bottom: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        z-index: 1 !important;
        margin: 0 !important; padding: 0 !important;
        overflow: hidden !important;
        background: #0b1220 !important;
    }
    /* ... y al iframe en sí, para que ocupe el 100% de ese wrapper. */
    div[data-testid="stIFrame"] iframe,
    iframe[title^="streamlit_app.components"],
    iframe[title*="components.v1.html"] {
        width: 100% !important;
        height: 100% !important;
        min-width: 100% !important; min-height: 100% !important;
        max-width: 100% !important; max-height: 100% !important;
        border: 0 !important;
        margin: 0 !important; padding: 0 !important;
        display: block !important;
        background: #0b1220 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1) Recolectar proyectos
    proyectos_con_munic, diagnostico = _recolectar_proyectos(df_depto, df_descent, df_municipios)
    grupos, no_geo = _agrupar_por_municipio(proyectos_con_munic)

    # Si no hay nada que mostrar, advertir al usuario con info útil.
    if not proyectos_con_munic:
        st.markdown(
            f"""
            <div style="background:#0f172a;border:1px solid #1e293b;border-radius:12px;
                        padding:1.2rem 1.4rem;color:#e5e7eb;margin:1rem">
                <div style="font-weight:800;color:#fff;margin-bottom:0.5rem">
                    El mapa no tiene proyectos para mostrar
                </div>
                <div style="font-size:0.83rem;color:#94a3b8;margin-bottom:0.8rem">
                    No se encontró la columna <code>MUNICIPIOS</code> en ninguna de las tablas,
                    o ninguna fila tiene un municipio válido registrado.
                </div>
                <div style="font-size:0.78rem;color:#cbd5e1;line-height:1.6">
                    {"<br>".join(f"• {d}" for d in diagnostico)}
                </div>
                <div style="margin-top:0.9rem;font-size:0.75rem;color:#94a3b8">
                    Verifica que el archivo Excel tenga la columna
                    <code>MUNICIPIOS</code> en alguna de las tres tablas
                    (Departamento, Descentralizadas o Municipios), con los
                    nombres de los municipios separados por coma. Para cobertura
                    total usa el texto <code>TODO EL DEPARTAMENTO DE SUCRE</code>.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # 2) Métricas globales — DEDUPLICADAS por BPIN
    # Un proyecto puede aparecer en N municipios (p. ej., los que tienen
    # impacto departamental cubren los 26 municipios de Sucre). Para que los
    # KPIs muestren la cantidad REAL de proyectos únicos, agrupamos por BPIN.
    # OJO: los conteos por municipio en los marcadores SÍ se mantienen como
    # apariciones (un proyecto departamental cuenta en cada municipio).
    proyectos_unicos = {}  # bpin -> proyecto (toma la primera ocurrencia)
    for g in grupos.values():
        for p in g["proyectos"]:
            bpin = p.get("bpin") or ""
            if bpin and bpin not in proyectos_unicos:
                proyectos_unicos[bpin] = p
    for _muni, p in no_geo:   # no_geo = lista de tuplas (municipio, proyecto)
        bpin = p.get("bpin") or ""
        if bpin and bpin not in proyectos_unicos:
            proyectos_unicos[bpin] = p

    total_proy   = len(proyectos_unicos)            # ← cantidad ÚNICA
    total_munic  = len(grupos)
    # Total de apariciones (suma cruda) — útil para "Información clave"
    total_apariciones = sum(len(g["proyectos"]) for g in grupos.values()) + len(no_geo)

    # Avances promedio y conteos por estado/sector — sobre proyectos únicos
    avances_f, avances_fin = [], []
    estados_count = {}
    sectores_count = {}
    for p in proyectos_unicos.values():
        if p["avance_fisico"]     is not None: avances_f.append(p["avance_fisico"])
        if p["avance_financiero"] is not None: avances_fin.append(p["avance_financiero"])
        estados_count[p["estado"]] = estados_count.get(p["estado"], 0) + 1
        if p["sector"]:
            sectores_count[p["sector"]] = sectores_count.get(p["sector"], 0) + 1
    av_f_prom   = round(sum(avances_f)/len(avances_f), 1) if avances_f else None
    av_fin_prom = round(sum(avances_fin)/len(avances_fin), 1) if avances_fin else None

    # 3) Datos para el front (JSON serializable)
    marcadores = []
    for m_norm, g in grupos.items():
        marcadores.append({
            "id":       m_norm,
            "nombre":   g["nombre"],
            "lat":      g["lat"],
            "lng":      g["lng"],
            "n":        len(g["proyectos"]),
            "proyectos": g["proyectos"],
        })

    # Ordenar marcadores por nombre para el listado lateral.
    marcadores.sort(key=lambda x: x["nombre"])

    # Conteo de proyectos por municipio normalizado (para colorear polígonos
    # del GeoJSON). Cada proyecto cuenta una sola vez por municipio.
    proy_por_muni = {m["id"]: m["n"] for m in marcadores}

    payload = {
        "centro":      list(CENTRO_DEPTO),
        "zoom":        ZOOM_INICIAL,
        "marcadores":  marcadores,
        "estados":     ESTADO_COLORES,
        "default":     COLOR_DEFAULT,
        "fuentes":     FUENTES_LABEL,
        "total_proy":  total_proy,
        "total_apariciones": total_apariciones,
        "total_munic": total_munic,
        "avance_fisico_prom":     av_f_prom,
        "avance_financiero_prom": av_fin_prom,
        "estados_count":  estados_count,
        "sectores_count": sectores_count,
        "no_geo_count": len(no_geo),
        "proy_por_muni": proy_por_muni,
    }

    # 4) HTML + Leaflet embebido
    payload_json = json.dumps(payload, ensure_ascii=False)
    geojson_sucre = _cargar_geojson_sucre()
    geojson_json  = json.dumps(geojson_sucre, ensure_ascii=False,
                               separators=(",", ":"))
    componente_html = _construir_componente_html(payload_json, geojson_json)

    # Altura ajustada al viewport típico de laptop (~900px). Un valor mayor
    # haría que la parte inferior del sidebar (con la sección "Estados") quede
    # fuera del área visible y, como el contenedor padre tiene overflow:hidden,
    # el usuario no podría hacer scroll. Con 850 el sidebar interno
    # (overflow-y:auto) puede scrollear su contenido cómodamente.
    components.html(componente_html, height=850, scrolling=False)


def _construir_componente_html(payload_json: str, geojson_json: str) -> str:
    """
    HTML+CSS+JS auto-contenido. Recibe payload + geojson ya serializados a JSON.

    Layout:
      ┌──────────┬────────────────────────────────────────┐
      │ sidebar  │             mapa                       │
      │ (filtros │   ┌──────── info panel ─────────────┐  │
      │  +      │   │ resumen, leyenda, etc.          │  │
      │  resumen)│   └─────────────────────────────────┘  │
      └──────────┴────────────────────────────────────────┘
    """
    # Cuidado: usar .replace en lugar de f-string aquí, porque el JS está
    # lleno de llaves y backticks que confundirían a Python.
    return (_TEMPLATE_HTML
            .replace("__PAYLOAD__", payload_json)
            .replace("__GEOJSON__", geojson_json))


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE HTML — Leaflet desde CDN, tema oscuro, sidebar y panel info.
# ─────────────────────────────────────────────────────────────────────────────
_TEMPLATE_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html, body { margin:0; padding:0; width:100%; height:100%; font-family: 'Montserrat', sans-serif;
               background:#0b1220; color:#e5e7eb; overflow: hidden;
               -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
  /* Layout: usa 100% del iframe (NO min-height fijo). Antes tenía
     min-height: 820px que en zoom out provocaba desbordamiento — el .main
     se extendía debajo del área visible y la leyenda (position:absolute con
     bottom:16px) quedaba fuera del viewport. */
  .layout { display:flex; width:100%; height:100%; min-height:0; }

  /* ── SIDEBAR ──────────────────────────────────────────────────────── */
  .sidebar {
    width: 290px; min-width:290px; background:#0f172a; border-right:1px solid #1e293b;
    display:flex; flex-direction:column;
    /* Scroll vertical garantizado: la altura sigue al iframe (100% del padre,
       no 100vh — esto evita peleas con cambios de zoom). El overflow:auto
       deja que el contenido (Resumen + Estados) sea accesible por scroll
       sin recortar nada cuando el viewport es pequeño. */
    height: 100%; max-height: 100%;
    overflow-y: auto !important; overflow-x: hidden;
    scrollbar-width: thin;
    scrollbar-color: #334155 #0b1220;
  }
  .sidebar > * { min-width: 0; flex-shrink: 0; }  /* hijos no se comprimen, scroll funciona */
  /* Scrollbar visible y notorio en el sidebar para que el usuario sepa que hay más contenido */
  .sidebar::-webkit-scrollbar { width: 8px; }
  .sidebar::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
  .sidebar::-webkit-scrollbar-thumb:hover { background: #475569; }
  .side-header {
    padding: 12px 16px 12px; border-bottom: 1px solid #1e293b;
    display:flex; gap:10px; align-items:center;
  }
  .side-logo {
    width: 32px; height: 32px; border-radius:8px;
    background: linear-gradient(135deg, #2563eb, #06b6d4);
    display:flex; align-items:center; justify-content:center; flex-shrink:0;
    font-weight:800; color:#fff; font-size:0.95rem;
  }
  .side-title { font-size:0.88rem; font-weight:700; color:#fff; line-height:1.15; }
  .side-sub   { font-size:0.65rem; color:#94a3b8; line-height:1.3; margin-top:2px; }

  .side-section-title {
    text-transform: uppercase; font-size:0.6rem; letter-spacing: 1.0px;
    color:#60a5fa; font-weight:700; padding: 10px 16px 5px;
  }
  .side-search-wrap { padding: 0 16px 8px; }
  .side-search {
    width: 100%; box-sizing: border-box;
    background:#0b1220; border:1px solid #1e293b;
    color:#e5e7eb; padding: 6px 9px; border-radius:7px;
    font-size:0.74rem; outline:none;
  }
  .side-search:focus { border-color:#3b82f6; }
  .filtro-wrap { position: relative; box-sizing: border-box; width: 100%; }
  .filtro-wrap, .filtro-wrap * { box-sizing: border-box; }

  .side-filters { padding: 0 16px 4px; display:flex; flex-direction:column; gap:6px; }
  .side-select {
    width:100%; box-sizing: border-box;
    background:#0b1220; border:1px solid #1e293b; color:#e5e7eb;
    padding: 6px 9px; border-radius:7px; font-size:0.74rem; outline:none;
    appearance: none;
    text-overflow: ellipsis; overflow: hidden; white-space: nowrap;
  }
  .side-select option { background:#0b1220; color:#e5e7eb; }

  /* — Tooltip por filtro: estilo del nodo flotante creado por JS — */
  .filtro-tip {
    position: fixed;
    width: 260px;
    background: #1e293b;
    color: #f1f5f9;
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid #334155;
    font-size: 0.72rem;
    line-height: 1.45;
    font-weight: 500;
    white-space: normal;
    text-transform: none; letter-spacing: 0;
    pointer-events: none;
    opacity: 0;
    transform: translateX(-6px);
    transition: opacity 0.18s ease, transform 0.18s ease;
    z-index: 100000;
    box-shadow: 0 8px 24px rgba(0,0,0,0.55),
                0 0 0 1px rgba(96,165,250,0.10);
  }
  .filtro-tip.is-visible { opacity: 1; transform: translateX(0); }
  .filtro-tip::before {
    content: '';
    position: absolute;
    left: -12px; top: 50%;
    transform: translateY(-50%);
    border: 6px solid transparent;
    border-right-color: #1e293b;
  }

  /* — Bloque destacado del filtro de Impacto — */
  .impacto-block {
    margin: 4px 16px 4px;
    padding: 7px 10px 9px;
    background: linear-gradient(135deg, rgba(96,165,250,0.10), rgba(6,182,212,0.05));
    border: 1px solid rgba(96,165,250,0.35);
    border-left: 3px solid #60a5fa;
    border-radius: 9px;
    box-shadow: 0 0 0 1px rgba(96,165,250,0.08), 0 4px 12px rgba(15,23,42,0.55);
  }
  .impacto-label {
    display: flex; align-items: center; gap: 7px;
    font-size: 0.58rem; text-transform: uppercase; letter-spacing: 1.0px;
    color: #93c5fd; font-weight: 800; margin-bottom: 5px;
  }
  .pulse-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #60a5fa;
    box-shadow: 0 0 0 0 rgba(96,165,250,0.7);
    animation: pulse-blue 2s infinite;
    flex-shrink: 0;
  }
  @keyframes pulse-blue {
    0%   { box-shadow: 0 0 0 0   rgba(96,165,250,0.7); }
    70%  { box-shadow: 0 0 0 7px rgba(96,165,250,0);   }
    100% { box-shadow: 0 0 0 0   rgba(96,165,250,0);   }
  }
  .side-select.is-emphasized {
    border-color: #3b82f6;
    background: #0b1326;
    font-weight: 600;
    color: #fff;
  }
  .side-select.is-emphasized:focus {
    border-color: #60a5fa;
    box-shadow: 0 0 0 3px rgba(96,165,250,0.25);
  }

  .resumen-grid {
    padding: 2px 16px 10px;
    display:grid; grid-template-columns: 1fr 1fr; gap: 6px;
  }
  .res-card {
    background:#0b1220; border:1px solid #1e293b; border-radius:8px;
    padding: 6px 8px; display:flex; gap:7px; align-items:center;
    min-width: 0; overflow: hidden;
  }
  .res-card > div:nth-child(2) {
    min-width: 0; flex: 1 1 auto;
  }
  .res-icon {
    width:24px; height:24px; border-radius:6px;
    display:flex; align-items:center; justify-content:center;
    font-weight:800; color:#fff; flex-shrink:0; font-size:0.75rem;
  }
  .res-num {
    font-size:0.85rem; font-weight:800; color:#fff; line-height:1.1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .res-lbl {
    font-size:0.54rem; color:#94a3b8; margin-top:2px;
    text-transform:uppercase; letter-spacing:0.4px; line-height:1.15;
    overflow: hidden; word-break: break-word;
  }

  /* ── MAPA ─────────────────────────────────────────────────────────── */
  /* min-height:0 indispensable en flex-children para que respeten el
     contenedor padre sin desbordarse (importante en zoom out). */
  .main { flex:1; position:relative; height:100%; min-height:0; overflow:hidden; }
  #map { width:100%; height:100%; background:#0b1220; }

  /* — Capa GeoJSON de municipios — */
  .leaflet-tooltip.geo-tip {
    background: rgba(15, 23, 42, 0.92);
    color: #e2e8f0;
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 11.5px;
    font-weight: 500;
    box-shadow: 0 4px 10px rgba(0,0,0,0.35);
  }
  .leaflet-tooltip.geo-tip::before { display:none; }
  .leaflet-tooltip.geo-tip .geo-tip-n {
    display:block;
    color: #93c5fd;
    font-size: 10.5px;
    margin-top: 2px;
    font-weight: 400;
  }

  /* ── PANEL INFO (esquina sup. derecha del mapa) ──────────────────── */
  .info-panel {
    position:absolute; top: 16px; right: 16px; z-index: 600;
    width: 260px; background: rgba(15,23,42,0.92);
    border:1px solid #1e293b; border-radius:12px; padding: 12px 14px;
    box-shadow: 0 8px 28px rgba(0,0,0,0.5);
    backdrop-filter: blur(6px);
    /* Tope de alto: deja espacio reservado para la leyenda inferior. */
    max-height: calc(100% - 220px);
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: thin;
    scrollbar-color: #334155 #0b1220;
  }
  .info-panel::-webkit-scrollbar { width: 6px; }
  .info-panel::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
  .info-title {
    font-size:0.68rem; text-transform:uppercase; color:#60a5fa;
    letter-spacing:1.1px; font-weight:700; margin-bottom:10px;
  }
  .info-row { display:flex; gap:10px; padding: 6px 0; align-items:center;
              border-top: 1px dashed #1e293b; }
  .info-row:first-of-type { border-top: none; padding-top: 2px; }
  .info-row .info-ico {
    width:26px; height:26px; border-radius:6px;
    display:flex; align-items:center; justify-content:center; color:#fff;
    font-weight:700; font-size:0.85rem;
  }
  .info-row .info-val { font-size:0.95rem; font-weight:800; color:#fff; line-height:1; }
  .info-row .info-lbl { font-size:0.66rem; color:#94a3b8; margin-top:3px; }
  .info-nota {
    display:none;
    margin-top: 10px;
    padding: 8px 10px;
    background: rgba(96,165,250,0.08);
    border-left: 2px solid #60a5fa;
    border-radius: 4px;
    font-size: 0.65rem;
    color: #cbd5e1;
    line-height: 1.4;
  }

  .leyenda {
    position:absolute; bottom: 16px; right: 16px; z-index: 600;
    background: rgba(15,23,42,0.92); border:1px solid #1e293b; border-radius:12px;
    padding: 12px 14px; box-shadow: 0 8px 28px rgba(0,0,0,0.5);
    backdrop-filter: blur(6px);
    /* Tope de alto: nunca pasa el 40% del .main para no chocar con el
       info-panel (arriba a la derecha) ni desbordar si el iframe queda
       pequeño en pantallas comprimidas. */
    max-height: calc(100% - 220px);
    max-width: 240px;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: thin;
    scrollbar-color: #334155 #0b1220;
  }
  .leyenda::-webkit-scrollbar { width: 6px; }
  .leyenda::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
  .leyenda-title {
    font-size:0.68rem; text-transform:uppercase; color:#60a5fa;
    letter-spacing:1.1px; font-weight:700; margin-bottom:8px;
    position: sticky; top: 0; background: rgba(15,23,42,0.92);
  }
  .ley-row { display:flex; align-items:center; gap:8px; font-size:0.75rem; margin: 3px 0; color:#cbd5e1; }
  .ley-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }

  /* ── MARCADORES PERSONALIZADOS ───────────────────────────────────── */
  .mun-marker {
    width:34px; height:34px; border-radius:50%;
    border:3px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.55);
    display:flex; align-items:center; justify-content:center;
    font-weight:800; color:#fff; font-size:0.78rem;
  }
  .mun-marker.size-l { width:42px; height:42px; font-size:0.9rem; }
  .mun-marker.size-m { width:36px; height:36px; font-size:0.78rem; }
  .mun-marker.size-s { width:30px; height:30px; font-size:0.68rem; }

  /* ── POPUP ──────────────────────────────────────────────────────── */
  .leaflet-popup-content-wrapper {
    background:#0f172a; color:#e5e7eb; border-radius:10px;
    border:1px solid #1e293b;
  }
  .leaflet-popup-tip { background:#0f172a; }
  .pop-title  { font-size:0.85rem; font-weight:800; color:#fff; margin-bottom:6px; }
  .pop-sub    { font-size:0.7rem; color:#94a3b8; margin-bottom:8px; }
  .pop-list {
    max-height: 220px; overflow-y:auto; padding-right: 4px;
  }
  .pop-item {
    border-top:1px solid #1e293b; padding: 6px 0; font-size:0.72rem; line-height:1.35;
  }
  .pop-item:first-child { border-top:none; padding-top: 0; }
  .pop-item .pop-bpin { color:#60a5fa; font-weight:700; font-family: 'DM Mono', monospace; }
  .pop-item .pop-est  {
    display:inline-block; padding: 1px 7px; border-radius:10px; font-size:0.62rem;
    font-weight:700; margin-left:6px; color:#fff;
  }
  .pop-item .pop-nom { color:#e5e7eb; margin-top:3px; }
  .pop-item .pop-meta { color:#94a3b8; margin-top:3px; font-size:0.65rem; }

  /* Cluster oscuro */
  .marker-cluster {
    background-color: rgba(37, 99, 235, 0.5);
  }
  .marker-cluster div {
    background-color: rgba(37, 99, 235, 0.9);
    color: #fff; font-weight:800;
  }
  /* Scrollbar oscura */
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: #0b1220; }
  ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: #334155; }

  /* Filtros chips inferior del sidebar */
  .estados-mini {
    padding: 0 16px 10px;
    display:flex; flex-wrap: wrap; gap: 5px;
  }
  .estado-chip {
    font-size:0.58rem; padding:3px 7px; border-radius:11px;
    background:#0b1220; border:1px solid #1e293b; color:#cbd5e1;
    display:inline-flex; align-items:center; gap:4px; cursor:default;
    max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .estado-chip .dot { width:7px; height:7px; border-radius:50%; flex-shrink: 0; }
  .estado-chip .n   { color:#fff; font-weight:700; flex-shrink: 0; }
  .estado-chip .lbl {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 160px;
  }

  .footer-note {
    margin-top:auto; padding: 8px 16px 10px;
    font-size:0.58rem; color:#475569; border-top: 1px solid #1e293b;
    word-wrap: break-word; overflow-wrap: break-word;
  }
  .footer-note strong { color: #94a3b8; }

  /* ── RESPONSIVE: alturas pequeñas (laptop, zoom in) ────────────────
     Cuando el viewport es bajito, el sidebar tiene demasiado contenido
     vertical. Compactamos aún más los espacios para reducir la necesidad
     de scroll y permitir que los Estados queden visibles sin moverse. */
  @media (max-height: 800px) {
    .side-header { padding: 9px 14px; gap: 8px; }
    .side-logo { width: 28px; height: 28px; font-size: 0.85rem; }
    .side-title { font-size: 0.82rem; }
    .side-sub { font-size: 0.6rem; }
    .side-section-title { padding: 7px 14px 3px; font-size: 0.55rem; }
    .side-search-wrap { padding: 0 14px 5px; }
    .side-filters { padding: 0 14px 2px; gap: 4px; }
    .side-search, .side-select { padding: 5px 8px; font-size: 0.7rem; }
    .impacto-block { margin: 2px 14px 2px; padding: 5px 8px 7px; }
    .resumen-grid { padding: 2px 14px 6px; gap: 4px; }
    .res-card { padding: 4px 6px; gap: 5px; }
    .res-icon { width: 20px; height: 20px; font-size: 0.65rem; }
    .res-num { font-size: 0.75rem; }
    .res-lbl { font-size: 0.5rem; }
    .estados-mini { padding: 0 14px 6px; gap: 4px; }
    .estado-chip { font-size: 0.55rem; padding: 2px 6px; }
    .footer-note { padding: 5px 14px 7px; font-size: 0.55rem; }
  }
  @media (max-height: 650px) {
    /* En alturas MUY pequeñas, ocultar el footer-note y compactar más */
    .footer-note { display: none; }
    .side-header { padding: 7px 12px; }
    .side-logo { width: 24px; height: 24px; font-size: 0.75rem; }
    .resumen-grid { grid-template-columns: 1fr 1fr 1fr 1fr; }
    .res-card { flex-direction: column; align-items: flex-start; gap: 2px; }
    .res-icon { width: 18px; height: 18px; }
    .res-lbl { font-size: 0.45rem; line-height: 1.05; }
  }
</style>
</head>
<body>
<div class="layout">

  <!-- ============ SIDEBAR ============ -->
  <aside class="sidebar">
    <div class="side-header">
      <div class="side-logo">SR</div>
      <div>
        <div class="side-title">Mapa de regalías</div>
        <div class="side-sub">Visor de proyectos · Sucre</div>
      </div>
    </div>

    <div class="side-section-title">Búsqueda</div>
    <div class="side-search-wrap">
      <div class="filtro-wrap" data-tip="Filtra proyectos cuyo BPIN o nombre contenga el texto que escribas. Buscador en vivo, no distingue mayúsculas.">
        <input id="f-buscar" class="side-search" placeholder="Buscar por BPIN o nombre…" />
      </div>
    </div>

    <div class="side-section-title">Filtros rápidos</div>
    <div class="side-filters">
      <div class="filtro-wrap" data-tip="Filtra por la tabla de origen del proyecto: Departamento (matriz de seguimiento), Descentralizadas u Otros municipios.">
        <select id="f-fuente" class="side-select">
          <option value="">Todas las fuentes</option>
        </select>
      </div>
      <div class="filtro-wrap" data-tip="Filtra por la entidad o secretaría responsable (Departamento) o el ejecutor (Descentralizadas / Municipios).">
        <select id="f-entidad" class="side-select">
          <option value="">Todas las entidades / ejecutores</option>
        </select>
      </div>
      <div class="filtro-wrap" data-tip="Filtra por el estado del proyecto: Sin contratar, Contratado sin acta, En ejecución, Terminado, Para cierre o Suspendido.">
        <select id="f-estado" class="side-select">
          <option value="">Todos los estados</option>
        </select>
      </div>
      <div class="filtro-wrap" data-tip="Filtra por el sector al que pertenece el proyecto (educación, salud, vivienda, etc.).">
        <select id="f-sector" class="side-select">
          <option value="">Todos los sectores</option>
        </select>
      </div>
      <div class="filtro-wrap" data-tip="Muestra únicamente el municipio seleccionado en el mapa. Útil para hacer foco en un solo punto del departamento.">
        <select id="f-municipio" class="side-select">
          <option value="">Todos los municipios</option>
        </select>
      </div>
    </div>

    <div class="filtro-wrap" data-tip="Filtra por alcance territorial del proyecto: Departamental (cubre los 26 municipios), Subregional (afecta varios municipios) o Municipal (un único municipio).">
      <div class="impacto-block">
        <div class="impacto-label">
          <span class="pulse-dot"></span>
          <span>Impacto</span>
        </div>
        <select id="f-impacto" class="side-select is-emphasized">
          <option value="">Todos los impactos</option>
          <option value="Departamental">Departamental · todo Sucre</option>
          <option value="Subregional">Subregional · varios municipios</option>
          <option value="Municipal">Municipal · un municipio</option>
        </select>
      </div>
    </div>

    <div class="side-section-title">Resumen general</div>
    <div class="resumen-grid">
      <div class="res-card">
        <div class="res-icon" style="background:#2563eb">P</div>
        <div>
          <div class="res-num" id="r-total">0</div>
          <div class="res-lbl">Proyectos<br>visibles</div>
        </div>
      </div>
      <div class="res-card">
        <div class="res-icon" style="background:#06b6d4">M</div>
        <div>
          <div class="res-num" id="r-munic">0</div>
          <div class="res-lbl">Municipios<br>activos</div>
        </div>
      </div>
      <div class="res-card">
        <div class="res-icon" style="background:#10b981">F</div>
        <div>
          <div class="res-num" id="r-avf">—</div>
          <div class="res-lbl">Avance<br>físico</div>
        </div>
      </div>
      <div class="res-card">
        <div class="res-icon" style="background:#f59e0b">$</div>
        <div>
          <div class="res-num" id="r-avfin">—</div>
          <div class="res-lbl">Avance<br>financiero</div>
        </div>
      </div>
    </div>

    <div class="side-section-title">Estados</div>
    <div id="estados-mini" class="estados-mini"></div>

    <div class="footer-note" id="nogeo-note"></div>
  </aside>

  <!-- ============ MAPA ============ -->
  <main class="main">
    <div id="map"></div>

    <div class="info-panel">
      <div class="info-title">Información clave</div>
      <div class="info-row">
        <div class="info-ico" style="background:#10b981">✓</div>
        <div>
          <div class="info-val" id="i-avf">—</div>
          <div class="info-lbl">Avance físico promedio</div>
        </div>
      </div>
      <div class="info-row">
        <div class="info-ico" style="background:#f59e0b">$</div>
        <div>
          <div class="info-val" id="i-avfin">—</div>
          <div class="info-lbl">Avance financiero promedio</div>
        </div>
      </div>
      <div class="info-row">
        <div class="info-ico" style="background:#2563eb">M</div>
        <div>
          <div class="info-val" id="i-munic">0</div>
          <div class="info-lbl">Municipios cubiertos</div>
        </div>
      </div>
      <div class="info-row">
        <div class="info-ico" style="background:#ef4444">!</div>
        <div>
          <div class="info-val" id="i-alerta">0</div>
          <div class="info-lbl">Proyectos suspendidos</div>
        </div>
      </div>
      <div id="i-nota" class="info-nota"></div>
    </div>

    <div class="leyenda">
      <div class="leyenda-title">Estado del proyecto</div>
      <div id="leyenda-rows"></div>
    </div>
  </main>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
const PAYLOAD = __PAYLOAD__;

// ── Sincronizar la altura del iframe con el viewport real ──────────────────
// Streamlit por defecto fija el iframe del componente a la altura pasada en
// `components.html(height=...)` (en nuestro caso 850px). Si el viewport del
// usuario es más chico (700px en zoom in / portátiles), el iframe queda más
// alto que la pantalla y todo lo que esté en `bottom:16px` (leyenda) cae
// fuera del área visible.
//
// La solución bidireccional: mientras el CSS `position:fixed; height:100vh`
// fuerza al wrapper a ocupar el viewport, este JS le dice al frontend de
// Streamlit que también ponga el iframe a esa altura, vía el mensaje
// estándar `streamlit:setFrameHeight`. CSS y JS se refuerzan mutuamente —
// si uno falla, el otro cubre.
(function() {
  var ultimaAltura = 0;
  function sincronizarAltura() {
    try {
      var pH = (window.parent && window.parent.innerHeight) || window.innerHeight;
      if (pH && Math.abs(pH - ultimaAltura) > 2) {
        ultimaAltura = pH;
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({
            type: 'streamlit:setFrameHeight',
            height: pH
          }, '*');
        }
        document.documentElement.style.height = pH + 'px';
        document.body.style.height = pH + 'px';
      }
    } catch (e) { /* cross-origin u otro; el CSS position:fixed compensa */ }
  }
  sincronizarAltura();
  window.addEventListener('resize', sincronizarAltura);
  // Polling lento: el zoom del navegador no siempre dispara 'resize' en
  // todos los OS/navegadores; este interval lo cubre.
  setInterval(sincronizarAltura, 600);
})();

// ── Setup mapa con tile oscura ─────────────────────────────────────────────
const map = L.map('map', { zoomControl: true, attributionControl: false })
  .setView(PAYLOAD.centro, PAYLOAD.zoom);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 18,
}).addTo(map);

// ── Capa GeoJSON: contorno de Sucre y sus 26 municipios ────────────────────
const GEOJSON_SUCRE = __GEOJSON__;

// Normalizador para hacer match con las claves del payload (sin tildes,
// mayúsculas, trim). Debe replicar el comportamiento de Python _norm_municipio.
function normMuni(s) {
  if (s == null) return '';
  let txt = String(s).normalize('NFKD').replace(/[̀-ͯ]/g, '');
  txt = txt.toUpperCase().trim();
  txt = txt.replace(/\s+/g, ' ').replace(/^[\s.]+|[\s.]+$/g, '');
  return txt;
}

// Color de relleno según conteo de proyectos en el municipio.
function fillColorMuni(n) {
  if (!n)             return 'rgba(148, 163, 184, 0.05)';   // gris muy tenue
  if (n >= 10)        return 'rgba(59, 130, 246, 0.35)';    // azul saturado
  if (n >= 4)         return 'rgba(59, 130, 246, 0.25)';    // azul medio
  return                'rgba(59, 130, 246, 0.15)';         // azul claro
}

function estiloMuni(feature) {
  const nombre = normMuni(feature.properties.MPIO_CNMBR);
  const n = PAYLOAD.proy_por_muni[nombre] || 0;
  return {
    color: 'rgba(148, 163, 184, 0.55)',  // borde gris claro
    weight: 1,
    fillColor: fillColorMuni(n),
    fillOpacity: 1,
  };
}

let geoLayer = null;
if (GEOJSON_SUCRE && GEOJSON_SUCRE.features && GEOJSON_SUCRE.features.length) {
  geoLayer = L.geoJSON(GEOJSON_SUCRE, {
    style: estiloMuni,
    onEachFeature: (feature, layer) => {
      const nombreOriginal = feature.properties.MPIO_CNMBR || '';
      const nombreNorm = normMuni(nombreOriginal);
      const n = PAYLOAD.proy_por_muni[nombreNorm] || 0;
      const proyTxt = n === 1 ? '1 proyecto' : (n + ' proyectos');
      layer.bindTooltip(
        `<strong>${nombreOriginal}</strong><span class="geo-tip-n">${proyTxt}</span>`,
        { sticky: true, className: 'geo-tip', direction: 'top', offset: [0, -4] }
      );
      layer.on('mouseover', e => {
        e.target.setStyle({ weight: 2, color: '#e2e8f0',
                            fillOpacity: 1, fillColor: 'rgba(96, 165, 250, 0.45)' });
        e.target.bringToFront();
      });
      layer.on('mouseout', e => geoLayer.resetStyle(e.target));
    },
  }).addTo(map);

  // Auto-encuadre al departamento si tenemos polígonos.
  try { map.fitBounds(geoLayer.getBounds(), { padding: [20, 20] }); }
  catch (e) { /* fallback al centro hardcodeado */ }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function estadoColor(estado) {
  const c = PAYLOAD.estados[estado];
  return c || PAYLOAD.default;
}
function escape(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]
  ));
}
function tamMarker(n) {
  if (n >= 10) return 'size-l';
  if (n >= 4)  return 'size-m';
  return 'size-s';
}
function dominanteColor(proyectos) {
  // Color del marcador = estado más frecuente entre sus proyectos.
  const conteos = {};
  proyectos.forEach(p => {
    conteos[p.estado] = (conteos[p.estado] || 0) + 1;
  });
  let max = -1, best = '';
  for (const e in conteos) {
    if (conteos[e] > max) { max = conteos[e]; best = e; }
  }
  return estadoColor(best);
}

function popupHtml(grupo) {
  const items = grupo.proyectos.map(p => {
    const col = estadoColor(p.estado);
    return `
      <div class="pop-item">
        <span class="pop-bpin">${escape(p.bpin || '—')}</span>
        <span class="pop-est" style="background:${col}">${escape(p.estado || '—')}</span>
        <div class="pop-nom">${escape(p.nombre)}</div>
        <div class="pop-meta">
          ${escape(p.entidad)} ·
          <strong>${escape(PAYLOAD.fuentes[p.fuente] || p.fuente)}</strong>
          ${p.sector ? ' · ' + escape(p.sector) : ''}
          ${p.avance_fisico != null ? ' · físico ' + p.avance_fisico + '%' : ''}
        </div>
      </div>`;
  }).join('');
  return `
    <div style="min-width:260px; max-width:340px">
      <div class="pop-title">${escape(grupo.nombre)}</div>
      <div class="pop-sub">${grupo.proyectos.length} proyecto(s) en este municipio</div>
      <div class="pop-list">${items}</div>
    </div>`;
}

// ── Construcción de marcadores ─────────────────────────────────────────────
const cluster = L.markerClusterGroup({
  showCoverageOnHover: false,
  spiderfyOnMaxZoom: true,
  maxClusterRadius: 38,
});

let allGrupos = PAYLOAD.marcadores; // referencia inmutable
let visibles = [];

function rebuildMarkers(grupos) {
  cluster.clearLayers();
  visibles = grupos.slice();
  grupos.forEach(g => {
    const color = dominanteColor(g.proyectos);
    const cls = 'mun-marker ' + tamMarker(g.proyectos.length);
    const icon = L.divIcon({
      className: '',
      iconSize: [40, 40],
      iconAnchor: [20, 20],
      html: `<div class="${cls}" style="background:${color}">${g.proyectos.length}</div>`,
    });
    const m = L.marker([g.lat, g.lng], { icon });
    m.bindPopup(popupHtml(g), { maxWidth: 360, minWidth: 280 });
    m.bindTooltip(g.nombre + ' · ' + g.proyectos.length, { direction: 'top', offset:[0, -12] });
    cluster.addLayer(m);
  });
  map.addLayer(cluster);
}

// ── Filtros ─────────────────────────────────────────────────────────────────
function poblarSelect(sel, valores) {
  // Mantener la primera opción ("Todos…")
  const first = sel.querySelector('option');
  sel.innerHTML = '';
  sel.appendChild(first);
  Array.from(valores).sort().forEach(v => {
    const op = document.createElement('option');
    op.value = v; op.textContent = v;
    sel.appendChild(op);
  });
}

function aplicarFiltros() {
  const q  = (document.getElementById('f-buscar').value || '').trim().toLowerCase();
  const fu = document.getElementById('f-fuente').value;
  const en = document.getElementById('f-entidad').value;
  const es = document.getElementById('f-estado').value;
  const sc = document.getElementById('f-sector').value;
  const mu = document.getElementById('f-municipio').value;
  const im = document.getElementById('f-impacto').value;

  const filtrados = [];
  let apariciones = 0;                  // suma cruda (un proyecto en N munis cuenta N)
  const estCount = {};
  // Dedupe por BPIN: KPIs deben mostrar el conteo REAL de proyectos únicos
  const bpinsUnicos     = new Set();
  const bpinsConAvF     = new Set();    // para promediar avance físico sin duplicar
  const bpinsConAvFin   = new Set();
  let   sumAvF = 0, sumAvFin = 0;
  let   suspNUnicos = 0;
  const bpinsSusp = new Set();
  const bpinsEstado = {};               // estado -> Set(bpin), dedupe por estado

  allGrupos.forEach(g => {
    if (mu && g.nombre.toUpperCase() !== mu) return;
    const proyFilt = g.proyectos.filter(p => {
      if (fu && p.fuente !== fu) return false;
      if (en && (p.entidad || '') !== en) return false;
      if (es && p.estado !== es) return false;
      if (sc && (p.sector || '') !== sc) return false;
      if (im && (p.impacto || '') !== im) return false;
      if (q) {
        const hay = (p.bpin + ' ' + p.nombre).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    if (proyFilt.length > 0) {
      filtrados.push(Object.assign({}, g, { proyectos: proyFilt }));
      apariciones += proyFilt.length;
      proyFilt.forEach(p => {
        const bpin = p.bpin || '';
        if (bpin && !bpinsUnicos.has(bpin)) {
          bpinsUnicos.add(bpin);
          // Avance físico/financiero: solo cuenta la primera ocurrencia
          if (p.avance_fisico     != null) { sumAvF   += p.avance_fisico;     bpinsConAvF.add(bpin); }
          if (p.avance_financiero != null) { sumAvFin += p.avance_financiero; bpinsConAvFin.add(bpin); }
          if (p.estado === 'SUSPENDIDO' && !bpinsSusp.has(bpin)) {
            bpinsSusp.add(bpin); suspNUnicos += 1;
          }
        }
        // Estado dedup por BPIN: un proyecto cuenta UNA vez por estado
        if (bpin) {
          if (!bpinsEstado[p.estado]) bpinsEstado[p.estado] = new Set();
          bpinsEstado[p.estado].add(bpin);
        }
      });
    }
  });

  // Convertir bpinsEstado a conteos
  Object.keys(bpinsEstado).forEach(e => { estCount[e] = bpinsEstado[e].size; });

  rebuildMarkers(filtrados);

  const totalUnicos = bpinsUnicos.size;
  const avFTxt   = bpinsConAvF.size   ? (sumAvF   / bpinsConAvF.size  ).toFixed(1) + '%' : '—';
  const avFinTxt = bpinsConAvFin.size ? (sumAvFin / bpinsConAvFin.size).toFixed(1) + '%' : '—';

  // KPIs sidebar — siempre números ÚNICOS (no duplicados por municipio)
  document.getElementById('r-total').textContent  = totalUnicos;
  document.getElementById('r-munic').textContent  = filtrados.length;
  document.getElementById('r-avf').textContent    = avFTxt;
  document.getElementById('r-avfin').textContent  = avFinTxt;
  // KPIs panel "Información clave" — únicos también
  document.getElementById('i-avf').textContent    = avFTxt;
  document.getElementById('i-avfin').textContent  = avFinTxt;
  document.getElementById('i-munic').textContent  = filtrados.length;
  document.getElementById('i-alerta').textContent = suspNUnicos;
  // Nota de claridad: cuántos proyectos únicos vs apariciones en municipios
  const notaEl = document.getElementById('i-nota');
  if (notaEl) {
    if (apariciones > totalUnicos) {
      const diff = apariciones - totalUnicos;
      notaEl.textContent = totalUnicos + ' proyectos únicos · ' + apariciones
        + ' apariciones (' + diff + ' por cobertura multi-municipio)';
      notaEl.style.display = 'block';
    } else {
      notaEl.style.display = 'none';
    }
  }

  // Chips de estados
  const cont = document.getElementById('estados-mini');
  cont.innerHTML = '';
  Object.keys(estCount).sort().forEach(e => {
    const col = estadoColor(e);
    const div = document.createElement('div');
    div.className = 'estado-chip';
    div.title = e;
    div.innerHTML = `<span class="dot" style="background:${col}"></span>`
                  + `<span class="lbl">${escape(e)}</span>`
                  + `<span class="n">${estCount[e]}</span>`;
    cont.appendChild(div);
  });
}

// ── Tooltip flotante para filtros ──────────────────────────────────────────
// Renderizamos el tooltip como un div fixed appendido a body para que NO
// quede clipeado por el overflow:hidden de .sidebar.
(function initTooltips() {
  let tipEl = null;
  function ensureTipEl() {
    if (tipEl) return tipEl;
    tipEl = document.createElement('div');
    tipEl.className = 'filtro-tip';
    document.body.appendChild(tipEl);
    return tipEl;
  }
  function show(wrap) {
    const text = wrap.getAttribute('data-tip');
    if (!text) return;
    const tip = ensureTipEl();
    tip.textContent = text;
    const rect = wrap.getBoundingClientRect();
    // Posicionamos a la derecha del filtro, centrado vertical
    const left = rect.right + 14;
    const top  = rect.top + (rect.height / 2);
    tip.style.left = left + 'px';
    tip.style.top  = (top - 26) + 'px';  // 26 ≈ mitad del alto típico del tip
    // Si se saldría por la derecha, lo ponemos a la izquierda
    requestAnimationFrame(() => {
      const tRect = tip.getBoundingClientRect();
      if (tRect.right > window.innerWidth - 8) {
        tip.style.left = (rect.left - tRect.width - 14) + 'px';
      }
      tip.classList.add('is-visible');
    });
  }
  function hide() {
    if (tipEl) tipEl.classList.remove('is-visible');
  }
  function wire() {
    document.querySelectorAll('.filtro-wrap').forEach(w => {
      if (w.dataset.tipWired === '1') return;
      w.dataset.tipWired = '1';
      w.addEventListener('mouseenter', () => show(w));
      w.addEventListener('mouseleave', hide);
      w.addEventListener('focusin',    () => show(w));
      w.addEventListener('focusout',   hide);
    });
  }
  wire();
  // Re-wire por si el DOM se construye después
  setTimeout(wire, 100);
  setTimeout(wire, 500);
})();

// ── Inicialización ─────────────────────────────────────────────────────────
(function init() {
  // Populate select options
  const fuentes = new Set(), entidades = new Set(), estados = new Set(),
        sectores = new Set(), munics = new Set();
  allGrupos.forEach(g => {
    munics.add(g.nombre.toUpperCase());
    g.proyectos.forEach(p => {
      if (p.fuente)  fuentes.add(p.fuente);
      if (p.entidad) entidades.add(p.entidad);
      if (p.estado)  estados.add(p.estado);
      if (p.sector)  sectores.add(p.sector);
    });
  });
  // Fuentes con label amigable
  const selFu = document.getElementById('f-fuente');
  Array.from(fuentes).sort().forEach(f => {
    const op = document.createElement('option');
    op.value = f; op.textContent = PAYLOAD.fuentes[f] || f;
    selFu.appendChild(op);
  });
  poblarSelect(document.getElementById('f-entidad'),   entidades);
  poblarSelect(document.getElementById('f-estado'),    estados);
  poblarSelect(document.getElementById('f-sector'),    sectores);
  poblarSelect(document.getElementById('f-municipio'), munics);

  // Wire events
  ['f-buscar','f-fuente','f-entidad','f-estado','f-sector','f-municipio','f-impacto'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('input',  aplicarFiltros);
    el.addEventListener('change', aplicarFiltros);
  });

  // Leyenda
  const ley = document.getElementById('leyenda-rows');
  Object.keys(PAYLOAD.estados).forEach(e => {
    const div = document.createElement('div');
    div.className = 'ley-row';
    div.innerHTML = `<span class="ley-dot" style="background:${PAYLOAD.estados[e]}"></span>${escape(e)}`;
    ley.appendChild(div);
  });

  // Nota de proyectos sin geocodificación
  const nogeoEl = document.getElementById('nogeo-note');
  if (PAYLOAD.no_geo_count > 0) {
    nogeoEl.innerHTML = '<strong>' + PAYLOAD.no_geo_count + '</strong> referencia(s) a municipios no reconocidos se omitieron del mapa.';
  } else {
    nogeoEl.textContent = 'Datos: ' + PAYLOAD.total_proy + ' proyecto(s), ' + PAYLOAD.total_munic + ' municipio(s) georreferenciados.';
  }

  aplicarFiltros();
})();
</script>
</body>
</html>
"""
