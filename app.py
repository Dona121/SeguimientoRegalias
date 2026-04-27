"""
app.py — Orquestador principal de la aplicación Streamlit.
Importa todos los módulos, gestiona sidebar, filtros, KPIs y renderiza los tabs.
"""
from constants import (
    C, INTERVALOS, SEMAFOROS, COLS_EVAL, COLS_EVAL_LABELS,
    TABLA_ESPERADA, TABLA_DESCENTRALIZADAS, COLUMNAS_ESPERADAS,
    TIPO_LABEL, TIPO_EJEMPLO, inject_css,
)
from data import (
    procesar, procesar_contratos, procesar_eval_sucre, procesar_descentralizadas,
    _cargar_desde_github, validar_archivo, th, error_card,
    _render_eval_errors,
    GITHUB_RAW_URL, GITHUB_CONTRATOS_URL,
)
from export import generar_excel
from render import (
    badge_html, _pill, _fmt_date, _dias_tooltip, eval_color,
    _clasificar_promedio, _contratos_panel, _calcular_clasi_modal,
    HITO_KEY_MAP, CLASI_TO_HITO, HITO_CALC_META,
    ESTADO_PROY_COLORS, ESTADO_CONT_COLORS, CTTO_ESTADO_COLORS,
    _estado_tooltip_html,
    _BADGE_BY_HITO, _ROW_CLS_MAP,
)
import streamlit as st
import polars as pl
import pandas as pd
import io
import html
import json
import logging
import urllib.parse
import datetime as _dt
import streamlit.components.v1 as components
from datetime import date

_log = logging.getLogger(__name__)

# Inyectar CSS global y JS de tooltips
inject_css()

with st.sidebar:
    st.markdown("<div class='sidebar-section'>📁 Datos</div>", unsafe_allow_html=True)

    # ── Botón de recarga ──────────────────────────────────────────────────────
    # Limpia el caché de _cargar_desde_github (que tiene ttl=3600) para forzar
    # una descarga fresca del repo. Útil cuando alguien acaba de subir cambios.
    if st.button("Recargar datos del repositorio", use_container_width=True,
                 help="Vuelve a descargar los archivos desde GitHub. Úsalo si acabas de actualizar el repositorio."):
        st.cache_data.clear()
        st.rerun()

    uploaded = st.file_uploader("Subir otro archivo Excel", type=["xlsx"], label_visibility="collapsed")
    if uploaded:
        st.success("Usando el archivo subido manualmente.")
    else:
        st.markdown(
            f"<p style='font-size:0.7rem;color:rgba(255,255,255,0.5);margin:0.3rem 0 0'>"
            f"Cargando datos desde el repositorio por defecto. "
            f"Sube un archivo para usar datos distintos.</p>",
            unsafe_allow_html=True,
        )
    st.markdown("<div class='sidebar-section'>📋 Contratos</div>", unsafe_allow_html=True)
    uploaded_cttos = st.file_uploader(
        "Archivo de contratos (CG-cttos)",
        type=["xlsx"],
        label_visibility="collapsed",
        key="uploader_contratos",
    )
    if uploaded_cttos:
        st.success("Usando contratos cargados manualmente.")
    else:
        st.markdown(
            f"<p style='font-size:0.7rem;color:rgba(255,255,255,0.5);margin:0.3rem 0 0'>"
            f"Contratos desde el repositorio por defecto.</p>",
            unsafe_allow_html=True,
        )

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="page-header">
  <div>
    <h1>Seguimiento y Evaluación · Regalías</h1>
    <p>Matriz de seguimiento de proyectos por hito de gestión</p>
  </div>
</div>
""", unsafe_allow_html=True)

# Caché de bytes del archivo subido para evitar consumir el stream en reruns
if uploaded is not None:
    _upload_id = f"{uploaded.name}_{uploaded.size}"
    if st.session_state.get("_upload_id") != _upload_id:
        st.session_state["_upload_id"]  = _upload_id
        st.session_state["_file_bytes"] = uploaded.read()
    file_bytes = st.session_state["_file_bytes"]
else:
    st.session_state.pop("_upload_id",  None)
    st.session_state.pop("_file_bytes", None)
    with st.spinner("Cargando datos desde el repositorio…"):
        file_bytes = _cargar_desde_github(GITHUB_RAW_URL)

if file_bytes is None:
    st.error(
        "No se pudo cargar el archivo de datos. "
        "Verifica que la URL en `GITHUB_RAW_URL` sea correcta y que el repositorio sea público, "
        "o sube el archivo manualmente desde el panel izquierdo."
    )
    st.stop()

df_raw, errores = validar_archivo(file_bytes)

if errores:
    muted = C["muted"]
    ref_rows = "".join(
        f"<tr><td><code>{col}</code></td>"
        f"<td><b>{TIPO_LABEL[tipo]}</b></td>"
        f"<td style='color:{muted}'>{TIPO_EJEMPLO[tipo]}</td></tr>"
        for col, (tipo, _) in COLUMNAS_ESPERADAS.items()
    )
    ref_table = f"""
    <table class="ref-table">
        <thead><tr>
            <th>Nombre exacto de la columna</th>
            <th>Tipo de dato esperado</th>
            <th>Ejemplo</th>
        </tr></thead>
        <tbody>{ref_rows}</tbody>
    </table>"""

    st.markdown(f"""
    <div style="background:{C['white']};border-radius:12px;padding:1.5rem 1.8rem;
                box-shadow:0 1px 6px rgba(0,0,0,0.07);margin-top:0.5rem">
        <div style="font-family:'Montserrat',sans-serif;font-size:1rem;font-weight:700;
                    color:{C['azul_oscuro']};margin-bottom:0.3rem">
            No se pudo cargar el archivo
        </div>
        <div style="font-size:0.83rem;color:{C['muted']};margin-bottom:1rem">
            Se encontraron los siguientes problemas. Corrígelos en Excel y vuelve a cargar el archivo.
        </div>
        {"".join(errores)}
        <details style="margin-top:1.2rem">
            <summary style="font-size:0.8rem;font-weight:600;color:{C['azul_medio']};
                            cursor:pointer;user-select:none;list-style:none;display:flex;align-items:center;gap:6px">
                &#9432; Ver referencia completa: tabla y columnas esperadas
            </summary>
            <div style="margin-top:0.8rem">
                <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;
                            letter-spacing:0.8px;color:{C['muted']};margin-bottom:0.3rem">
                    Nombre de la tabla en Excel
                </div>
                <div style="font-size:0.85rem;margin-bottom:1rem">
                    La tabla debe llamarse exactamente:
                    <code style="background:#f1f5f9;padding:2px 8px;border-radius:4px;
                    color:{C['azul_medio']};font-size:0.85rem">{TABLA_ESPERADA}</code>
                    <span style="font-size:0.78rem;color:{C['muted']}">
                    — puedes verificarlo en Excel seleccionando cualquier celda de la tabla
                    y mirando el cuadro de nombre en la esquina superior izquierda.</span>
                </div>
                <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;
                            letter-spacing:0.8px;color:{C['muted']};margin-bottom:0.3rem">
                    Columnas esperadas
                </div>
                <div style="font-size:0.78rem;color:{C['muted']};margin-bottom:0.6rem">
                    Los nombres deben ser exactamente iguales, incluyendo tildes, espacios y mayúsculas.
                </div>
                {ref_table}
            </div>
        </details>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

try:
    df = procesar(file_bytes)
except Exception as e:
    msg = str(e)
    col_hint = ""
    for col in COLUMNAS_ESPERADAS:
        if col.lower() in msg.lower():
            col_hint = f"<br>Columna relacionada: <code>{col}</code>"
            break
    st.markdown(f"""
    <div style="background:{C['white']};border-radius:12px;padding:1.5rem 1.8rem;
                box-shadow:0 1px 6px rgba(0,0,0,0.07);margin-top:0.5rem">
        <div style="font-family:'Montserrat',sans-serif;font-size:1rem;font-weight:700;
                    color:{C['azul_oscuro']};margin-bottom:0.8rem">
            Error al procesar el archivo
        </div>
        <div class="error-card">
            <div class="error-title">&#9888; Problema inesperado al leer los datos</div>
            <div class="error-body">
                El archivo fue cargado pero ocurrió un error al procesar su contenido.{col_hint}
            </div>
            <div class="error-fix">
                <strong>Cómo solucionarlo</strong>
                Verifica que ninguna columna haya sido renombrada o eliminada en la tabla
                <code>{TABLA_ESPERADA}</code>. Si el problema persiste, intenta exportar el archivo
                de nuevo desde el sistema origen y cargarlo sin modificaciones.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# CARGA DE CONTRATOS
# ─────────────────────────────────────────────────────────────────────────────
if uploaded_cttos is not None:
    _cttos_id = f"{uploaded_cttos.name}_{uploaded_cttos.size}"
    if st.session_state.get("_cttos_id") != _cttos_id:
        st.session_state["_cttos_id"]    = _cttos_id
        st.session_state["_cttos_bytes"] = uploaded_cttos.read()
    _cttos_bytes = st.session_state["_cttos_bytes"]
else:
    st.session_state.pop("_cttos_id",    None)
    st.session_state.pop("_cttos_bytes", None)
    with st.spinner("Cargando contratos desde el repositorio…"):
        _cttos_bytes = _cargar_desde_github(GITHUB_CONTRATOS_URL)

df_contratos, _cttos_diag = (
    procesar_contratos(_cttos_bytes) if _cttos_bytes
    else (None, "No se obtuvieron bytes del archivo de contratos")
)

# ─────────────────────────────────────────────────────────────────────────────
# FILTROS EN SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
HITOS = {
    "H1 · Sin contratar sin apertura":    ("hito_1_val", "clasi_1"),
    "H2 · Sin contratar con apertura":    ("hito_2_val", "clasi_2"),
    "H3 · Contratado sin acta de inicio": ("hito_3_val", "clasi_3"),
    "H4 · En ejecución rezagado":         ("hito_4_val", "clasi_4"),
    "H5 · Proyectos terminados":          ("hito_5_val", "clasi_5"),
}

# ─────────────────────────────────────────────────────────────────────────────
# UNIVERSO DE TRABAJO
# Sin filtros globales en el sidebar — cada pestaña tiene sus propios filtros
# que actúan sobre df_f directamente.
# ─────────────────────────────────────────────────────────────────────────────
df_f = df

# ─────────────────────────────────────────────────────────────────────────────
# KPIs
# ─────────────────────────────────────────────────────────────────────────────
total_proy      = df_f.height
total_entidades = df_f["ENTIDAD O SECRETARIA"].n_unique()
suspendidos     = int(df_f["Suspendidos"].drop_nulls().sum()) if df_f["Suspendidos"].drop_nulls().len() > 0 else 0
para_cierre     = int(df_f["Para cierre"].drop_nulls().sum()) if df_f["Para cierre"].drop_nulls().len() > 0 else 0

estados_conteo = (
    df_f.group_by("ESTADO PROYECTO")
    .agg(pl.len().alias("n"))
    .sort("n", descending=True)
)
estado_items = ""
for row_e in estados_conteo.to_dicts():
    est = row_e["ESTADO PROYECTO"] or "(Sin estado)"
    n   = row_e["n"]
    eu  = est.strip().upper()
    dot_colors = {
        "CONTRATADO EN EJECUCIÓN":       C["verde_medio"],
        "TERMINADO":                     C["muted"],
        "SIN CONTRATAR":                 C["cian"],
        "PARA CIERRE":                   C["cafe"],
        "CONTRATADO SIN ACTA DE INICIO": C["azul_medio"],
        "SUSPENDIDO":                    C["naranja_osc"],
    }
    dot = dot_colors.get(eu, C["muted"])
    estado_items += (
        f'<div class="estado-kpi-row">'
        f'<span class="estado-kpi-label">'
        f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;'
        f'background:{dot};margin-right:5px;flex-shrink:0"></span>{est}</span>'
        f'<span class="estado-kpi-n">{n}</span></div>'
    )

st.markdown("<div style='height:0.2rem'></div>", unsafe_allow_html=True)
ka, kb, kd = st.columns([1.3, 1.3, 3.2])

with ka:
    st.markdown(f"""
    <div class="kpi-main">
        <div class="label">Total proyectos</div>
        <div class="value">{total_proy}</div>
        <div class="sub">en los filtros activos</div>
    </div>""", unsafe_allow_html=True)

with kb:
    st.markdown(f"""
    <div class="kpi-main" style="background:{C['verde_oscuro']}">
        <div class="label">Entidades</div>
        <div class="value">{total_entidades}</div>
        <div class="sub">secretarías / dependencias</div>
    </div>""", unsafe_allow_html=True)

with kd:
    st.markdown(f"""
    <div class="kpi-estados">
        <div class="kpi-estados-title">Proyectos por estado</div>
        <div class="kpi-estados-grid">{estado_items}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# AGRUPACIÓN
# ─────────────────────────────────────────────────────────────────────────────
agrupacion = (
    df.group_by("ENTIDAD O SECRETARIA")
    .agg(
        pl.col("hito_1_val").mean().round(1).alias("Hito 1 (días)"),
        pl.col("hito_2_val").mean().round(1).alias("Hito 2 (días)"),
        pl.col("hito_3_val").mean().round(1).alias("Hito 3 (días)"),
        pl.col("hito_4_val").mean().round(1).alias("Hito 4 (días)"),
        pl.col("hito_5_val").mean().round(1).alias("Hito 5 (días)"),
        pl.col("Suspendidos").sum().alias("Suspendidos"),
        pl.col("Para cierre").sum().alias("Para cierre"),
        pl.len().alias("Total"),
    )
    .sort("ENTIDAD O SECRETARIA")
)

_CLASI_COLS      = ["clasi_1", "clasi_2", "clasi_3", "clasi_4", "clasi_5"]
clasi_por_entidad = _calcular_clasi_modal(df, _CLASI_COLS)

# ─────────────────────────────────────────────────────────────────────────────
# PRE-CARGA EVALUACIÓN
# ─────────────────────────────────────────────────────────────────────────────
_df_eval_sucre, _cols_eval_sucre, _, _df_eval_sucre_raw = procesar_eval_sucre(file_bytes)
_df_eval_desc,  _cols_eval_desc,  _, _df_eval_desc_raw  = procesar_descentralizadas(file_bytes)

tab_resumen, tab_proyectos, tab_evaluacion, tab_comunicaciones, tab_exportar = st.tabs([
    "Resumen por entidad",
    "Todos los proyectos",
    "Evaluación del modelo",
    "Comunicaciones",
    "Exportar",
])

# ── TAB 1: Tabla resumen ──────────────────────────────────────────────────────
with tab_resumen:
    def hito_cell(dias_val, clasi_key):
        if dias_val is None or (isinstance(dias_val, float) and dias_val != dias_val):
            return "<td class='null-cell'>—</td>"
        clasi  = _clasificar_promedio(dias_val, clasi_key)
        hito_k = HITO_KEY_MAP.get(clasi_key)
        return f"<td><span class='dias-val'>{dias_val:.1f} d</span>{badge_html(clasi, hito_k)}</td>"

    def _build_row(row):
        e    = html.escape(row["ENTIDAD O SECRETARIA"] or "")
        susp = int(row["Suspendidos"]) if row["Suspendidos"] else 0
        pc   = int(row["Para cierre"]) if row["Para cierre"] else 0
        return f"""<tr>
            <td class="entidad-name">{e}</td>
            {hito_cell(row['Hito 1 (días)'], 'clasi_1')}
            {hito_cell(row['Hito 2 (días)'], 'clasi_2')}
            {hito_cell(row['Hito 3 (días)'], 'clasi_3')}
            {hito_cell(row['Hito 4 (días)'], 'clasi_4')}
            {hito_cell(row['Hito 5 (días)'], 'clasi_5')}
            <td style="text-align:center;font-weight:500">{susp}</td>
            <td style="text-align:center;font-weight:500">{pc}</td>
            <td class="col-total">{int(row['Total'])}</td>
        </tr>"""

    rows_html = "".join(_build_row(row) for row in agrupacion.to_dicts())

    st.markdown(f"""
    <table class="summary-table">
    <thead><tr>
        <th>Entidad / Secretaría</th>
        {th("Sin contratar<br>sin apertura", "Hito 1 · Sin contratar sin apertura",
            "Promedio de días entre la <b>Fecha de aprobación</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Estado = SIN CONTRATAR y sin fecha de apertura.")}
        {th("Sin contratar<br>con apertura", "Hito 2 · Sin contratar con apertura",
            "Promedio de días entre la <b>Fecha de apertura del primer proceso</b> y la <b>Fecha de acta de inicio</b>.<br><br>Condición: Estado = SIN CONTRATAR con fecha de apertura registrada.")}
        {th("Contratado<br>sin acta de inicio", "Hito 3 · Contratado sin acta de inicio",
            "Promedio de días entre la <b>Fecha de suscripción</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Estado = CONTRATADO SIN ACTA DE INICIO.<br><br>Semáforo: Verde 0–15 d · Naranja 16–30 d · Rojo 31–45 d · Negro &gt;45 d")}
        {th("En ejecución<br>rezagado", "Hito 4 · En ejecución rezagado",
            "Meses entre el <b>Horizonte del proyecto</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Estado = CONTRATADO EN EJECUCIÓN, CPI = 0, SPI = 0 y horizonte vencido.")}
        {th("Proyectos<br>terminados", "Hito 5 · Proyectos terminados",
            "Promedio de días entre la <b>Fecha de finalización</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Fecha de finalización registrada.")}
        {th("Suspendidos", "Proyectos suspendidos", "Conteo de proyectos cuyo <b>Estado contrato</b> = SUSPENDIDO.")}
        {th("Para cierre", "Proyectos para cierre", "Conteo de proyectos con Estado = PARA CIERRE.")}
        <th class="col-total">Total</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)

    # ── Detalle por hito ──────────────────────────────────────────────────────
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>Detalle por hito</div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.78rem;color:#6b7280;margin-bottom:0.8rem'>"
        "Selecciona un hito para ver el detalle de todos los proyectos que lo tienen activo, "
        "ordenados de mayor a menor tiempo.</div>",
        unsafe_allow_html=True,
    )

    sel_hito_resumen = st.selectbox(
        "Hito a detallar",
        list(HITOS.keys()),
        key="sel_hito_resumen",
        label_visibility="collapsed",
    )
    sel_hito_col_r, sel_clasi_col_r = HITOS[sel_hito_resumen]
    hito_key_detalle = HITO_KEY_MAP.get(sel_clasi_col_r, None)

    DATE_COLS_DET = [
        "FECHA APROBACIÓN PROYECTO", "FECHA DE APERTURA DEL PRIMER PROCESO",
        "FECHA SUSCRIPCION", "FECHA ACTA INICIO", "HORIZONTE DEL PROYECTO",
        "FECHA DE FINALIZACIÓN", "FECHA DE CORTE GESPROY",
    ]
    df_det = (
        df
        .filter(~pl.col(sel_hito_col_r).is_null())
        .select(
            "ENTIDAD O SECRETARIA", "BPIN", "NOMBRE PROYECTO", "ESTADO PROYECTO",
            sel_hito_col_r, sel_clasi_col_r,
            *DATE_COLS_DET,
        )
        .sort(["ENTIDAD O SECRETARIA", sel_hito_col_r], descending=[False, True])
    )

    if df_det.height == 0:
        st.info("No hay proyectos con valor en este hito para los filtros seleccionados.")
    else:
        for entidad in df_det["ENTIDAD O SECRETARIA"].unique().sort().to_list():
            sub      = df_det.filter(pl.col("ENTIDAD O SECRETARIA") == entidad)
            prom     = sub[sel_hito_col_r].mean()
            n        = sub.height
            prom_str = f"{prom:.1f} días" if prom is not None else "—"

            with st.expander(f"{entidad}   ·   {n} proyecto(s)   ·   Promedio: {prom_str}", expanded=False):
                det_rows_list = []
                for r in sub.to_dicts():
                    dias_v   = r[sel_hito_col_r]
                    dias_str = f"{dias_v:.1f} d" if dias_v is not None else "—"

                    # ── Reclasificación local — usa INTERVALOS directamente ──
                    if dias_v is not None:
                        if sel_hito_col_r == "hito_4_val":
                            meses = dias_v / 30.0
                            if   meses <= 1: clasi_v = "0-1"
                            elif meses <= 3: clasi_v = "1.1-3"
                            elif meses <= 6: clasi_v = "3.1-6"
                            else:            clasi_v = ">6"
                        else:
                            intervalos = INTERVALOS.get(sel_hito_col_r, [])
                            clasi_v = None
                            for label, lo, hi in intervalos:
                                if hi is None and dias_v >= lo:                 clasi_v = label; break
                                elif hi is not None and lo <= dias_v <= hi:     clasi_v = label; break
                    else:
                        clasi_v = None

                    # ── Badge y color de fila por hito (sin colisiones) ──────
                    badge_cls_str = (
                        _BADGE_BY_HITO.get(sel_hito_col_r, {}).get(str(clasi_v), "badge-yellow")
                        if clasi_v else ""
                    )
                    row_cls = _ROW_CLS_MAP.get(badge_cls_str, "")

                    tooltip  = _dias_tooltip(r, sel_hito_col_r)
                    _bpin_h  = html.escape(str(r['BPIN'] or '—'))
                    _nom_h   = html.escape(r['NOMBRE PROYECTO'] or '—')
                    _est_h   = html.escape(r['ESTADO PROYECTO'] or '(Sin estado)')
                    det_rows_list.append(f"""<tr class="{row_cls}">
                        <td><span class="bpin-tag">{_bpin_h}</span></td>
                        <td style="font-size:0.81rem">{_nom_h}</td>
                        <td><span class="estado-tag">{_est_h}</span></td>
                        <td>
                          <div class="dias-tip-wrap">
                            <span class="dias-val-link">{dias_str}</span>
                            {tooltip}
                          </div>
                        </td>
                        <td>{badge_html(clasi_v, hito_key_detalle)}</td>
                    </tr>""")

                st.markdown(f"""
                <table class="detail-table">
                <thead><tr>
                    <th>BPIN</th><th>Nombre del proyecto</th><th>Estado</th>
                    <th>Días <span style="font-size:0.58rem;font-weight:500;opacity:0.7">(pasar el cursor)</span></th>
                    <th>Clasificación</th>
                </tr></thead>
                <tbody>{"".join(det_rows_list)}</tbody>
                </table>""", unsafe_allow_html=True)

# ── TAB 2: Todos los proyectos ────────────────────────────────────────────────
with tab_proyectos:
    st.markdown("<div class='section-heading'>Todos los proyectos</div>", unsafe_allow_html=True)

    st.markdown(f"""
    <style>
    .proy-table {{
        width: 100%; border-collapse: collapse; font-size: 0.83rem;
        background: #ffffff; border-radius: 12px; overflow: hidden;
        box-shadow: 0 2px 20px rgba(0,40,90,0.10);
    }}
    .proy-table thead tr {{ background: {C['azul_oscuro']}; color: white; }}
    .proy-table th {{
        padding: 0.85rem 1rem; font-family: 'Montserrat', sans-serif;
        font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.8px; text-align: left; white-space: nowrap;
    }}
    .proy-table td {{
        padding: 0.85rem 1rem; border-bottom: 1px solid {C['border']};
        vertical-align: middle;
    }}
    .proy-table tbody tr:last-child td {{ border-bottom: none; }}
    .proy-table tbody tr.proy-data-row:hover td {{
        background: #eef5ff !important; transition: background 0.15s;
    }}
    .proy-ent    {{ font-weight:700; font-size:0.8rem; color:{C['azul_oscuro']}; white-space:nowrap; }}
    .proy-nombre {{ font-size:0.82rem; color:{C['text']}; line-height:1.5; }}
    .proy-pill {{
        display:inline-block; font-size:0.68rem; padding:4px 11px;
        border-radius:20px; font-weight:600; white-space:nowrap;
        font-family:'Montserrat',sans-serif;
    }}
    .proy-pill--empty {{ color:{C['muted']}; font-weight:400; }}
    .ctto-toggle {{
        display: inline-flex; align-items: center; gap: 6px;
        background: {C['azul_oscuro']}0f; border: 1.5px solid {C['azul_oscuro']}28;
        color: {C['azul_oscuro']}; border-radius: 8px; padding: 5px 12px;
        font-size: 0.68rem; font-weight: 700; cursor: pointer; white-space: nowrap;
        user-select: none; font-family: 'Montserrat', sans-serif;
        transition: background 0.15s, border-color 0.15s;
    }}
    .ctto-toggle:hover {{
        background: {C['azul_medio']}18; border-color: {C['azul_medio']}55; color: {C['azul_medio']};
    }}
    .ctto-toggle.open {{
        background: {C['azul_oscuro']}; border-color: {C['azul_oscuro']}; color: white;
    }}
    .ctto-arrow {{ font-size:0.55rem; transition: transform 0.2s; line-height:1; }}
    .ctto-toggle.open .ctto-arrow {{ transform: rotate(90deg); }}
    .ctto-detail-row {{ display: none; }}
    .ctto-detail-row.visible {{ display: table-row; }}
    .ctto-detail-row td {{
        padding: 0 !important; border: none !important;
        border-bottom: 3px solid {C['azul_oscuro']}25 !important;
    }}
    .ctto-panel {{
        padding: 1.1rem 1.4rem 1.2rem 1.4rem;
        background: linear-gradient(180deg, #edf3fb 0%, #f4f8fd 100%);
        border-left: 4px solid {C['azul_medio']};
    }}
    .ctto-panel-header {{ display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.9rem; }}
    .ctto-panel-title {{
        font-family: 'Montserrat', sans-serif; font-size: 0.7rem; font-weight: 800;
        text-transform: uppercase; letter-spacing: 1.2px; color: {C['azul_oscuro']};
    }}
    .ctto-panel-count {{
        background: {C['azul_medio']}; color: white; border-radius: 20px; padding: 1px 9px;
        font-size: 0.62rem; font-weight: 700; font-family: 'DM Mono', monospace;
    }}
    .ctto-panel-empty {{ font-size: 0.8rem; color: {C['muted']}; font-style: italic; padding: 0.5rem 0; }}
    .ctto-table {{ width: 100%; border-collapse: collapse; font-size: 0.77rem; }}
    .ctto-table thead tr {{ background: {C['azul_medio']}; }}
    .ctto-table th {{
        padding: 0.55rem 1rem; font-family: 'Montserrat', sans-serif; font-size: 0.59rem;
        font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px;
        color: rgba(255,255,255,0.95); text-align: left; white-space: nowrap; border: none;
    }}
    .ctto-table td {{
        padding: 0.5rem 1rem; vertical-align: middle; border: none;
        border-bottom: 1px solid rgba(0,0,0,0.06);
    }}
    .ctto-table tbody tr:last-child td {{ border-bottom: none; }}
    .ctto-table tbody tr:hover td {{ filter: brightness(0.97); }}
    td.ctto-col1, th.ctto-col1 {{ padding-left: 1.4rem !important; }}
    .ctto-valor-wrap {{ display: inline-block; }}
    .ctto-valor {{
        font-family: 'DM Mono', monospace; font-weight: 800; font-size: 0.82rem;
        white-space: nowrap; color: {C['azul_oscuro']}; display: block;
    }}
    .ctto-valor-bar {{
        display: block; height: 3px; border-radius: 2px; margin-top: 4px;
        background: {C['azul_medio']}; opacity: 0.4;
    }}
    .ctto-estado-pill {{
        display: inline-block; font-size: 0.63rem; padding: 3px 9px; border-radius: 12px;
        font-weight: 700; white-space: nowrap; font-family: 'Montserrat', sans-serif;
        letter-spacing: 0.3px;
    }}
    .ctto-objeto {{ font-size: 0.73rem; color: {C['text']}; line-height: 1.5; max-width: 320px; }}
    .ctto-proceso {{
        font-family: 'DM Mono', monospace; font-size: 0.72rem;
        color: {C['azul_medio']}; font-weight: 600; white-space: nowrap;
    }}
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:0.6rem;
        background:{C['azul_oscuro']}0d;border:1px solid {C['azul_oscuro']}22;
        border-left:3px solid {C['cian']};border-radius:6px;
        padding:0.5rem 0.85rem;margin-bottom:0.75rem">
        <span style="font-size:0.78rem;color:{C['azul_oscuro']};font-weight:600;
                     font-family:'Montserrat',sans-serif;letter-spacing:0.3px">
            Filtros disponibles:
        </span>
        <span style="font-size:0.75rem;color:{C['muted']}">
            entidad &nbsp;·&nbsp; estado del proyecto &nbsp;·&nbsp;
            estado del contrato &nbsp;·&nbsp; BPIN &nbsp;·&nbsp; nombre del proyecto
        </span>
        <span style="margin-left:auto;font-size:0.7rem;color:{C['cian']};font-weight:600;white-space:nowrap">
            Puedes combinarlos
        </span>
    </div>
    """, unsafe_allow_html=True)

    fc1, fc2, fc3 = st.columns([2, 1.4, 1.4])
    with fc1:
        busqueda = st.text_input("busqueda_proy", placeholder="Buscar por BPIN o nombre…",
                                 label_visibility="collapsed")
    with fc2:
        entidades_proy = sorted(df_f["ENTIDAD O SECRETARIA"].drop_nulls().unique().to_list())
        sel_ent_proy   = st.multiselect("Entidad", entidades_proy,
                                        placeholder="Todas las entidades",
                                        label_visibility="collapsed")
    with fc3:
        estados_proy_opts = sorted(df_f["ESTADO PROYECTO"].drop_nulls().unique().to_list())
        sel_est_proy      = st.multiselect("Estado proyecto", estados_proy_opts,
                                           placeholder="Todos los estados",
                                           label_visibility="collapsed")
    fc4, fc5 = st.columns([1.4, 4.4])
    with fc4:
        estados_cont_opts = sorted(df_f["ESTADO CONTRATO"].drop_nulls().unique().to_list())
        sel_cont_proy     = st.multiselect("Estado contrato", estados_cont_opts,
                                           placeholder="Todos los contratos",
                                           label_visibility="collapsed")

    df_proy = df_f.select(
        "ENTIDAD O SECRETARIA", "BPIN", "NOMBRE PROYECTO",
        "ESTADO PROYECTO", "ESTADO CONTRATO", "CPI", "SPI",
        "FECHA APROBACIÓN PROYECTO", "FECHA DE APERTURA DEL PRIMER PROCESO",
        "FECHA SUSCRIPCION", "FECHA ACTA INICIO",
        "HORIZONTE DEL PROYECTO", "FECHA DE FINALIZACIÓN", "FECHA DE CORTE GESPROY",
        "hito_1_val", "hito_2_val", "hito_3_val", "hito_4_val", "hito_5_val",
        "clasi_1", "clasi_2", "clasi_3", "clasi_4", "clasi_5",
    )
    if busqueda:
        term = busqueda.strip().lower()
        df_proy = df_proy.filter(
            pl.col("NOMBRE PROYECTO").str.to_lowercase().str.contains(term, literal=True)
            | pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(term, literal=True)
        )
    if sel_ent_proy:
        df_proy = df_proy.filter(pl.col("ENTIDAD O SECRETARIA").is_in(sel_ent_proy))
    if sel_est_proy:
        df_proy = df_proy.filter(pl.col("ESTADO PROYECTO").is_in(sel_est_proy))
    if sel_cont_proy:
        df_proy = df_proy.filter(pl.col("ESTADO CONTRATO").is_in(sel_cont_proy))

    df_proy  = df_proy.sort(["ENTIDAD O SECRETARIA", "NOMBRE PROYECTO"])
    n_proy   = df_proy.height
    hay_contratos = df_contratos is not None and df_contratos.height > 0

    with st.expander("Verificación del archivo de contratos", expanded=not hay_contratos):
        if _cttos_bytes is None:
            st.error("No se pudo descargar el archivo de contratos desde GitHub. Intenta subirlo manualmente desde el panel izquierdo.")
        elif df_contratos is None:
            st.error("El archivo se descargó pero no pudo leerse correctamente.")
            st.caption(_cttos_diag)
        else:
            bpins_matriz = set(
                str(b).strip().replace(".", "").replace(",", "").replace(" ", "").replace("-", "")
                for b in df_f["BPIN"].drop_nulls().to_list()
            )
            bpins_cttos = set(df_contratos["BPIN"].drop_nulls().to_list())
            en_comun    = bpins_matriz & bpins_cttos
            sin_ctto    = bpins_matriz - bpins_cttos

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Contratos cargados",      df_contratos.height)
            col_b.metric("Proyectos con contratos", len(en_comun))
            col_c.metric("Proyectos sin contratos", len(sin_ctto))

            if len(en_comun) == 0:
                st.warning("Ningún proyecto coincide con los contratos del archivo.")
            elif len(sin_ctto) > 0:
                st.info(f"{len(sin_ctto)} proyecto(s) no tienen contratos registrados en el archivo.")

    if not hay_contratos:
        st.warning("No se pudieron cargar los contratos. Puedes subirlos manualmente desde el panel izquierdo.", icon=None)

    st.markdown(
        f"<div style='font-size:0.73rem;color:{C['muted']};margin:0.4rem 0 0.6rem'>"
        f"<strong style='color:{C['azul_oscuro']}'>{n_proy}</strong> proyecto(s) encontrado(s)"
        + (f" &nbsp;·&nbsp; <span style='color:{C['verde_medio']};font-weight:600'>"
           f"{df_contratos.height} contratos cargados</span>" if hay_contratos else "")
        + "</div>",
        unsafe_allow_html=True,
    )

    if n_proy == 0:
        st.info("No hay proyectos que coincidan con los filtros aplicados.")
    else:
        rows_html_list = []
        for idx, r in enumerate(df_proy.to_dicts()):
            entidad  = html.escape(r.get("ENTIDAD O SECRETARIA") or "—")
            bpin     = html.escape(str(r.get("BPIN") or "—"))
            nombre   = html.escape(r.get("NOMBRE PROYECTO") or "—")
            est_proy = r.get("ESTADO PROYECTO") or ""
            est_cont = r.get("ESTADO CONTRATO") or ""
            row_id   = f"proy-{idx}"

            es_susp = est_cont.strip().upper() == "SUSPENDIDO"
            bg_susp = 'style="background:#fff7ed"' if es_susp else ""

            bpin_norm = (
                str(bpin).strip()
                .replace(".", "").replace("-", "").replace(",", "").replace(" ", "")
            )
            n_cttos = 0
            if hay_contratos:
                n_cttos = df_contratos.filter(pl.col("BPIN") == bpin_norm).height
            badge = (
                f'<span style="background:{C["azul_medio"]};color:white;border-radius:10px;'
                f'padding:1px 6px;font-size:0.58rem;margin-left:4px;font-weight:700">{n_cttos}</span>'
                if n_cttos > 0 else
                f'<span style="background:#e5e7eb;color:{C["muted"]};border-radius:10px;'
                f'padding:1px 6px;font-size:0.58rem;margin-left:4px">0</span>'
            )

            panel_html = _contratos_panel(bpin, df_contratos)

            rows_html_list.append(f"""
            <tr class="proy-data-row" {bg_susp}>
                <td class="proy-ent">{entidad}</td>
                <td><span class="bpin-tag">{bpin}</span></td>
                <td class="proy-nombre">{nombre}</td>
                <td>{_estado_tooltip_html(est_proy, r)}</td>
                <td>{_pill(est_cont, ESTADO_CONT_COLORS)}</td>
                <td style="white-space:nowrap">
                    <span class="ctto-toggle" data-target="{row_id}">
                        <span class="ctto-arrow">▶</span> Contratos{badge}
                    </span>
                </td>
            </tr>
            <tr class="ctto-detail-row" id="{row_id}">
                <td colspan="6">{panel_html}</td>
            </tr>""")

        st.markdown(f"""
        <table class="proy-table">
        <thead><tr>
            <th style="width:150px">Entidad / Secretaría</th>
            <th style="width:120px">BPIN</th>
            <th>Nombre del proyecto</th>
            <th style="width:190px">Estado proyecto</th>
            <th style="width:165px">Estado contrato</th>
            <th style="width:110px">Contratos</th>
        </tr></thead>
        <tbody>{"".join(rows_html_list)}</tbody>
        </table>
        """, unsafe_allow_html=True)

# ── TAB 3: Evaluación del modelo ──────────────────────────────────────────────
with tab_evaluacion:
    st.markdown("<div class='section-heading'>Evaluación del modelo ejecutor</div>", unsafe_allow_html=True)

    modelo_sel = st.radio(
        "Ejecutor",
        ["Departamento de Sucre", "Descentralizadas"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    if modelo_sel == "Departamento de Sucre":
        df_eval, cols_eval_ok, eval_errores, df_eval_raw = procesar_eval_sucre(file_bytes)
        col_entidad    = "ENTIDAD O SECRETARIA"
        label_entidad  = "Entidad / Secretaría"
        contexto_error = "Departamento de Sucre"
    else:
        df_eval, cols_eval_ok, eval_errores, df_eval_raw = procesar_descentralizadas(file_bytes)
        col_entidad    = "EJECUTOR"
        label_entidad  = "Ejecutor"
        contexto_error = "Descentralizadas"

    if eval_errores:
        _render_eval_errors(eval_errores, contexto_error)

    if df_eval is None or df_eval.height == 0:
        st.info(f"No se encontraron datos de evaluación para «{modelo_sel}».")
    else:
        max_score = 100.0

        st.markdown(f"""
        <style>
        .eval-table {{
            width: 100%; border-collapse: collapse; font-size: 0.83rem;
            background: #ffffff; border-radius: 8px; overflow: hidden; margin-bottom: 0.5rem;
        }}
        .eval-table thead tr {{ background: {C['azul_oscuro']}; color: white; }}
        .eval-table th {{
            padding: 0.65rem 1rem; font-size: 0.63rem; font-weight: 700;
            text-transform: uppercase; letter-spacing: 0.8px; text-align: left;
        }}
        .eval-table td {{
            padding: 0.6rem 1rem; border-bottom: 1px solid {C['border']};
            vertical-align: top; background: #ffffff;
        }}
        .eval-table tbody tr:nth-child(even) td {{ background: #f7fafd; }}
        .eval-table tbody tr:last-child td {{ border-bottom: none; }}
        .eval-table tbody tr:hover td {{ background: #e8f3ff !important; }}
        .eval-score-pill {{
            font-family: 'DM Mono', monospace; font-weight: 700; font-size: 0.88rem;
            padding: 3px 12px; border-radius: 20px; display: inline-block;
        }}
        .eval-comment {{
            font-size: 0.75rem; color: {C['muted']}; line-height: 1.6;
        }}
        .eval-comment strong {{ color: {C['text']}; font-weight: 600; }}
        .eval-no-aplica {{
            font-size: 0.72rem; color: {C['muted']}; font-style: italic;
        }}
        </style>
        """, unsafe_allow_html=True)

        tabs_eval = st.tabs([
            "Desempeño en contratación",
            "Información a tiempo",
            "Ejecución del proyecto",
            "Calidad de la información",
        ])

        for i, (col_cal, label_cal) in enumerate(zip(COLS_EVAL, COLS_EVAL_LABELS)):
            with tabs_eval[i]:
                if col_cal not in cols_eval_ok:
                    st.info(f"No hay datos disponibles para «{label_cal}» debido a errores en el archivo.")
                    continue

                filas = []
                for row in df_eval.sort(col_cal, descending=True, nulls_last=True).to_dicts():
                    nombre = row.get(col_entidad) or "Sin nombre"
                    score  = row.get(col_cal)

                    # ── Construir comentario ──────────────────────────────────
                    comentario_html = "—"
                    if df_eval_raw is not None and col_cal in df_eval_raw.columns:
                        sub         = df_eval_raw.filter(pl.col(col_entidad) == nombre)
                        n_total     = sub.height
                        n_con_cal   = int(sub[col_cal].drop_nulls().len())
                        n_no_aplica = n_total - n_con_cal
                        n_cero      = int((sub[col_cal] == 0).sum())  if n_con_cal > 0 else 0
                        n_max       = int((sub[col_cal] == 100).sum()) if n_con_cal > 0 else 0
                        vals_ok     = sub[col_cal].drop_nulls()
                        v_min       = float(vals_ok.min()) if n_con_cal > 0 else None
                        v_max_v     = float(vals_ok.max()) if n_con_cal > 0 else None

                        def _bpin_proy(val_filtro):
                            f  = sub.filter(pl.col(col_cal) == val_filtro)
                            if f.height == 0: return None
                            bp = (f.to_dicts()[0].get("BPIN") or "").strip()
                            return bp if bp else None

                        proy_bajo = _bpin_proy(v_min)   if v_min  is not None and v_min  < 60  else None
                        proy_alto = _bpin_proy(v_max_v) if v_max_v is not None and v_max_v >= 80 else None

                        partes = []

                        if score is None:
                            # Sin calificación → todos son no aplicables
                            partes.append(
                                f"Ninguno de los <strong>{n_total} proyecto(s)</strong> de esta entidad "
                                f"aplica para este criterio: no cumplen las condiciones requeridas "
                                f"para que se calcule esta calificación "
                                f"(por ejemplo, estado del proyecto, tipo de contrato o etapa de ejecución)."
                            )
                            comentario_html = " ".join(partes)
                            filas.append(f"""<tr>
                                <td class="entidad-name">{html.escape(nombre)}</td>
                                <td style="color:{C['muted']}">—</td>
                                <td class="eval-comment eval-no-aplica">{comentario_html}</td>
                            </tr>""")
                            continue

                        # ── Apertura: cuántos proyectos se usaron ────────────
                        if n_no_aplica == 0:
                            partes.append(
                                f"Calificación calculada sobre los "
                                f"<strong>{n_con_cal} {'proyecto' if n_con_cal == 1 else 'proyectos'}</strong> "
                                f"de la entidad que aplican para este criterio."
                            )
                        else:
                            partes.append(
                                f"Calificación calculada sobre "
                                f"<strong>{n_con_cal} de {n_total} proyectos</strong>. "
                                f"Los {n_no_aplica} restantes son <em>no aplicables</em>: "
                                f"no cumplen las condiciones requeridas para que este criterio se calcule "
                                f"(por ejemplo, estado del proyecto, tipo de contrato o etapa de ejecución)."
                            )

                        # ── Dispersión ───────────────────────────────────────
                        if v_min is not None and v_max_v is not None and n_con_cal > 1:
                            diferencia = v_max_v - v_min
                            if diferencia < 10:
                                partes.append(
                                    f"Los resultados son homogéneos "
                                    f"(entre {v_min:.0f} y {v_max_v:.0f} puntos)."
                                )
                            elif diferencia >= 50:
                                partes.append(
                                    f"Existe una brecha importante: el resultado más bajo fue "
                                    f"{v_min:.0f} puntos y el más alto {v_max_v:.0f}, "
                                    f"lo que refleja situaciones muy distintas entre proyectos."
                                )
                            else:
                                partes.append(
                                    f"Los proyectos obtuvieron resultados entre "
                                    f"{v_min:.0f} y {v_max_v:.0f} puntos."
                                )

                        # ── Proyectos que bajan el promedio ──────────────────
                        if n_cero == 1:
                            extra = f" (BPIN {html.escape(proy_bajo)})" if proy_bajo and v_min == 0 else ""
                            partes.append(
                                f"Un proyecto{extra} obtuvo cero puntos, "
                                f"lo que reduce el promedio general de la entidad."
                            )
                        elif n_cero > 1:
                            partes.append(
                                f"{n_cero} proyectos obtuvieron cero puntos, "
                                f"lo que arrastra el promedio hacia abajo."
                            )
                        elif proy_bajo:
                            partes.append(
                                f"El proyecto con menor resultado es el BPIN {html.escape(proy_bajo)} "
                                f"con {v_min:.0f} puntos."
                            )

                        # ── Proyectos que suben el promedio ──────────────────
                        if n_max == 1 and n_con_cal > 1:
                            extra = f" (BPIN {html.escape(proy_alto)})" if proy_alto else ""
                            partes.append(
                                f"Por otro lado, un proyecto{extra} alcanzó 100 puntos."
                            )
                        elif n_max > 1:
                            partes.append(
                                f"Por otro lado, {n_max} proyectos alcanzaron 100 puntos."
                            )
                        elif proy_alto and n_max == 0 and n_con_cal > 1:
                            partes.append(
                                f"El proyecto con mejor desempeño es el BPIN "
                                f"{html.escape(proy_alto)} con {v_max_v:.0f} puntos."
                            )

                        comentario_html = " ".join(partes) if partes else "—"

                    # ── Pill de score ─────────────────────────────────────────
                    color_bar, nivel = eval_color(score, max_score)
                    bg_map = {
                        C["verde_medio"]: "#d1fae5",
                        C["cian"]:        "#e0f7fa",
                        C["naranja"]:     "#fff7ed",
                        C["salmon"]:      "#fee2e2",
                    }
                    bg = bg_map.get(color_bar, "#f1f5f9")

                    filas.append(f"""<tr>
                        <td class="entidad-name">{html.escape(nombre)}</td>
                        <td style="white-space:nowrap">
                            <span class="eval-score-pill" style="background:{bg};color:{color_bar}">
                                {score:.2f}
                            </span>
                        </td>
                        <td class="eval-comment">{comentario_html}</td>
                    </tr>""")

                if not filas:
                    st.info("No hay registros con calificación para este criterio.")
                else:
                    st.markdown(f"""
                    <table class="eval-table">
                    <thead><tr>
                        <th style="width:22%">{label_entidad}</th>
                        <th style="width:14%">Calificación promedio &nbsp;(escala 0–{max_score:.0f})</th>
                        <th>Comentario</th>
                    </tr></thead>
                    <tbody>{"".join(filas)}</tbody>
                    </table>
                    """, unsafe_allow_html=True)

    # ── Reporte semanal ───────────────────────────────────────────────────────
    st.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>Reporte semanal de alertas</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.78rem;color:{C['muted']};margin-bottom:1rem'>"
        "Conteo de proyectos con semáforo <strong>naranja, rojo o negro</strong> por dependencia y estado, "
        "basado en los hitos activos. Incluye solo los filtros activos del panel lateral.</div>",
        unsafe_allow_html=True,
    )

    # Claves de alerta que se consideran (naranja / rojo / negro)
    ALERTAS_NRN = {
        "hito_1_val": ["101-150", "151-180", ">180"],
        "hito_2_val": ["101-150", "151-180", ">180"],
        "hito_3_val": ["16-30", "31-45", ">45"],
        "hito_4_val": ["1.1-3", "3.1-6", ">6"],
    }

    # Colores por nivel de alerta para los pills
    ALERTA_COLOR = {
        # naranja
        "101-150": (C["naranja"], "#fff7ed"), "31-45": (C["naranja"], "#fff7ed"),
        "1.1-3":   (C["naranja"], "#fff7ed"), "16-30": (C["naranja"], "#fff7ed"),
        # rojo
        "151-180": (C["naranja_osc"], "#ffedd5"), "46-60": (C["naranja_osc"], "#ffedd5"),
        "3.1-6":   (C["naranja_osc"], "#ffedd5"),
        # negro
        ">180":    (C["text"], "#e2e8f0"), ">60": (C["text"], "#e2e8f0"),
        ">6":      (C["text"], "#e2e8f0"), ">45": (C["text"], "#e2e8f0"),
    }

    def _pill_alerta(clasi):
        fg, bg = ALERTA_COLOR.get(clasi, (C["muted"], "#f1f5f9"))
        return (
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'border:1px solid {fg}40;border-radius:12px;padding:1px 7px;'
            f'font-size:0.63rem;font-weight:700;margin:1px 2px;white-space:nowrap">'
            f'{clasi}</span>'
        )

    def _comentario_reporte(estado_up, conteos_hito, n_total_estado):
        """Genera comentario dinámico basado en los conteos reales de alertas."""
        partes = []
        n_alerta = sum(conteos_hito.values())

        if n_alerta == 0:
            return "Ningún proyecto presenta alertas en este estado."

        pct = round(n_alerta / n_total_estado * 100) if n_total_estado else 0
        partes.append(
            f"<strong>{n_alerta} de {n_total_estado} proyecto(s)</strong> ({pct}%) "
            f"presentan alertas que requieren atención."
        )

        if estado_up == "SIN CONTRATAR":
            # H1 sin apertura
            h1 = {k: v for k, v in conteos_hito.items() if k in ALERTAS_NRN["hito_1_val"]}
            h2 = {k: v for k, v in conteos_hito.items() if k in ALERTAS_NRN["hito_2_val"]}
            n_h1 = sum(h1.values())
            n_h2 = sum(h2.values())
            if n_h1:
                partes.append(
                    f"<strong>{n_h1}</strong> sin apertura del proceso precontractual "
                    f"(hito 1: días desde aprobación sin contratar)."
                )
            if n_h2:
                partes.append(
                    f"<strong>{n_h2}</strong> con proceso abierto pero sin contrato suscrito "
                    f"(hito 2: días desde apertura)."
                )
            # Máxima alerta
            n_negro_h1 = conteos_hito.get(">180", 0)
            n_negro_h2 = conteos_hito.get(">180", 0)  # comparten clave
            if n_negro_h1 + n_negro_h2 > 0:
                partes.append(
                    f"Se detectaron <strong>{n_negro_h1 + n_negro_h2} proyecto(s) en alerta negra</strong> "
                    f"(más de 180 días sin avance). Requieren intervención urgente."
                )

        elif estado_up == "CONTRATADO SIN ACTA DE INICIO":
            n_rojo  = conteos_hito.get("31-45", 0)
            n_negro = conteos_hito.get(">45", 0)
            n_nar   = conteos_hito.get("16-30", 0)
            if n_nar:
                partes.append(
                    f"<strong>{n_nar}</strong> entre 16 y 30 días sin formalizar el acta de inicio."
                )
            if n_rojo:
                partes.append(
                    f"<strong>{n_rojo}</strong> entre 31 y 45 días — situación crítica sin acta de inicio."
                )
            if n_negro:
                partes.append(
                    f"<strong>{n_negro}</strong> superan los 45 días — requieren intervención urgente."
                )

        elif estado_up == "CONTRATADO EN EJECUCIÓN":
            n_nar   = conteos_hito.get("1.1-3", 0)
            n_rojo  = conteos_hito.get("3.1-6", 0)
            n_negro = conteos_hito.get(">6",    0)
            if n_nar:
                partes.append(
                    f"<strong>{n_nar}</strong> con horizonte vencido entre 1 y 3 meses."
                )
            if n_rojo:
                partes.append(
                    f"<strong>{n_rojo}</strong> con horizonte vencido entre 3 y 6 meses — rezago significativo."
                )
            if n_negro:
                partes.append(
                    f"<strong>{n_negro}</strong> con más de 6 meses de horizonte vencido — "
                    f"requieren revisión del plan de ejecución."
                )

        return " ".join(partes)

    # ── Configuración de estados y sus hitos ──────────────────────────────────
    REPORTE_CONFIG = [
        {
            "estado":      "SIN CONTRATAR",
            "label":       "Sin contratar",
            "hitos":       [("clasi_1", "hito_1_val", "H1 · Sin apertura"),
                            ("clasi_2", "hito_2_val", "H2 · Con apertura")],
            "color_est":   (C["cian"], "#e0f7fa"),
        },
        {
            "estado":      "CONTRATADO SIN ACTA DE INICIO",
            "label":       "Contratado sin acta de inicio",
            "hitos":       [("clasi_3", "hito_3_val", "H3 · Sin acta")],
            "color_est":   (C["azul_medio"], "#dbeafe"),
        },
        {
            "estado":      "CONTRATADO EN EJECUCIÓN",
            "label":       "Contratado en ejecución",
            "hitos":       [("clasi_4", "hito_4_val", "H4 · En ejecución rezagado")],
            "color_est":   (C["verde_medio"], "#d1fae5"),
        },
    ]

    # ── Calcular conteos por entidad y estado ─────────────────────────────────
    entidades_reporte = sorted(df_f["ENTIDAD O SECRETARIA"].drop_nulls().unique().to_list())

    reporte_rows = []
    for cfg in REPORTE_CONFIG:
        estado_up  = cfg["estado"]
        df_estado  = df_f.filter(pl.col("ESTADO PROYECTO") == estado_up)
        n_total_est = df_estado.height

        if n_total_est == 0:
            continue

        # Conteo global de alertas NRN para este estado (todas las entidades)
        conteos_global: dict = {}
        for clasi_col, hito_col, _ in cfg["hitos"]:
            alertas_validas = ALERTAS_NRN.get(hito_col, [])
            for alerta in alertas_validas:
                n = int(df_estado.filter(pl.col(clasi_col) == alerta).height)
                if n > 0:
                    conteos_global[alerta] = conteos_global.get(alerta, 0) + n

        n_total_alerta = sum(conteos_global.values())

        # Conteo por entidad
        filas_entidad = []
        for ent in entidades_reporte:
            df_ent = df_estado.filter(pl.col("ENTIDAD O SECRETARIA") == ent)
            if df_ent.height == 0:
                continue

            conteos_ent: dict = {}
            for clasi_col, hito_col, _ in cfg["hitos"]:
                for alerta in ALERTAS_NRN.get(hito_col, []):
                    n = int(df_ent.filter(pl.col(clasi_col) == alerta).height)
                    if n > 0:
                        conteos_ent[alerta] = conteos_ent.get(alerta, 0) + n

            n_ent_alerta = sum(conteos_ent.values())
            if n_ent_alerta == 0:
                continue

            pills = "".join(_pill_alerta(k) for k in sorted(conteos_ent, key=lambda x: conteos_ent[x], reverse=True))
            filas_entidad.append((ent, df_ent.height, n_ent_alerta, pills, conteos_ent))

        if not filas_entidad:
            continue

        # Comentario global del estado
        comentario_global = _comentario_reporte(estado_up, conteos_global, n_total_alerta)
        fg_est, bg_est = cfg["color_est"]

        # Fila de encabezado del estado (agrupa las entidades)
        reporte_rows.append(
            f'<tr style="background:{bg_est}20">'
            f'<td colspan="4" style="padding:0.55rem 0.9rem;border-bottom:2px solid {fg_est}30">'
            f'<span style="font-family:\'Montserrat\',sans-serif;font-size:0.67rem;font-weight:800;'
            f'text-transform:uppercase;letter-spacing:0.8px;color:{fg_est}">'
            f'{cfg["label"]}</span>'
            f'<span style="font-size:0.7rem;color:{C["muted"]};font-weight:400;margin-left:0.6rem">'
            f'{n_total_est} proyecto(s) en este estado · {n_total_alerta} con alerta</span>'
            f'</td></tr>'
        )

        for ent, n_ent_total, n_ent_alerta, pills_html, conteos_ent in filas_entidad:
            com_ent = _comentario_reporte(estado_up, conteos_ent, n_ent_alerta)
            reporte_rows.append(f"""<tr>
                <td style="font-weight:600;font-size:0.81rem;color:{C['azul_oscuro']};
                    padding:0.65rem 0.9rem;vertical-align:top">
                    {html.escape(ent)}
                </td>
                <td style="padding:0.65rem 0.9rem;vertical-align:top">
                    <span style="display:inline-block;background:{bg_est};color:{fg_est};
                        border:1px solid {fg_est}40;border-radius:12px;padding:2px 9px;
                        font-size:0.65rem;font-weight:700;white-space:nowrap">
                        {html.escape(cfg['label'])}
                    </span>
                </td>
                <td style="padding:0.65rem 0.9rem;vertical-align:top;text-align:center">
                    <div style="font-family:'DM Mono',monospace;font-size:1.1rem;font-weight:800;
                        color:{C['azul_oscuro']};line-height:1">{n_ent_alerta}</div>
                    <div style="font-size:0.62rem;color:{C['muted']};margin-top:2px">
                        de {n_ent_total}
                    </div>
                    <div style="margin-top:4px">{pills_html}</div>
                </td>
                <td style="padding:0.65rem 0.9rem;vertical-align:top;
                    font-size:0.75rem;color:{C['text']};line-height:1.6">
                    {com_ent}
                </td>
            </tr>""")

    _color_muted = C["muted"]
    st.markdown(f"""
    <style>
    .reporte-table {{
        width: 100%; border-collapse: collapse; font-size: 0.83rem;
        background: #ffffff; border-radius: 10px; overflow: hidden;
        box-shadow: 0 2px 16px rgba(0,40,90,0.09);
    }}
    .reporte-table thead tr {{ background: {C['azul_oscuro']}; color: white; }}
    .reporte-table th {{
        padding: 0.7rem 0.9rem; font-family: 'Montserrat', sans-serif;
        font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.8px; text-align: left;
    }}
    .reporte-table td {{ border-bottom: 1px solid {C['border']}; }}
    .reporte-table tbody tr:last-child td {{ border-bottom: none; }}
    .reporte-table tbody tr:hover td {{ background: #f0f6ff !important; transition: background 0.12s; }}
    </style>
    <table class="reporte-table">
    <thead><tr>
        <th style="width:20%">Dependencia</th>
        <th style="width:22%">Estado del proyecto</th>
        <th style="width:15%">N.° proyectos<br>con alerta</th>
        <th>Comentario</th>
    </tr></thead>
    <tbody>{"".join(reporte_rows) if reporte_rows else
        f'<tr><td colspan="4" style="padding:1.2rem;color:{_color_muted};font-style:italic;text-align:center">'
        f'No se encontraron proyectos con alertas naranja, roja o negra en los filtros activos.</td></tr>'
    }
    </tbody>
    </table>
    """, unsafe_allow_html=True)

# ── TAB 4: Exportar ───────────────────────────────────────────────────────────
with tab_exportar:
    st.markdown("<div class='section-heading'>Descargar reporte</div>", unsafe_allow_html=True)
    st.markdown(
        "El archivo incluye hasta **4 hojas**: "
        "**Resumen por entidad** con promedios por hito y nivel de alerta, "
        "**Detalle proyectos** con cada proyecto y sus fechas de cálculo, "
        "**Evaluación Sucre** y **Evaluación Descentralizadas** con las calificaciones "
        "promedio por entidad (semáforo verde ≥80, azul ≥60, naranja ≥40, rojo <40).",
        unsafe_allow_html=False,
    )
    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)

    st.download_button(
        label="Descargar reporte Excel",
        data=generar_excel(
            df_f, agrupacion, clasi_por_entidad,
            df_eval_sucre=_df_eval_sucre, cols_eval_sucre=_cols_eval_sucre,
            df_eval_desc=_df_eval_desc,   cols_eval_desc=_cols_eval_desc,
        ),
        file_name=f"regalias_seguimiento_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ── TAB 5: Comunicaciones ─────────────────────────────────────────────────────
with tab_comunicaciones:
    st.markdown("<div class='section-heading'>Comunicaciones</div>", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,{C['azul_oscuro']}08,{C['cian']}12);
        border:1px solid {C['cian']}40; border-left:4px solid {C['cian']};
        border-radius:10px; padding:1rem 1.3rem; margin-bottom:1.2rem;
        font-size:0.8rem; color:{C['text']}; line-height:1.7">
        <div style="font-family:'Montserrat',sans-serif;font-size:0.72rem;font-weight:800;
            text-transform:uppercase;letter-spacing:1px;color:{C['cian']};margin-bottom:0.5rem">
            Cómo funciona
        </div>
        <b>1. Filtra</b> los proyectos por hito, nivel de alerta y entidad. &nbsp;
        <b>2. Selecciona</b> con el checkbox los proyectos que quieres incluir. &nbsp;
        <b>3. Edita</b> el texto generado si lo necesitas. &nbsp;
        <b>4. Copia</b> el texto con el botón y pégalo en tu correo.
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <style>
    .com-card {{
        background: {C['white']}; border-radius: 12px; padding: 1.3rem 1.5rem;
        margin-bottom: 1rem; box-shadow: 0 1px 8px rgba(0,40,90,0.08);
        border-left: 4px solid {C['azul_medio']};
    }}
    .com-card-title {{
        font-family: 'Montserrat', sans-serif; font-size: 0.7rem; font-weight: 800;
        text-transform: uppercase; letter-spacing: 1.1px;
        color: {C['azul_oscuro']}; margin-bottom: 0.7rem;
    }}
    .com-counter {{ font-size: 0.72rem; color: {C['muted']}; margin: 0.5rem 0 0.9rem; }}
    .com-counter strong {{ color: {C['azul_oscuro']}; }}
    </style>
    """, unsafe_allow_html=True)

    HITO_LABELS_COM = {
        "H1 · Sin contratar sin apertura":    ("hito_1_val", "clasi_1"),
        "H2 · Sin contratar con apertura":    ("hito_2_val", "clasi_2"),
        "H3 · Contratado sin acta de inicio": ("hito_3_val", "clasi_3"),
        "H4 · En ejecución rezagado":         ("hito_4_val", "clasi_4"),
        "H5 · Proyectos terminados":          ("hito_5_val", "clasi_5"),
    }
    CLASI_OPTIONS_COM = {
        "Todos":   None,
        "Verde":   ["0-100", "0-30", "0-1", "0-15"],
        "Naranja": ["101-150", "31-45", "1.1-3", "16-30"],
        "Rojo":    ["151-180", "46-60", "3.1-6", "31-45"],
        "Negro":   [">180", ">60", ">6", ">45"],
    }
    HITO_DESCRIPCION_COM = {
        "H1 · Sin contratar sin apertura":    "proyectos sin contratar y sin apertura del proceso precontractual",
        "H2 · Sin contratar con apertura":    "proyectos sin contratar con proceso precontractual abierto",
        "H3 · Contratado sin acta de inicio": "proyectos contratados sin acta de inicio firmada",
        "H4 · En ejecución rezagado":         "proyectos en ejecución con horizonte vencido",
        "H5 · Proyectos terminados":          "proyectos terminados pendientes de cierre",
    }

    st.markdown('<div class="com-card"><div class="com-card-title">Paso 1 &nbsp;·&nbsp; Seleccionar proyectos</div>', unsafe_allow_html=True)
    ca, cb, cc = st.columns([2, 1.4, 1.8])
    with ca:
        com_hito_label  = st.selectbox("Hito", list(HITO_LABELS_COM.keys()), key="com_hito", label_visibility="collapsed")
    with cb:
        com_clasi_label = st.selectbox("Clasificación", list(CLASI_OPTIONS_COM.keys()), key="com_clasi", label_visibility="collapsed")
    with cc:
        entidades_com = ["Todas"] + sorted(df_f["ENTIDAD O SECRETARIA"].drop_nulls().unique().to_list())
        com_entidad   = st.selectbox("Entidad", entidades_com, key="com_entidad", label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

    com_hito_col, com_clasi_col = HITO_LABELS_COM[com_hito_label]
    df_com = (
        df_f
        .filter(~pl.col(com_hito_col).is_null())
        .select("ENTIDAD O SECRETARIA", "BPIN", "NOMBRE PROYECTO", "ESTADO PROYECTO", com_hito_col, com_clasi_col)
        .sort(["ENTIDAD O SECRETARIA", com_hito_col], descending=[False, True])
    )
    clasi_vals = CLASI_OPTIONS_COM[com_clasi_label]
    if clasi_vals:
        df_com = df_com.filter(pl.col(com_clasi_col).is_in(clasi_vals))
    if com_entidad != "Todas":
        df_com = df_com.filter(pl.col("ENTIDAD O SECRETARIA") == com_entidad)

    n_com = df_com.height
    st.markdown(
        f'<div class="com-counter"><strong>{n_com}</strong> proyecto(s) encontrado(s)</div>',
        unsafe_allow_html=True,
    )

    if n_com == 0:
        st.info("No hay proyectos con este hito y clasificación. Ajusta los filtros.")
    else:
        df_com_pd = df_com.to_pandas()
        df_com_pd.insert(0, "Incluir", True)
        df_com_pd = df_com_pd.rename(columns={
            com_hito_col:           "Días",
            com_clasi_col:          "Alerta",
            "ENTIDAD O SECRETARIA": "Entidad",
            "NOMBRE PROYECTO":      "Nombre del proyecto",
            "ESTADO PROYECTO":      "Estado",
        })

        edited = st.data_editor(
            df_com_pd[["Incluir", "Entidad", "BPIN", "Nombre del proyecto", "Estado", "Días", "Alerta"]],
            column_config={
                "Incluir":             st.column_config.CheckboxColumn("✓", width="small"),
                "Entidad":             st.column_config.TextColumn("Entidad", width="medium"),
                "BPIN":                st.column_config.TextColumn("BPIN", width="small"),
                "Nombre del proyecto": st.column_config.TextColumn("Nombre del proyecto", width="large"),
                "Estado":              st.column_config.TextColumn("Estado", width="medium"),
                "Días":                st.column_config.NumberColumn("Días", format="%.0f", width="small"),
                "Alerta":              st.column_config.TextColumn("Alerta", width="small"),
            },
            hide_index=True,
            width="stretch",
            key="com_editor",
        )

        proyectos_sel = edited[edited["Incluir"] == True]
        n_sel = len(proyectos_sel)
        st.markdown(
            f'<div class="com-counter"><strong>{n_sel}</strong> proyecto(s) seleccionado(s) para el correo</div>',
            unsafe_allow_html=True,
        )

        if n_sel > 0:
            st.markdown(f'<div class="com-card" style="border-left-color:{C["cian"]}"><div class="com-card-title">Paso 2 &nbsp;·&nbsp; Cuerpo del correo</div>', unsafe_allow_html=True)

            HITO_CALC_EXPLICACION = {
                "H1 · Sin contratar sin apertura": (
                    "hito_1_val",
                    "Este hito mide los días transcurridos desde la aprobación del proyecto "
                    "hasta la fecha de corte GESPROY, sin que se haya abierto ningún proceso precontractual.",
                ),
                "H2 · Sin contratar con apertura": (
                    "hito_2_val",
                    "Este hito mide los días entre la apertura del primer proceso precontractual "
                    "y la firma del acta de inicio del contrato.",
                ),
                "H3 · Contratado sin acta de inicio": (
                    "hito_3_val",
                    "Este hito mide los días transcurridos desde la suscripción del contrato "
                    "hasta la fecha de corte GESPROY, sin que se haya firmado el acta de inicio.",
                ),
                "H4 · En ejecución rezagado": (
                    "hito_4_val",
                    "Este hito mide los meses de retraso del proyecto respecto a su horizonte "
                    "de ejecución previsto, bajo condición de CPI=0 y SPI=0.",
                ),
                "H5 · Proyectos terminados": (
                    "hito_5_val",
                    "Este hito mide los días transcurridos desde la fecha de finalización "
                    "registrada del proyecto hasta la fecha de corte GESPROY.",
                ),
            }

            def _lista_proyectos(df_sel):
                hito_key_com, calc_exp = HITO_CALC_EXPLICACION[com_hito_label]
                lineas = []
                for _, row in df_sel.iterrows():
                    d       = row["Días"]
                    alerta  = str(row["Alerta"]) if row["Alerta"] == row["Alerta"] else None
                    mensaje_sem = ""
                    if alerta and hito_key_com in SEMAFOROS and alerta in SEMAFOROS[hito_key_com]:
                        _, _, mensaje_sem = SEMAFOROS[hito_key_com][alerta]
                    es_h4 = com_hito_label == "H4 · En ejecución rezagado"
                    if d == d and d is not None:
                        d_str = f"{d/30:.1f} meses ({d:.0f} días)" if es_h4 else f"{d:.0f} días"
                    else:
                        d_str = "—"
                    lineas.append(
                        f"  • BPIN {row['BPIN']}  —  {row['Nombre del proyecto']}\n"
                        f"    {mensaje_sem}\n"
                        f"    Tiempo transcurrido: {d_str}.\n"
                        f"    ({calc_exp})"
                    )
                return "\n\n".join(lineas)

            hito_desc  = HITO_DESCRIPCION_COM[com_hito_label]
            lista_txt  = _lista_proyectos(proyectos_sel)
            cuerpo_def = (
                f"Estimados,\n\n"
                f"Por medio del presente, nos permitimos informar que en el marco del seguimiento "
                f"y evaluación de proyectos de regalías, se han identificado {n_sel} proyecto(s) "
                f"con {hito_desc}:\n\n"
                f"{lista_txt}\n\n"
                f"Solicitamos respetuosamente su atención a estos proyectos y la adopción de las "
                f"medidas necesarias para avanzar en su gestión.\n\n"
                f"Quedamos atentos a cualquier inquietud.\n\n"
                f"Cordialmente,\n"
                f"Secretaría Técnica · Regalías\n"
                f"Departamento de Sucre"
            )

            _body_key = f"com_cuerpo_{com_hito_label}_{com_clasi_label}_{com_entidad}_{n_sel}"

            com_cuerpo = st.text_area(
                "Edita el texto si lo necesitas, luego cópialo con el botón",
                value=cuerpo_def,
                height=400,
                key=_body_key,
                label_visibility="visible",
            )

            _cuerpo_js = json.dumps(com_cuerpo)
            components.html(f"""
            <style>
            .copy-btn {{
                display:inline-flex; align-items:center; gap:8px;
                background:#f1f5f9; border:1.5px solid #cbd5e1;
                color:#1a2332; border-radius:7px; padding:9px 22px;
                font-size:0.76rem; font-weight:700; cursor:pointer;
                font-family:'Montserrat',sans-serif; transition:all 0.15s;
            }}
            .copy-btn:hover {{ background:#e2e8f0; border-color:#94a3b8; }}
            .copy-btn.copied {{ background:#d1fae5; border-color:#059669; color:#065f46; }}
            </style>
            <div style="margin-top:8px">
                <button class="copy-btn" id="btn_cuerpo" onclick="doCopy()">
                    Copiar texto del correo
                </button>
            </div>
            <script>
            var _texto = {_cuerpo_js};
            function doCopy() {{
                var btn = document.getElementById('btn_cuerpo');
                function onOk() {{
                    btn.innerText = '✓ Copiado';
                    btn.classList.add('copied');
                    setTimeout(function() {{
                        btn.innerText = 'Copiar texto del correo';
                        btn.classList.remove('copied');
                    }}, 2000);
                }}
                if (navigator.clipboard && navigator.clipboard.writeText) {{
                    navigator.clipboard.writeText(_texto).then(onOk).catch(function() {{
                        fallback(); onOk();
                    }});
                }} else {{
                    fallback(); onOk();
                }}
            }}
            function fallback() {{
                var ta = document.createElement('textarea');
                ta.value = _texto;
                ta.style.position = 'fixed';
                ta.style.opacity  = '0';
                document.body.appendChild(ta);
                ta.focus(); ta.select();
                try {{ document.execCommand('copy'); }} catch(e) {{}}
                document.body.removeChild(ta);
            }}
            </script>
            """, height=55)

            st.markdown("</div>", unsafe_allow_html=True)
