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
    # Subregión Sabanas
    "SINCELEJO":              (9.3047, -75.3978),
    "COROZAL":                (9.3211, -75.2939),
    "MORROA":                 (9.3406, -75.3097),
    "LOS PALMITOS":           (9.3792, -75.2675),
    "SAMPUES":                (9.1814, -75.3814),
    "SAN JUAN DE BETULIA":    (9.2667, -75.2417),
    "BUENAVISTA":             (9.3197, -74.9706),
    "SINCE":                  (9.2433, -75.1450),
    "SAN PEDRO":              (9.3956, -75.0567),
    "GALERAS":                (9.1639, -75.0497),
    "EL ROBLE":               (9.1014, -75.1003),
    # Subregión Montes de María
    "OVEJAS":                 (9.5247, -75.2294),
    "CHALAN":                 (9.5450, -75.3147),
    "COLOSO":                 (9.4961, -75.3531),
    # Subregión Golfo de Morrosquillo
    "TOLU":                   (9.5236, -75.5828),
    "TOLU VIEJO":             (9.4500, -75.4400),
    "COVENAS":                (9.4011, -75.6800),
    "SAN ONOFRE":             (9.7361, -75.5283),
    "SAN ANTONIO DE PALMITO": (9.3372, -75.5358),
    "PALMITO":                (9.3372, -75.5358),  # mismo que San Antonio de Palmito
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


def _norm_municipio(s) -> str:
    """Normaliza un nombre de municipio: trim + mayúsculas + sin tildes + sin
    puntos. Devuelve string vacío si la entrada es None/vacía."""
    if s is None:
        return ""
    txt = str(s).strip()
    if not txt:
        return ""
    txt = _strip_acentos(txt).upper()
    # eliminar puntos y caracteres redundantes
    txt = re.sub(r"\s+", " ", txt).strip(" .")
    return txt


# Lista normalizada de TODOS los municipios para replicar "TODO EL DEPTO"
# (sólo nombres únicos — Palmito/San Antonio de Palmito son el mismo).
_TODOS_MUNICIPIOS_NORM = list(dict.fromkeys([
    "SINCELEJO", "COROZAL", "MORROA", "LOS PALMITOS", "SAMPUES",
    "SAN JUAN DE BETULIA", "BUENAVISTA", "SINCE", "SAN PEDRO", "GALERAS",
    "EL ROBLE", "OVEJAS", "CHALAN", "COLOSO", "TOLU", "TOLU VIEJO",
    "COVENAS", "SAN ONOFRE", "SAN ANTONIO DE PALMITO", "SAN MARCOS",
    "SAN BENITO ABAD", "CAIMITO", "LA UNION", "SUCRE", "MAJAGUAL", "GUARANDA",
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
    st.markdown("""
    <style>
    /* — Bloquear scroll vertical del documento en la vista Mapa — */
    html, body, [data-testid="stAppViewContainer"] {
        overflow: hidden !important;
        height: 100vh !important;
        max-height: 100vh !important;
    }
    section.main {
        overflow: hidden !important;
        height: 100vh !important;
        max-height: 100vh !important;
    }
    /* — Romper el contenedor principal y eliminar paddings — */
    section.main > div.block-container,
    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="stMainBlockContainer"],
    div.main .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        width: 100% !important;
        height: 100vh !important;
        max-height: 100vh !important;
        overflow: hidden !important;
    }
    /* — Iframe del componente: usa el 100% del contenedor padre, no del
       viewport completo, para que si el usuario abre el sidebar nativo de
       Streamlit el iframe se reduzca y no quede empujado fuera de pantalla. — */
    section.main iframe,
    div[data-testid="stIFrame"] iframe,
    iframe[title="streamlit_app.components.v1.html.html"] {
        width: 100% !important;
        min-width: 100% !important;
        height: 100vh !important;
        min-height: 100vh !important;
        margin: 0 !important;
        border: 0 !important;
        display: block !important;
    }
    /* — Fondo del main y header transparentes (estilo dark) — */
    section.main { background: #0b1220 !important; }
    header[data-testid="stHeader"] {
        background: transparent !important;
        z-index: 999999;
    }
    /* Sidebar nativo: NO lo forzamos colapsado — Streamlit lo maneja con el
       botón « del usuario. Solo le damos un fondo oscuro para que combine
       con el visor en caso de que el usuario lo deje abierto. */
    section[data-testid="stSidebar"] {
        background: #0f172a !important;
    }
    /* Botón de toggle « con buen contraste sobre el mapa oscuro */
    button[kind="header"], [data-testid="stSidebarCollapsedControl"] button {
        color: #fff !important;
        background: rgba(15, 23, 42, 0.85) !important;
        border-radius: 8px;
    }
    /* Quitar el botón "Deploy" y menús de Streamlit en esta vista */
    [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu {
        display: none !important;
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

    # 2) Métricas globales
    total_proy = sum(len(g["proyectos"]) for g in grupos.values()) + len(no_geo)
    total_munic = len(grupos)
    # Avances promedio (omitiendo nulos)
    avances_f, avances_fin = [], []
    estados_count = {}
    sectores_count = {}
    for g in grupos.values():
        for p in g["proyectos"]:
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

    payload = {
        "centro":      list(CENTRO_DEPTO),
        "zoom":        ZOOM_INICIAL,
        "marcadores":  marcadores,
        "estados":     ESTADO_COLORES,
        "default":     COLOR_DEFAULT,
        "fuentes":     FUENTES_LABEL,
        "total_proy":  total_proy,
        "total_munic": total_munic,
        "avance_fisico_prom":     av_f_prom,
        "avance_financiero_prom": av_fin_prom,
        "estados_count":  estados_count,
        "sectores_count": sectores_count,
        "no_geo_count": len(no_geo),
    }

    # 4) HTML + Leaflet embebido
    payload_json = json.dumps(payload, ensure_ascii=False)
    # Escapamos las llaves para que .format/f-string no las interprete.
    componente_html = _construir_componente_html(payload_json)

    # Altura fija grande para que la CSS de 100vh dentro del iframe llene
    # bien la pantalla en cualquier monitor. El CSS externo limita el
    # contenedor de Streamlit a 100vh, así que no hay scroll vertical.
    components.html(componente_html, height=1200, scrolling=False)


def _construir_componente_html(payload_json: str) -> str:
    """
    HTML+CSS+JS auto-contenido. Recibe el payload ya serializado a JSON.

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
    return (_TEMPLATE_HTML).replace("__PAYLOAD__", payload_json)


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
  html, body { margin:0; padding:0; height:100%; font-family: 'Montserrat', sans-serif;
               background:#0b1220; color:#e5e7eb; overflow: hidden;
               -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
  .layout { display:flex; height:100vh; min-height: 820px; }

  /* ── SIDEBAR ──────────────────────────────────────────────────────── */
  .sidebar {
    width: 290px; min-width:290px; background:#0f172a; border-right:1px solid #1e293b;
    display:flex; flex-direction:column;
    overflow-y: auto; overflow-x: hidden;
  }
  .sidebar > * { min-width: 0; }  /* permite a los hijos no overflowear */
  .side-header {
    padding: 18px 18px 16px; border-bottom: 1px solid #1e293b;
    display:flex; gap:12px; align-items:center;
  }
  .side-logo {
    width: 38px; height: 38px; border-radius:10px;
    background: linear-gradient(135deg, #2563eb, #06b6d4);
    display:flex; align-items:center; justify-content:center; flex-shrink:0;
    font-weight:800; color:#fff; font-size:1.1rem;
  }
  .side-title { font-size:0.95rem; font-weight:700; color:#fff; line-height:1.15; }
  .side-sub   { font-size:0.7rem;  color:#94a3b8; line-height:1.3; margin-top:2px; }

  .side-section-title {
    text-transform: uppercase; font-size:0.65rem; letter-spacing: 1.1px;
    color:#60a5fa; font-weight:700; padding: 14px 18px 6px;
  }
  .side-search-wrap { padding: 0 18px 12px; }
  .side-search {
    width: 100%; background:#0b1220; border:1px solid #1e293b;
    color:#e5e7eb; padding: 8px 10px; border-radius:8px;
    font-size:0.78rem; outline:none;
  }
  .side-search:focus { border-color:#3b82f6; }

  .side-filters { padding: 0 18px 4px; display:flex; flex-direction:column; gap:8px; }
  .side-select {
    width:100%; background:#0b1220; border:1px solid #1e293b; color:#e5e7eb;
    padding: 8px 10px; border-radius:8px; font-size:0.78rem; outline:none;
    appearance: none;
    text-overflow: ellipsis; overflow: hidden; white-space: nowrap;
  }
  .side-select option { background:#0b1220; color:#e5e7eb; }

  .resumen-grid {
    padding: 4px 18px 18px;
    display:grid; grid-template-columns: 1fr 1fr; gap: 8px;
  }
  .res-card {
    background:#0b1220; border:1px solid #1e293b; border-radius:10px;
    padding: 9px 10px; display:flex; gap:8px; align-items:center;
    min-width: 0; overflow: hidden;
  }
  .res-card > div:nth-child(2) {
    min-width: 0; flex: 1 1 auto;
  }
  .res-icon {
    width:28px; height:28px; border-radius:8px;
    display:flex; align-items:center; justify-content:center;
    font-weight:800; color:#fff; flex-shrink:0; font-size:0.85rem;
  }
  .res-num {
    font-size:0.95rem; font-weight:800; color:#fff; line-height:1.1;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .res-lbl {
    font-size:0.58rem; color:#94a3b8; margin-top:3px;
    text-transform:uppercase; letter-spacing:0.5px; line-height:1.2;
    overflow: hidden; word-break: break-word;
  }

  /* ── MAPA ─────────────────────────────────────────────────────────── */
  .main { flex:1; position:relative; }
  #map { width:100%; height:100%; background:#0b1220; }

  /* ── PANEL INFO (esquina sup. derecha del mapa) ──────────────────── */
  .info-panel {
    position:absolute; top: 16px; right: 16px; z-index: 600;
    width: 260px; background: rgba(15,23,42,0.92);
    border:1px solid #1e293b; border-radius:12px; padding: 12px 14px;
    box-shadow: 0 8px 28px rgba(0,0,0,0.5);
    backdrop-filter: blur(6px);
  }
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

  .leyenda {
    position:absolute; bottom: 16px; right: 16px; z-index: 600;
    background: rgba(15,23,42,0.92); border:1px solid #1e293b; border-radius:12px;
    padding: 12px 14px; box-shadow: 0 8px 28px rgba(0,0,0,0.5);
    backdrop-filter: blur(6px);
  }
  .leyenda-title {
    font-size:0.68rem; text-transform:uppercase; color:#60a5fa;
    letter-spacing:1.1px; font-weight:700; margin-bottom:8px;
  }
  .ley-row { display:flex; align-items:center; gap:8px; font-size:0.75rem; margin: 3px 0; color:#cbd5e1; }
  .ley-dot { width:10px; height:10px; border-radius:50%; }

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
    padding: 0 18px 14px;
    display:flex; flex-wrap: wrap; gap: 6px;
  }
  .estado-chip {
    font-size:0.62rem; padding:4px 8px; border-radius:12px;
    background:#0b1220; border:1px solid #1e293b; color:#cbd5e1;
    display:inline-flex; align-items:center; gap:5px; cursor:default;
    max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .estado-chip .dot { width:7px; height:7px; border-radius:50%; flex-shrink: 0; }
  .estado-chip .n   { color:#fff; font-weight:700; flex-shrink: 0; }
  .estado-chip .lbl {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 160px;
  }

  .footer-note {
    margin-top:auto; padding: 10px 18px 14px;
    font-size:0.64rem; color:#475569; border-top: 1px solid #1e293b;
    word-wrap: break-word; overflow-wrap: break-word;
  }
  .footer-note strong { color: #94a3b8; }
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
      <input id="f-buscar" class="side-search" placeholder="Buscar por BPIN o nombre…" />
    </div>

    <div class="side-section-title">Filtros rápidos</div>
    <div class="side-filters">
      <select id="f-fuente" class="side-select">
        <option value="">Todas las fuentes</option>
      </select>
      <select id="f-estado" class="side-select">
        <option value="">Todos los estados</option>
      </select>
      <select id="f-sector" class="side-select">
        <option value="">Todos los sectores</option>
      </select>
      <select id="f-municipio" class="side-select">
        <option value="">Todos los municipios</option>
      </select>
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

// ── Setup mapa con tile oscura ─────────────────────────────────────────────
const map = L.map('map', { zoomControl: true, attributionControl: false })
  .setView(PAYLOAD.centro, PAYLOAD.zoom);

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 18,
}).addTo(map);

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
  const es = document.getElementById('f-estado').value;
  const sc = document.getElementById('f-sector').value;
  const mu = document.getElementById('f-municipio').value;

  const filtrados = [];
  let total = 0;
  const estCount = {};
  let avF = [], avFin = [], suspN = 0;

  allGrupos.forEach(g => {
    if (mu && g.nombre.toUpperCase() !== mu) return;
    const proyFilt = g.proyectos.filter(p => {
      if (fu && p.fuente !== fu) return false;
      if (es && p.estado !== es) return false;
      if (sc && (p.sector || '') !== sc) return false;
      if (q) {
        const hay = (p.bpin + ' ' + p.nombre).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    if (proyFilt.length > 0) {
      filtrados.push(Object.assign({}, g, { proyectos: proyFilt }));
      total += proyFilt.length;
      proyFilt.forEach(p => {
        estCount[p.estado] = (estCount[p.estado] || 0) + 1;
        if (p.avance_fisico     != null) avF.push(p.avance_fisico);
        if (p.avance_financiero != null) avFin.push(p.avance_financiero);
        if (p.estado === 'SUSPENDIDO') suspN += 1;
      });
    }
  });

  rebuildMarkers(filtrados);

  // KPIs sidebar
  document.getElementById('r-total').textContent  = total;
  document.getElementById('r-munic').textContent  = filtrados.length;
  document.getElementById('r-avf').textContent    = avF.length
    ? (avF.reduce((a,b)=>a+b,0)/avF.length).toFixed(1) + '%' : '—';
  document.getElementById('r-avfin').textContent  = avFin.length
    ? (avFin.reduce((a,b)=>a+b,0)/avFin.length).toFixed(1) + '%' : '—';
  // KPIs panel info
  document.getElementById('i-avf').textContent    = document.getElementById('r-avf').textContent;
  document.getElementById('i-avfin').textContent  = document.getElementById('r-avfin').textContent;
  document.getElementById('i-munic').textContent  = filtrados.length;
  document.getElementById('i-alerta').textContent = suspN;

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

// ── Inicialización ─────────────────────────────────────────────────────────
(function init() {
  // Populate select options
  const fuentes = new Set(), estados = new Set(), sectores = new Set(), munics = new Set();
  allGrupos.forEach(g => {
    munics.add(g.nombre.toUpperCase());
    g.proyectos.forEach(p => {
      if (p.fuente) fuentes.add(p.fuente);
      if (p.estado) estados.add(p.estado);
      if (p.sector) sectores.add(p.sector);
    });
  });
  // Fuentes con label amigable
  const selFu = document.getElementById('f-fuente');
  Array.from(fuentes).sort().forEach(f => {
    const op = document.createElement('option');
    op.value = f; op.textContent = PAYLOAD.fuentes[f] || f;
    selFu.appendChild(op);
  });
  poblarSelect(document.getElementById('f-estado'), estados);
  poblarSelect(document.getElementById('f-sector'), sectores);
  poblarSelect(document.getElementById('f-municipio'), munics);

  // Wire events
  ['f-buscar','f-fuente','f-estado','f-sector','f-municipio'].forEach(id => {
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
