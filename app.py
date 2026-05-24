"""
app.py — Orquestador principal de la aplicación Streamlit.
Importa todos los módulos, gestiona sidebar, filtros, KPIs y renderiza
las pestañas según la vista seleccionada (Departamento / Descentralizadas / Municipios).
"""
from constants import (
    C, INTERVALOS, SEMAFOROS, COLS_EVAL, COLS_EVAL_LABELS,
    TABLA_ESPERADA, TABLA_DESCENTRALIZADAS, COLUMNAS_ESPERADAS,
    TIPO_LABEL, TIPO_EJEMPLO, inject_css,
)
from data import (
    procesar, procesar_contratos, procesar_eval_sucre, procesar_descentralizadas,
    procesar_descentralizadas_hitos, procesar_municipios,
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


# ─────────────────────────────────────────────────────────────────────────────
# GUÍA DE HITOS — metadata + helper para la pestaña explicativa
# ─────────────────────────────────────────────────────────────────────────────
# Cada hito se describe con la misma estructura: estados que aplican,
# condiciones adicionales, la fórmula que se calcula y su unidad. El semáforo
# (rangos + mensajes) se lee dinámicamente desde SEMAFOROS para que la guía
# refleje siempre la fuente de verdad del cálculo.
HITOS_INFO = [
    {
        "n": 0,
        "titulo": "Sin contratar (general)",
        "descripcion": "Vista global de los proyectos en estado SIN CONTRATAR. Muestra los días promedio "
                       "transcurridos desde la aprobación, sin importar si ya tienen abierto el primer "
                       "proceso precontractual. No tiene semáforo.",
        "estados":   ["SIN CONTRATAR", "(o estado vacío)"],
        "condiciones": [
            "Tiene fecha de aprobación del proyecto",
            "La fecha de aprobación es anterior o igual a la fecha de corte",
            "Aplica con o sin apertura del primer proceso precontractual",
        ],
        "formula":     ("FECHA DE CORTE GESPROY", "FECHA APROBACIÓN PROYECTO", "días"),
        "intervalos":  None,  # ← sin semáforo
    },
    {
        "n": 1,
        "titulo": "Sin contratar sin apertura",
        "descripcion": "Días que un proyecto aprobado lleva sin abrir su primer proceso precontractual.",
        "estados":   ["SIN CONTRATAR", "(o estado vacío)"],
        "condiciones": [
            "Tiene fecha de aprobación del proyecto",
            "<strong>NO</strong> tiene fecha de apertura del primer proceso (si la tiene, pasa a Hito 2)",
            "La fecha de aprobación es anterior o igual a la fecha de corte",
        ],
        "formula":     ("FECHA DE CORTE GESPROY", "FECHA APROBACIÓN PROYECTO", "días"),
        "intervalos":  "hito_1_val",
    },
    {
        "n": 2,
        "titulo": "Sin contratar con apertura",
        "descripcion": "Días desde que se abrió el primer proceso precontractual sin que se haya suscrito contrato.",
        "estados":   ["SIN CONTRATAR", "(o estado vacío)"],
        "condiciones": [
            "Tiene fecha de apertura del primer proceso precontractual",
        ],
        "formula":     ("FECHA DE CORTE GESPROY", "FECHA DE APERTURA DEL PRIMER PROCESO", "días"),
        "intervalos":  "hito_2_val",
    },
    {
        "n": 3,
        "titulo": "Contratado sin acta de inicio",
        "descripcion": "Días desde la suscripción del contrato sin que se firme el acta de inicio.",
        "estados":   ["CONTRATADO SIN ACTA DE INICIO"],
        "condiciones": [
            "Tiene fecha de suscripción del contrato",
        ],
        "formula":     ("FECHA DE CORTE GESPROY", "FECHA SUSCRIPCION", "días"),
        "intervalos":  "hito_3_val",
    },
    {
        "n": 4,
        "titulo": "En ejecución rezagado",
        "descripcion": "Meses que un proyecto en ejecución lleva con su horizonte vencido y sin avance.",
        "estados":   ["CONTRATADO EN EJECUCIÓN"],
        "condiciones": [
            "CPI = 0  y  SPI = 0",
            "El horizonte del proyecto ya está vencido (horizonte ≤ fecha de corte)",
        ],
        "formula":     ("FECHA DE CORTE GESPROY", "HORIZONTE DEL PROYECTO", "meses"),
        "intervalos":  "hito_4_val",
    },
    {
        "n": 5,
        "titulo": "Terminados pendientes de cierre",
        "descripcion": "Días que un proyecto terminado lleva sin pasar formalmente al estado 'Para cierre'.",
        "estados":   ["TERMINADO"],
        "condiciones": [
            "Estado del proyecto = <strong>TERMINADO</strong>",
            "Tiene fecha de finalización registrada",
        ],
        "formula":     ("FECHA DE CORTE GESPROY", "FECHA DE FINALIZACIÓN", "días"),
        "intervalos":  "hito_5_val",
    },
]

# Mapeo del color interno de SEMAFOROS al sufijo CSS (.guia-sem--*)
_GUIA_COLOR_CLS = {"green": "verde", "yellow": "naranja", "orange": "rojo", "black": "negro"}


def render_guia_hitos(incluir_h5: bool, fuente: str):
    """
    Renderiza la pestaña 'Guía de hitos' con cards por cada hito.
      incluir_h5 : si la fuente actual permite calcular Hito 5
      fuente     : nombre del modelo ("Departamento" o "Descentralizadas")
    """
    # Encabezado
    st.markdown('<div class="section-heading">Guía de cálculo de hitos</div>',
                unsafe_allow_html=True)

    # Intro
    h5_disclaimer = (
        ""
        if incluir_h5
        else (" Para esta fuente <strong>Hito 5 no aplica</strong> porque "
              "la tabla no incluye fecha de finalización.")
    )
    st.markdown(f"""
    <div class="guia-intro">
      <div class="guia-intro-title">¿Cómo se evalúan los proyectos?</div>
      Cada proyecto se mide contra <strong>{6 if incluir_h5 else 5} hitos de gestión</strong>
      según el estado en que se encuentra. El <strong>Hito 0</strong> es informativo y
      solo reporta los días promedio para todos los proyectos sin contratar; los demás
      hitos calculan el tiempo transcurrido entre dos fechas clave y lo clasifican en
      un nivel de alerta (verde, naranja, rojo o negro) según el rango en el que caiga.{h5_disclaimer}
      <br><br>
      La <strong>fecha de corte GESPROY</strong> es la referencia temporal: por defecto
      viene del archivo cargado, pero puedes cambiarla a <em>la fecha de hoy</em> desde
      el filtro <strong>Fecha de corte</strong> del panel lateral.
    </div>
    """, unsafe_allow_html=True)

    # Flujo: Estados → Hitos
    flujo = [
        ("Sin contratar",              "Hitos 0, 1 y 2"),
        ("Contratado sin acta",        "Hito 3"),
        ("Contratado en ejecución",    "Hito 4"),
        ("Terminado",                  "Hito 5" if incluir_h5 else "no aplica"),
    ]
    flow_parts = ['<div class="guia-flow">']
    for i, (estado, hitos) in enumerate(flujo):
        flow_parts.append(
            f'<div class="guia-flow-step">'
            f'<div class="guia-flow-state">{estado}</div>'
            f'<div class="guia-flow-hitos">{hitos}</div>'
            f'</div>'
        )
        if i < len(flujo) - 1:
            flow_parts.append('<div class="guia-flow-arrow">›</div>')
    flow_parts.append('</div>')
    st.markdown("".join(flow_parts), unsafe_allow_html=True)

    # Cards de cada hito
    hitos_a_mostrar = HITOS_INFO if incluir_h5 else [h for h in HITOS_INFO if h["n"] != 5]
    for hito in hitos_a_mostrar:
        # Etiquetas de estado
        estados_html = "".join(
            f'<span class="guia-tag">{e}</span>' for e in hito["estados"]
        )
        # Condiciones como lista
        if hito["condiciones"]:
            cond_html = (
                '<ul class="guia-bullets">'
                + "".join(f"<li>{c}</li>" for c in hito["condiciones"])
                + '</ul>'
            )
        else:
            cond_html = '<span style="color:#9CA3AF;font-style:italic">Sin condiciones adicionales.</span>'

        col_a, col_b, unidad = hito["formula"]
        formula_html = (
            '<div class="guia-formula">'
            f'<span class="guia-formula-col">{col_a}</span>'
            '<span class="guia-formula-op">−</span>'
            f'<span class="guia-formula-col">{col_b}</span>'
            '<span class="guia-formula-eq">=</span>'
            f'<span class="guia-formula-result">{unidad}</span>'
            '</div>'
        )

        # Semáforo desde SEMAFOROS — orden de inserción preserva el orden
        # natural verde→negro porque los dicts conservan orden. Si el hito no
        # tiene intervalos (caso de Hito 0, que solo muestra días), omitimos
        # la fila de semáforo.
        sem_block_html = ""
        if hito.get("intervalos"):
            sem_dict = SEMAFOROS.get(hito["intervalos"], {})
            sem_cells = []
            for rango, (color, nivel, mensaje) in sem_dict.items():
                cls = _GUIA_COLOR_CLS.get(color, "verde")
                sem_cells.append(
                    f'<div class="guia-sem guia-sem--{cls}">'
                    f'  <div class="guia-sem-rango">{rango}</div>'
                    f'  <div class="guia-sem-nivel">{nivel}</div>'
                    f'  <div class="guia-sem-mensaje">{mensaje}</div>'
                    f'</div>'
                )
            sem_html = '<div class="guia-semaforo">' + "".join(sem_cells) + '</div>'
            sem_block_html = (
                '<div class="guia-row">'
                '  <div class="guia-row-label">Semáforo</div>'
                f'  <div class="guia-row-value">{sem_html}</div>'
                '</div>'
            )
        else:
            sem_block_html = (
                '<div class="guia-row">'
                '  <div class="guia-row-label">Semáforo</div>'
                '  <div class="guia-row-value" style="font-size:0.8rem;color:#6b7280;font-style:italic">'
                '    Este hito es informativo. Solo se reportan los días transcurridos '
                '    (sin clasificación de alerta).'
                '  </div>'
                '</div>'
            )

        st.markdown(f"""
        <div class="guia-hito">
          <div class="guia-hito-header">
            <div class="guia-hito-num">H{hito["n"]}</div>
            <div>
              <div class="guia-hito-titulo">{hito["titulo"]}</div>
              <div class="guia-hito-subtitulo">{hito["descripcion"]}</div>
            </div>
          </div>
          <div class="guia-hito-body">
            <div class="guia-row">
              <div class="guia-row-label">Estado del proyecto</div>
              <div class="guia-row-value">{estados_html}</div>
            </div>
            <div class="guia-row">
              <div class="guia-row-label">Condiciones</div>
              <div class="guia-row-value">{cond_html}</div>
            </div>
            <div class="guia-row">
              <div class="guia-row-label">Cálculo</div>
              <div class="guia-row-value">{formula_html}</div>
            </div>
            {sem_block_html}
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Nota final
    st.markdown("""
    <div class="guia-nota">
      <strong>Tip:</strong> al pasar el cursor sobre cualquier celda de alerta en las pestañas
      de Resumen o Detalle, se muestra el mensaje específico del hito y nivel.
      En el Detalle por hito, también se puede consultar el comentario de calificación
      del proyecto haciendo hover sobre el estado.
    </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    # ── Selector de vista (controla qué se muestra en el área principal) ─────
    # La "Guía de hitos" es la primera y se vuelve la vista por defecto al abrir
    # la app, para que un usuario nuevo entienda cómo se calcula cada hito antes
    # de explorar los datos.
    st.markdown("<div class='sidebar-section'>Vista</div>", unsafe_allow_html=True)
    vista = st.radio(
        "Vista",
        ["Guía de hitos", "Departamento", "Descentralizadas", "Municipios", "Mapa"],
        label_visibility="collapsed",
        key="vista_principal",
        help=(
            "Guía: introducción al cálculo de los hitos (vista por defecto).\n"
            "Departamento: Matriz de Seguimiento (hitos completos).\n"
            "Descentralizadas: Hitos 1-4 + evaluación.\n"
            "Municipios: solo listado de proyectos.\n"
            "Mapa: visor geográfico de los proyectos por municipio."
        ),
    )

    # ── Selector de fecha de corte para los hitos ───────────────────────────
    # "Del archivo" usa la columna FECHA DE CORTE GESPROY tal cual la trae el
    # Excel. "Hoy" la sobreescribe con la fecha actual de Bogotá, útil para
    # ver el avance en tiempo real sin esperar a un nuevo cargue.
    try:
        from zoneinfo import ZoneInfo
        _hoy_bog = _dt.datetime.now(ZoneInfo("America/Bogota")).date()
    except Exception:
        _hoy_bog = date.today()

    st.markdown("<div class='sidebar-section'>Fecha de corte</div>", unsafe_allow_html=True)
    _opciones_corte = {
        "Del archivo (GESPROY)": None,
        f"Hoy · {_hoy_bog.strftime('%d/%m/%Y')}": _hoy_bog,
    }
    _corte_label = st.radio(
        "Fecha de corte",
        list(_opciones_corte.keys()),
        label_visibility="collapsed",
        key="fecha_corte_modo",
        help=(
            "Selecciona qué fecha se usa como referencia para calcular los hitos:\n"
            "• Del archivo: usa la fecha registrada en GESPROY al momento del cargue.\n"
            "• Hoy: recalcula todos los hitos con la fecha actual de Bogotá."
        ),
    )
    fecha_corte_override = _opciones_corte[_corte_label]

    st.markdown("<div class='sidebar-section'>Datos</div>", unsafe_allow_html=True)

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
    st.markdown("<div class='sidebar-section'>Contratos</div>", unsafe_allow_html=True)
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
# HEADER — se oculta para la vista Mapa (que es full-screen y tiene su propia
# barra superior dentro del componente).
# ─────────────────────────────────────────────────────────────────────────────
if vista != "Mapa":
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
    df = procesar(file_bytes, fecha_corte_override=fecha_corte_override)
    df_descent_hitos = procesar_descentralizadas_hitos(file_bytes,
                                                       fecha_corte_override=fecha_corte_override)
    df_municipios    = procesar_municipios(file_bytes)
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
    "H0 · Sin contratar (general)":       ("hito_0_val", None),
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

# ═════════════════════════════════════════════════════════════════════════════
# VISTA GUÍA DE HITOS — pantalla introductoria (no muestra KPIs ni tabs).
# Se renderiza completa aquí y `st.stop()` evita ejecutar el resto del flujo.
# ═════════════════════════════════════════════════════════════════════════════
if vista == "Guía de hitos":
    render_guia_hitos(incluir_h5=True, fuente="Guía global")
    st.stop()

# ═════════════════════════════════════════════════════════════════════════════
# VISTA MAPA — visor geográfico de proyectos por municipio (tema oscuro).
# Toda la lógica vive en mapa.py para mantener este orquestador limpio.
# ═════════════════════════════════════════════════════════════════════════════
if vista == "Mapa":
    # CSS del modo "full-viewport" inyectado AQUÍ antes de cualquier
    # otra cosa (incluyendo render_mapa). Tres objetivos:
    #   1. ELIMINAR el padding-top que reserva Streamlit para su header
    #      (incluso si ocultamos el header con display:none, el padding
    #      del wrapper sigue ocupando ~80px = la "barra" oscura arriba).
    #   2. NEUTRALIZAR transforms/contain en los ancestros que romperían
    #      position:fixed del iframe (rendering quirk de Streamlit).
    #   3. Colocar el iframe como capa fija a 100vw × 100vh.
    st.markdown("""
    <style>
    /* (1) Fondo oscuro en TODO ancestro + sin overflow ni padding-top */
    html, body { margin:0 !important; padding:0 !important;
                 width:100% !important; height:100% !important;
                 background:#0b1220 !important; overflow:hidden !important; }
    [data-testid="stApp"] {
        background:#0b1220 !important;
        height:100vh !important; max-height:100vh !important;
        margin:0 !important; padding:0 !important;
        overflow:hidden !important;
    }
    [data-testid="stAppViewContainer"] {
        background:#0b1220 !important;
        height:100vh !important; max-height:100vh !important;
        margin:0 !important;
        /* ELIMINA explícitamente el padding-top reservado para el header
           de Streamlit. Sin este reset, queda una franja oscura arriba
           porque el wrapper conserva el espacio del header oculto. */
        padding:0 !important;
        padding-top:0 !important;
        top:0 !important; left:0 !important;
        overflow:hidden !important;
    }
    section.main, .stMain, section[class*="stMain"] {
        background:#0b1220 !important;
        height:100vh !important; max-height:100vh !important;
        margin:0 !important; padding:0 !important;
        padding-top:0 !important;
        top:0 !important;
        overflow:hidden !important;
    }
    /* (2) Bloquear cualquier transform/contain/will-change que rompa
       el contexto de position:fixed del iframe. */
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"],
    section.main, .stMain,
    [data-testid="stAppViewBlockContainer"],
    [data-testid="stMainBlockContainer"],
    .block-container {
        transform:none !important;
        -webkit-transform:none !important;
        will-change:auto !important;
        contain:none !important;
        filter:none !important;
        perspective:none !important;
    }

    /* (3) Header de Streamlit: completamente fuera */
    header[data-testid="stHeader"],
    div[data-testid="stHeader"],
    [data-testid="stAppHeader"],
    header.stAppHeader, .stAppHeader,
    [data-testid="stDecoration"],
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    [data-testid="stDeployButton"],
    [data-testid="manage-app-button"],
    [data-testid="stHeaderActionElements"] {
        display:none !important; height:0 !important;
        min-height:0 !important; max-height:0 !important;
        padding:0 !important; margin:0 !important;
        visibility:hidden !important;
        position:absolute !important; top:-9999px !important;
    }
    /* Toggle del sidebar nativo: visible y por encima del iframe */
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"] {
        display:block !important; visibility:visible !important;
        opacity:1 !important; pointer-events:auto !important;
        z-index:1000002 !important; top:8px !important;
    }
    section[data-testid="stSidebar"] {
        background:#0f172a !important; z-index:1000001 !important;
    }
    /* Block-container y main-block: sin padding, fill vertical */
    section.main > div.block-container,
    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="stMainBlockContainer"],
    .block-container {
        padding:0 !important; margin:0 !important;
        max-width:100% !important; width:100% !important;
        height:100vh !important; max-height:100vh !important;
        overflow:hidden !important;
        background:#0b1220 !important;
    }
    /* IFRAME: position:fixed total = SIEMPRE 100vw × 100vh del viewport */
    div[data-testid="stIFrame"] {
        position:fixed !important;
        top:0 !important; left:0 !important;
        right:0 !important; bottom:0 !important;
        width:100vw !important; height:100vh !important;
        z-index:1 !important;
        margin:0 !important; padding:0 !important;
        overflow:hidden !important; background:#0b1220 !important;
    }
    div[data-testid="stIFrame"] iframe,
    iframe[title^="streamlit_app.components"],
    iframe[title*="components.v1.html"] {
        position:absolute !important;
        top:0 !important; left:0 !important;
        width:100% !important; height:100% !important;
        min-width:100% !important; min-height:100% !important;
        max-width:100% !important; max-height:100% !important;
        border:0 !important; margin:0 !important; padding:0 !important;
        display:block !important; background:#0b1220 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    from mapa import render_mapa
    render_mapa(df_f, df_descent_hitos, df_municipios)
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# KPIs — adaptados a la vista activa
# ─────────────────────────────────────────────────────────────────────────────
# Selección de DataFrame y columna de agrupación según el filtro general.
# Si la tabla de la vista no está disponible (None), caemos a Departamento
# para no romper la pantalla.
if vista == "Descentralizadas" and df_descent_hitos is not None:
    df_kpi          = df_descent_hitos
    col_agrup_kpi   = "EJECUTOR"
    label_agrup_kpi = "Ejecutores"
    sub_agrup_kpi   = "entidades descentralizadas"
elif vista == "Municipios" and df_municipios is not None:
    df_kpi          = df_municipios
    col_agrup_kpi   = "EJECUTOR"
    label_agrup_kpi = "Municipios"
    sub_agrup_kpi   = "ejecutores municipales"
else:
    # Departamento (default)
    df_kpi          = df_f
    col_agrup_kpi   = "ENTIDAD O SECRETARIA"
    label_agrup_kpi = "Entidades"
    sub_agrup_kpi   = "secretarías / dependencias"

# ─────────────────────────────────────────────────────────────────────────────
# Aplicar los filtros del tab "Proyectos" también a las KPIs del header.
# Los widgets se renderizan más abajo dentro del tab, pero como Streamlit
# re-ejecuta TODO el script en cada interacción, sus valores ya están en
# st.session_state desde el rerun anterior (con explicit key=). Los leemos
# aquí para que las tarjetas Total proyectos / Entidades / Proyectos por
# estado reflejen exactamente el mismo subconjunto que se ve en el tab.
# ─────────────────────────────────────────────────────────────────────────────
def _aplicar_filtros_kpi(df_in, vista_actual):
    """Filtra df_kpi según los valores actuales de los filtros del tab
    Proyectos correspondientes a la vista activa. Devuelve df filtrado.
    Si los filtros no existen aún (primer render) no filtra nada."""
    df_out = df_in
    if vista_actual == "Departamento":
        _busq = (st.session_state.get("busq_dpto") or "").strip().lower()
        if _busq and "NOMBRE PROYECTO" in df_out.columns:
            df_out = df_out.filter(
                pl.col("NOMBRE PROYECTO").str.to_lowercase().str.contains(_busq, literal=True)
                | pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(_busq, literal=True)
            )
        _ent = st.session_state.get("ms_ent_dpto") or []
        if _ent and "ENTIDAD O SECRETARIA" in df_out.columns:
            df_out = df_out.filter(pl.col("ENTIDAD O SECRETARIA").is_in(_ent))
        _est = st.session_state.get("ms_est_dpto") or []
        if _est and "ESTADO PROYECTO" in df_out.columns:
            df_out = df_out.filter(pl.col("ESTADO PROYECTO").is_in(_est))
        _cont = st.session_state.get("ms_cont_dpto") or []
        if _cont and "ESTADO CONTRATO" in df_out.columns:
            df_out = df_out.filter(pl.col("ESTADO CONTRATO").is_in(_cont))
        _resp = st.session_state.get("ms_resp_dpto") or []
        if _resp and "RESPONSABLE CARGUE EN GESPROY" in df_out.columns:
            df_out = df_out.filter(pl.col("RESPONSABLE CARGUE EN GESPROY").is_in(_resp))
    elif vista_actual == "Descentralizadas":
        _busq = (st.session_state.get("busq_d") or "").strip().lower()
        if _busq:
            nombre_col = "NOMBRE DEL PROYECTO" if "NOMBRE DEL PROYECTO" in df_out.columns else None
            if nombre_col:
                df_out = df_out.filter(
                    pl.col(nombre_col).str.to_lowercase().str.contains(_busq, literal=True)
                    | pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(_busq, literal=True)
                )
            else:
                df_out = df_out.filter(
                    pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(_busq, literal=True)
                )
        _eje = st.session_state.get("ms_eje_d") or []
        if _eje and "EJECUTOR" in df_out.columns:
            df_out = df_out.filter(pl.col("EJECUTOR").is_in(_eje))
    elif vista_actual == "Municipios":
        _busq = (st.session_state.get("busq_m") or "").strip().lower()
        if _busq:
            nombre_col = "NOMBRE DEL PROYECTO" if "NOMBRE DEL PROYECTO" in df_out.columns else None
            if nombre_col:
                df_out = df_out.filter(
                    pl.col(nombre_col).str.to_lowercase().str.contains(_busq, literal=True)
                    | pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(_busq, literal=True)
                )
            else:
                df_out = df_out.filter(
                    pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(_busq, literal=True)
                )
        _eje = st.session_state.get("ms_eje_m") or []
        if _eje and "EJECUTOR" in df_out.columns:
            df_out = df_out.filter(pl.col("EJECUTOR").is_in(_eje))
    return df_out

# Sustituir df_kpi por la versión filtrada — todos los cálculos posteriores
# (total, entidades, conteo por estado) usan este df filtrado.
df_kpi = _aplicar_filtros_kpi(df_kpi, vista)

total_proy      = df_kpi.height
total_entidades = df_kpi[col_agrup_kpi].n_unique() if col_agrup_kpi in df_kpi.columns else 0
suspendidos     = (int(df_f["Suspendidos"].drop_nulls().sum())
                   if "Suspendidos" in df_f.columns and df_f["Suspendidos"].drop_nulls().len() > 0 else 0)
para_cierre     = (int(df_f["Para cierre"].drop_nulls().sum())
                   if "Para cierre" in df_f.columns and df_f["Para cierre"].drop_nulls().len() > 0 else 0)

if "ESTADO PROYECTO" in df_kpi.columns:
    estados_conteo = (
        df_kpi.group_by("ESTADO PROYECTO")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
    )
else:
    estados_conteo = None

estado_items = ""
if estados_conteo is not None:
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
        <div class="sub">{vista.lower()}</div>
    </div>""", unsafe_allow_html=True)

with kb:
    st.markdown(f"""
    <div class="kpi-main kpi-second">
        <div class="label">{label_agrup_kpi}</div>
        <div class="value">{total_entidades}</div>
        <div class="sub">{sub_agrup_kpi}</div>
    </div>""", unsafe_allow_html=True)

with kd:
    _estado_html = estado_items or (
        "<div style='font-size:0.75rem;color:#9ca3af;font-style:italic'>"
        "Sin datos disponibles.</div>"
    )
    st.markdown(f"""
    <div class="kpi-estados">
        <div class="kpi-estados-title">Proyectos por estado</div>
        <div class="kpi-estados-grid">{_estado_html}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# AGRUPACIÓN
# ─────────────────────────────────────────────────────────────────────────────
agrupacion = (
    df.group_by("ENTIDAD O SECRETARIA")
    .agg(
        pl.col("hito_0_val").mean().round(1).alias("Hito 0 (días)"),
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

# ─────────────────────────────────────────────────────────────────────────────
# EXPORT GLOBAL — siempre disponible en el sidebar, no depende del filtro/vista.
# Incluye Departamento, Descentralizadas y Municipios consolidados.
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div class='sidebar-section'>Exportar</div>", unsafe_allow_html=True)
    st.download_button(
        label="Descargar reporte Excel",
        data=generar_excel(
            df_f=df, df_agr=agrupacion, clasi_por_entidad_map=clasi_por_entidad,
            df_eval_sucre=_df_eval_sucre, cols_eval_sucre=_cols_eval_sucre,
            df_eval_desc=_df_eval_desc,   cols_eval_desc=_cols_eval_desc,
            df_descent_hitos=df_descent_hitos,
            df_municipios=df_municipios,
        ),
        file_name=f"regalias_seguimiento_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        help=("Reporte completo y consolidado: Departamento, Descentralizadas y "
              "Municipios. Independiente de la vista activa."),
    )

# ═════════════════════════════════════════════════════════════════════════════
# ROUTING POR VISTA — el sidebar selecciona qué fuente se muestra en pantalla.
# El exportable es global: siempre incluye Departamento + Descentralizadas +
# Municipios, sin importar la vista activa.
# ═════════════════════════════════════════════════════════════════════════════

# Tabs declarados condicionalmente: cada vista crea sus propios objetos tab.
# Las tabs de Departamento se conservan con los nombres originales para
# minimizar cambios en el código existente.
tab_resumen = tab_proyectos = tab_alertas = tab_evaluacion = None
tab_d_resumen = tab_d_proyectos = tab_d_alertas = tab_d_evaluacion = None
tab_m_proyectos = None

if vista == "Departamento":
    tab_resumen, tab_proyectos, tab_alertas, tab_evaluacion = st.tabs([
        "Resumen por entidad",
        "Todos los proyectos",
        "Reporte semanal de alertas",
        "Evaluación del modelo",
    ])
elif vista == "Descentralizadas":
    tab_d_resumen, tab_d_proyectos, tab_d_alertas, tab_d_evaluacion = st.tabs([
        "Resumen por entidad",
        "Proyectos",
        "Reporte semanal de alertas",
        "Evaluación del modelo",
    ])
elif vista == "Municipios":
    tab_m_proyectos = st.tabs(["Proyectos"])[0]

# ── TAB 1: Tabla resumen ──────────────────────────────────────────────────────
if tab_resumen is not None:
  with tab_resumen:
    def hito_cell(dias_val, clasi_key):
        if dias_val is None or (isinstance(dias_val, float) and dias_val != dias_val):
            return "<td class='null-cell'>—</td>"
        clasi  = _clasificar_promedio(dias_val, clasi_key)
        hito_k = HITO_KEY_MAP.get(clasi_key)
        # H4 se mide en meses (igual que sus intervalos de alerta y el tooltip);
        # el resto de hitos se mide en días.
        if clasi_key == "clasi_4":
            display = f"{dias_val/30.0:.1f} m"
        else:
            display = f"{dias_val:.1f} d"
        return f"<td><span class='dias-val'>{display}</span>{badge_html(clasi, hito_k)}</td>"

    def hito_cell_sin_semaforo(dias_val):
        """Celda solo con días (sin badge), usada por Hito 0 que no tiene semáforo."""
        if dias_val is None or (isinstance(dias_val, float) and dias_val != dias_val):
            return "<td class='null-cell'>—</td>"
        return f"<td><span class='dias-val'>{dias_val:.1f} d</span></td>"

    def _build_row(row):
        e    = html.escape(row["ENTIDAD O SECRETARIA"] or "")
        susp = int(row["Suspendidos"]) if row["Suspendidos"] else 0
        pc   = int(row["Para cierre"]) if row["Para cierre"] else 0
        return f"""<tr>
            <td class="entidad-name">{e}</td>
            {hito_cell_sin_semaforo(row['Hito 0 (días)'])}
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
        {th("Sin contratar<br>(general)", "Hito 0 · Sin contratar (general)",
            "Promedio de días entre la <b>Fecha de aprobación</b> y la <b>Fecha de corte GESPROY</b> para <b>todos los proyectos sin contratar</b> (con o sin apertura del primer proceso).<br><br>Este hito es informativo: no tiene clasificación de semáforo.")}
        {th("Sin contratar<br>sin apertura", "Hito 1 · Sin contratar sin apertura",
            "Promedio de días entre la <b>Fecha de aprobación</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Estado = SIN CONTRATAR y sin fecha de apertura.")}
        {th("Sin contratar<br>con apertura", "Hito 2 · Sin contratar con apertura",
            "Promedio de días entre la <b>Fecha de apertura del primer proceso</b> y la <b>Fecha de corte GESPROY</b>, sin firma del primer contrato.<br><br>Condición: Estado = SIN CONTRATAR con fecha de apertura registrada.")}
        {th("Contratado<br>sin acta de inicio", "Hito 3 · Contratado sin acta de inicio",
            "Promedio de días entre la <b>Fecha de suscripción</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Estado = CONTRATADO SIN ACTA DE INICIO.<br><br>Semáforo: Verde 0–15 d · Naranja 16–30 d · Rojo 31–45 d · Negro &gt;45 d")}
        {th("En ejecución<br>rezagado", "Hito 4 · En ejecución rezagado",
            "Meses entre el <b>Horizonte del proyecto</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Estado = CONTRATADO EN EJECUCIÓN, CPI = 0, SPI = 0 y horizonte vencido.")}
        {th("Proyectos<br>terminados", "Hito 5 · Proyectos terminados",
            "Promedio de días entre la <b>Fecha de finalización</b> y la <b>Fecha de corte GESPROY</b>.<br><br>Condición: Estado = TERMINADO y Fecha de finalización registrada.")}
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
    hito_key_detalle = HITO_KEY_MAP.get(sel_clasi_col_r, None) if sel_clasi_col_r else None
    es_hito_sin_semaforo = sel_clasi_col_r is None

    DATE_COLS_DET = [
        "FECHA APROBACIÓN PROYECTO", "FECHA DE APERTURA DEL PRIMER PROCESO",
        "FECHA SUSCRIPCION", "FECHA ACTA INICIO", "HORIZONTE DEL PROYECTO",
        "FECHA DE FINALIZACIÓN", "FECHA DE CORTE GESPROY",
    ]
    # Incluimos COMENTARIOS CALIFICACIÓN si está presente — se usa como
    # tooltip al pasar el cursor sobre el estado del proyecto.
    _select_cols_det = ["ENTIDAD O SECRETARIA", "BPIN", "NOMBRE PROYECTO",
                         "ESTADO PROYECTO", sel_hito_col_r,
                         *DATE_COLS_DET]
    if sel_clasi_col_r:
        _select_cols_det.insert(5, sel_clasi_col_r)
    if "COMENTARIOS CALIFICACIÓN" in df.columns:
        _select_cols_det.append("COMENTARIOS CALIFICACIÓN")

    df_det = (
        df
        .filter(~pl.col(sel_hito_col_r).is_null())
        .select(_select_cols_det)
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

                    # ── Reclasificación local — usa INTERVALOS directamente.
                    # Para Hito 0 (sin semáforo) no calculamos clasi_v.
                    if es_hito_sin_semaforo:
                        clasi_v = None
                    elif dias_v is not None:
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

                    # ── Estado con tooltip de COMENTARIOS CALIFICACIÓN ──
                    _comentario = (r.get("COMENTARIOS CALIFICACIÓN") or "").strip()
                    if _comentario:
                        _comentario_h = html.escape(_comentario).replace("\n", "<br>")
                        estado_html = (
                            f'<div class="coment-wrap">'
                            f'<span class="estado-tag">{_est_h}</span>'
                            f'<div class="coment-tip-box">'
                            f'<div class="coment-tip-title">Comentario calificación</div>'
                            f'<div class="coment-tip-body">{_comentario_h}</div>'
                            f'</div></div>'
                        )
                    else:
                        estado_html = f'<span class="estado-tag">{_est_h}</span>'

                    if es_hito_sin_semaforo:
                        clasi_cell = "<td style='color:#9ca3af;text-align:center'>—</td>"
                    else:
                        clasi_cell = f"<td>{badge_html(clasi_v, hito_key_detalle)}</td>"

                    det_rows_list.append(f"""<tr class="{row_cls}">
                        <td><span class="bpin-tag">{_bpin_h}</span></td>
                        <td style="font-size:0.81rem">{_nom_h}</td>
                        <td>{estado_html}</td>
                        <td>
                          <div class="dias-tip-wrap">
                            <span class="dias-val-link">{dias_str}</span>
                            {tooltip}
                          </div>
                        </td>
                        {clasi_cell}
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
if tab_proyectos is not None:
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
        # key="busq_dpto" → expone el valor en st.session_state para que las
        # KPIs del header se filtren con el mismo input.
        busqueda = st.text_input("busqueda_proy", placeholder="Buscar por BPIN o nombre…",
                                 label_visibility="collapsed", key="busq_dpto")
    with fc2:
        entidades_proy = sorted(df_f["ENTIDAD O SECRETARIA"].drop_nulls().unique().to_list())
        sel_ent_proy   = st.multiselect("Entidad", entidades_proy,
                                        placeholder="Todas las entidades",
                                        label_visibility="collapsed",
                                        key="ms_ent_dpto")
    with fc3:
        estados_proy_opts = sorted(df_f["ESTADO PROYECTO"].drop_nulls().unique().to_list())
        sel_est_proy      = st.multiselect("Estado proyecto", estados_proy_opts,
                                           placeholder="Todos los estados",
                                           label_visibility="collapsed",
                                           key="ms_est_dpto")
    fc4, fc5 = st.columns([1.4, 1.6])
    with fc4:
        estados_cont_opts = sorted(df_f["ESTADO CONTRATO"].drop_nulls().unique().to_list())
        sel_cont_proy     = st.multiselect("Estado contrato", estados_cont_opts,
                                           placeholder="Todos los contratos",
                                           label_visibility="collapsed",
                                           key="ms_cont_dpto")
    with fc5:
        # Filtro por responsable de cargue en GESPROY (columna nueva del archivo).
        if "RESPONSABLE CARGUE EN GESPROY" in df_f.columns:
            resp_opts = sorted(df_f["RESPONSABLE CARGUE EN GESPROY"].drop_nulls().unique().to_list())
            sel_resp_proy = st.multiselect(
                "Responsable cargue GESPROY", resp_opts,
                placeholder="Todos los responsables",
                label_visibility="collapsed", key="ms_resp_dpto",
            )
        else:
            sel_resp_proy = []

    # Columnas a seleccionar — incluye RESPONSABLE / AVANCE solo si existen
    _proy_cols = [
        "ENTIDAD O SECRETARIA", "BPIN", "NOMBRE PROYECTO",
        "ESTADO PROYECTO", "ESTADO CONTRATO", "CPI", "SPI",
        "FECHA APROBACIÓN PROYECTO", "FECHA DE APERTURA DEL PRIMER PROCESO",
        "FECHA SUSCRIPCION", "FECHA ACTA INICIO",
        "HORIZONTE DEL PROYECTO", "FECHA DE FINALIZACIÓN", "FECHA DE CORTE GESPROY",
        "hito_1_val", "hito_2_val", "hito_3_val", "hito_4_val", "hito_5_val",
        "clasi_1", "clasi_2", "clasi_3", "clasi_4", "clasi_5",
    ]
    for _opt in ("AVANCE FISICO", "AVANCE FINANCIERO", "RESPONSABLE CARGUE EN GESPROY"):
        if _opt in df_f.columns and _opt not in _proy_cols:
            _proy_cols.append(_opt)

    df_proy = df_f.select(_proy_cols)
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
    if sel_resp_proy:
        df_proy = df_proy.filter(pl.col("RESPONSABLE CARGUE EN GESPROY").is_in(sel_resp_proy))
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

# ── TAB 3: Evaluación del modelo (solo Departamento de Sucre) ────────────────
# Nota: la evaluación de Descentralizadas vive en su propia vista; aquí solo
# mostramos los datos de la tabla MatrizSeguimientoEvaluacion (Sucre).
if tab_evaluacion is not None:
  with tab_evaluacion:
    st.markdown("<div class='section-heading'>Evaluación del modelo ejecutor</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.78rem;color:{C['muted']};margin-bottom:0.4rem'>"
        "Calificaciones promedio por entidad / secretaría (Departamento de Sucre).</div>"
        f"<div style='font-size:0.72rem;color:{C['azul_medio']};background:#eff6ff;"
        f"border-left:3px solid {C['azul_medio']};padding:0.45rem 0.7rem;border-radius:4px;"
        "margin-bottom:1rem'>"
        "<strong>Nota:</strong> esta pestaña usa siempre la <b>fecha de corte registrada en "
        "el archivo</b>. El filtro de fecha de corte del panel lateral no aplica aquí.</div>",
        unsafe_allow_html=True,
    )

    # Importante: usamos file_bytes directamente — sin fecha_corte_override —
    # para que la evaluación sea estable y reproducible respecto al archivo.
    df_eval, cols_eval_ok, eval_errores, df_eval_raw = procesar_eval_sucre(file_bytes)
    col_entidad    = "ENTIDAD O SECRETARIA"
    label_entidad  = "Entidad / Secretaría"
    contexto_error = "Departamento de Sucre"
    modelo_sel     = "Departamento de Sucre"

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

# ── TAB Reporte semanal de alertas (Departamento) ────────────────────────────
if tab_alertas is not None:
  with tab_alertas:
    # ── Reporte semanal ───────────────────────────────────────────────────────
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
            # Máxima alerta — H1 y H2 comparten la clave ">180" en conteos_hito,
            # así que el valor ya está combinado: leerlo una sola vez.
            n_negro = conteos_hito.get(">180", 0)
            if n_negro > 0:
                partes.append(
                    f"Se detectaron <strong>{n_negro} proyecto(s) en alerta negra</strong> "
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

# Las pestañas de Exportar y Comunicaciones se eliminaron: el botón de
# exportar está ahora en el sidebar (siempre visible y global), y el módulo
# de Comunicaciones se removió por desuso.

# ─────────────────────────────────────────────────────────────────────────────
# DEAD CODE — bloque histórico que queda después del corte de tabs.
# Mantener `if False:` para preservar ramas no ejecutables sin romper el flujo.
# ─────────────────────────────────────────────────────────────────────────────
if False:
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
                    "Este hito mide los días transcurridos desde la apertura del primer proceso "
                    "precontractual hasta la fecha de corte GESPROY, sin que se haya suscrito "
                    "el contrato.",
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

# ═════════════════════════════════════════════════════════════════════════════
# VISTA DESCENTRALIZADAS — Resumen por entidad (hitos 1-4) + Proyectos + Evaluación
# ═════════════════════════════════════════════════════════════════════════════
if tab_d_resumen is not None and df_descent_hitos is not None:
  with tab_d_resumen:
    st.markdown("<div class='section-heading'>Resumen por ejecutor (Descentralizadas)</div>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.78rem;color:{C['muted']};margin-bottom:1rem'>"
        "Cálculo de hitos 1 a 4 por ejecutor. <strong>Hito 5 no aplica</strong> "
        "porque la tabla de Descentralizadas no contiene fecha de finalización.</div>",
        unsafe_allow_html=True,
    )

    # Agregar promedios por EJECUTOR
    _hito_cols_present = [c for c in ("hito_0_val","hito_1_val","hito_2_val","hito_3_val","hito_4_val")
                          if c in df_descent_hitos.columns]
    _agg_exprs = []
    for hk in _hito_cols_present:
        n = hk.split("_")[1]
        _agg_exprs.append(pl.col(hk).mean().round(1).alias(f"Hito {n} (días)"))
    if "Suspendidos" in df_descent_hitos.columns:
        _agg_exprs.append(pl.col("Suspendidos").sum().alias("Suspendidos"))
    if "Para cierre" in df_descent_hitos.columns:
        _agg_exprs.append(pl.col("Para cierre").sum().alias("Para cierre"))
    _agg_exprs.append(pl.len().alias("Total"))

    agrup_descent = (
        df_descent_hitos.group_by("EJECUTOR")
        .agg(_agg_exprs)
        .sort("EJECUTOR")
    )

    def _hito_cell_d(dias_val, clasi_key):
        if dias_val is None or (isinstance(dias_val, float) and dias_val != dias_val):
            return "<td class='null-cell'>—</td>"
        clasi  = _clasificar_promedio(dias_val, clasi_key)
        hito_k = HITO_KEY_MAP.get(clasi_key)
        if clasi_key == "clasi_4":
            display = f"{dias_val/30.0:.1f} m"
        else:
            display = f"{dias_val:.1f} d"
        return f"<td><span class='dias-val'>{display}</span>{badge_html(clasi, hito_k)}</td>"

    def _hito_cell_d_sin_semaforo(dias_val):
        """Celda solo con días (sin badge) — usada por Hito 0."""
        if dias_val is None or (isinstance(dias_val, float) and dias_val != dias_val):
            return "<td class='null-cell'>—</td>"
        return f"<td><span class='dias-val'>{dias_val:.1f} d</span></td>"

    _has_h0_descent = "hito_0_val" in df_descent_hitos.columns
    rows_html_d = ""
    for row in agrup_descent.to_dicts():
        ent  = html.escape(row.get("EJECUTOR") or "")
        susp = int(row.get("Suspendidos") or 0)
        pc   = int(row.get("Para cierre") or 0)
        cells = ""
        if _has_h0_descent:
            cells += _hito_cell_d_sin_semaforo(row.get("Hito 0 (días)"))
        for n, ck in [("1","clasi_1"),("2","clasi_2"),("3","clasi_3"),("4","clasi_4")]:
            cells += _hito_cell_d(row.get(f"Hito {n} (días)"), ck)
        rows_html_d += (
            f"<tr><td class='entidad-name'>{ent}</td>{cells}"
            f"<td style='text-align:center;font-weight:500'>{susp}</td>"
            f"<td style='text-align:center;font-weight:500'>{pc}</td>"
            f"<td class='col-total'>{int(row['Total'])}</td></tr>"
        )

    _th_h0_descent = (
        th("Sin contratar<br>(general)", "Hito 0 · Sin contratar (general)",
           "Promedio de días entre la <b>Fecha de aprobación</b> y la <b>Fecha de corte GESPROY</b> para "
           "<b>todos los proyectos sin contratar</b> (con o sin apertura).<br><br>Este hito es informativo: "
           "no tiene clasificación de semáforo.")
        if _has_h0_descent else ""
    )

    st.markdown(f"""
    <table class="summary-table">
    <thead><tr>
        <th>Ejecutor</th>
        {_th_h0_descent}
        {th("Sin contratar<br>sin apertura", "Hito 1",
            "Promedio de días entre la <b>Fecha de aprobación</b> y la <b>Fecha de corte GESPROY</b>.")}
        {th("Sin contratar<br>con apertura", "Hito 2",
            "Promedio de días entre la <b>Fecha de apertura del primer proceso</b> y la <b>Fecha de corte GESPROY</b>.")}
        {th("Contratado<br>sin acta de inicio", "Hito 3",
            "Promedio de días entre la <b>Fecha de suscripción</b> y la <b>Fecha de corte GESPROY</b>.")}
        {th("En ejecución<br>rezagado", "Hito 4",
            "Meses entre el <b>Horizonte del proyecto</b> y la <b>Fecha de corte GESPROY</b>.")}
        {th("Suspendidos", "Suspendidos", "Conteo por <b>ESTADO CONTRATO = SUSPENDIDO</b>.")}
        {th("Para cierre", "Para cierre", "Conteo de proyectos con <b>Estado = PARA CIERRE</b>.")}
        <th class="col-total">Total</th>
    </tr></thead>
    <tbody>{rows_html_d}</tbody>
    </table>
    """, unsafe_allow_html=True)

    # ── Detalle por hito (Descentralizadas) ───────────────────────────────────
    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    st.markdown("<div class='section-heading'>Detalle por hito</div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size:0.78rem;color:#6b7280;margin-bottom:0.8rem'>"
        "Selecciona un hito para ver el detalle de los proyectos que lo tienen activo, "
        "ordenados de mayor a menor tiempo.</div>",
        unsafe_allow_html=True,
    )

    HITOS_D_OPTS = {
        "H0 · Sin contratar (general)":       ("hito_0_val", None),
        "H1 · Sin contratar sin apertura":    ("hito_1_val", "clasi_1"),
        "H2 · Sin contratar con apertura":    ("hito_2_val", "clasi_2"),
        "H3 · Contratado sin acta de inicio": ("hito_3_val", "clasi_3"),
        "H4 · En ejecución rezagado":         ("hito_4_val", "clasi_4"),
    }
    # Solo ofrecer hitos que estén calculados en el dataframe
    HITOS_D_OPTS = {k: v for k, v in HITOS_D_OPTS.items() if v[0] in df_descent_hitos.columns}

    if not HITOS_D_OPTS:
        st.info("No hay hitos calculados disponibles para mostrar.")
    else:
        sel_hito_d = st.selectbox(
            "Hito a detallar (Descent.)",
            list(HITOS_D_OPTS.keys()),
            key="sel_hito_resumen_descent",
            label_visibility="collapsed",
        )
        sel_hito_col_d, sel_clasi_col_d = HITOS_D_OPTS[sel_hito_d]
        hito_key_detalle_d = HITO_KEY_MAP.get(sel_clasi_col_d, None) if sel_clasi_col_d else None
        es_hito_sin_semaforo_d = sel_clasi_col_d is None

        DATE_COLS_DET_D = [
            c for c in (
                "FECHA APROBACIÓN PROYECTO", "FECHA DE APERTURA DEL PRIMER PROCESO",
                "FECHA SUSCRIPCION", "FECHA ACTA INICIO",
                "HORIZONTE DEL PROYECTO", "FECHA DE CORTE GESPROY",
            ) if c in df_descent_hitos.columns
        ]
        nombre_col = "NOMBRE DEL PROYECTO" if "NOMBRE DEL PROYECTO" in df_descent_hitos.columns else "EJECUTOR"

        _select_cols_det_d = ["EJECUTOR", "BPIN", nombre_col, "ESTADO PROYECTO",
                              sel_hito_col_d, *DATE_COLS_DET_D]
        if sel_clasi_col_d:
            _select_cols_det_d.insert(5, sel_clasi_col_d)
        if "COMENTARIOS CALIFICACIÓN" in df_descent_hitos.columns:
            _select_cols_det_d.append("COMENTARIOS CALIFICACIÓN")

        df_det_d = (
            df_descent_hitos
            .filter(~pl.col(sel_hito_col_d).is_null())
            .select(_select_cols_det_d)
            .sort(["EJECUTOR", sel_hito_col_d], descending=[False, True])
        )

        if df_det_d.height == 0:
            st.info("No hay proyectos con valor en este hito.")
        else:
            for ejecutor in df_det_d["EJECUTOR"].unique().sort().to_list():
                sub  = df_det_d.filter(pl.col("EJECUTOR") == ejecutor)
                prom = sub[sel_hito_col_d].mean()
                n    = sub.height
                if sel_hito_col_d == "hito_4_val" and prom is not None:
                    prom_str = f"{prom/30.0:.1f} meses"
                else:
                    prom_str = f"{prom:.1f} días" if prom is not None else "—"

                with st.expander(f"{ejecutor}   ·   {n} proyecto(s)   ·   Promedio: {prom_str}", expanded=False):
                    det_rows_d = []
                    for r in sub.to_dicts():
                        dias_v = r[sel_hito_col_d]
                        if dias_v is not None:
                            if sel_hito_col_d == "hito_4_val":
                                dias_str = f"{dias_v/30.0:.1f} m"
                            else:
                                dias_str = f"{dias_v:.1f} d"
                        else:
                            dias_str = "—"

                        if es_hito_sin_semaforo_d:
                            clasi_v = None
                        elif dias_v is not None:
                            if sel_hito_col_d == "hito_4_val":
                                meses = dias_v / 30.0
                                if   meses <= 1: clasi_v = "0-1"
                                elif meses <= 3: clasi_v = "1.1-3"
                                elif meses <= 6: clasi_v = "3.1-6"
                                else:            clasi_v = ">6"
                            else:
                                intervalos = INTERVALOS.get(sel_hito_col_d, [])
                                clasi_v = None
                                for label, lo, hi in intervalos:
                                    if hi is None and dias_v >= lo:               clasi_v = label; break
                                    elif hi is not None and lo <= dias_v <= hi:   clasi_v = label; break
                        else:
                            clasi_v = None

                        badge_cls_str = (
                            _BADGE_BY_HITO.get(sel_hito_col_d, {}).get(str(clasi_v), "badge-yellow")
                            if clasi_v else ""
                        )
                        row_cls = _ROW_CLS_MAP.get(badge_cls_str, "")

                        tooltip  = _dias_tooltip(r, sel_hito_col_d)
                        _bpin_h  = html.escape(str(r['BPIN'] or '—'))
                        _nom_h   = html.escape(r.get(nombre_col) or '—')
                        _est_h   = html.escape(r.get('ESTADO PROYECTO') or '(Sin estado)')

                        # Estado con tooltip de COMENTARIOS CALIFICACIÓN
                        _coment_d = (r.get("COMENTARIOS CALIFICACIÓN") or "").strip()
                        if _coment_d:
                            _coment_h = html.escape(_coment_d).replace("\n", "<br>")
                            estado_d_html = (
                                f'<div class="coment-wrap">'
                                f'<span class="estado-tag">{_est_h}</span>'
                                f'<div class="coment-tip-box">'
                                f'<div class="coment-tip-title">Comentario calificación</div>'
                                f'<div class="coment-tip-body">{_coment_h}</div>'
                                f'</div></div>'
                            )
                        else:
                            estado_d_html = f'<span class="estado-tag">{_est_h}</span>'

                        if es_hito_sin_semaforo_d:
                            clasi_cell_d = "<td style='color:#9ca3af;text-align:center'>—</td>"
                        else:
                            clasi_cell_d = f"<td>{badge_html(clasi_v, hito_key_detalle_d)}</td>"

                        det_rows_d.append(f"""<tr class="{row_cls}">
                            <td><span class="bpin-tag">{_bpin_h}</span></td>
                            <td style="font-size:0.81rem">{_nom_h}</td>
                            <td>{estado_d_html}</td>
                            <td>
                              <div class="dias-tip-wrap">
                                <span class="dias-val-link">{dias_str}</span>
                                {tooltip}
                              </div>
                            </td>
                            {clasi_cell_d}
                        </tr>""")

                    st.markdown(f"""
                    <table class="detail-table">
                    <thead><tr>
                        <th>BPIN</th><th>Nombre del proyecto</th><th>Estado</th>
                        <th>Tiempo <span style="font-size:0.58rem;font-weight:500;opacity:0.7">(pasar el cursor)</span></th>
                        <th>Clasificación</th>
                    </tr></thead>
                    <tbody>{"".join(det_rows_d)}</tbody>
                    </table>""", unsafe_allow_html=True)

elif tab_d_resumen is not None:
  with tab_d_resumen:
    st.warning("No se encontró la tabla **OtrosEjecutoresDescentralizadas** en el archivo, "
               "o no tiene las columnas necesarias para calcular hitos.")

if tab_d_proyectos is not None and df_descent_hitos is not None:
  with tab_d_proyectos:
    st.markdown("<div class='section-heading'>Proyectos · Descentralizadas</div>",
                unsafe_allow_html=True)

    fcd1, fcd2 = st.columns([2, 1.6])
    with fcd1:
        busq_d = st.text_input("busq_descent", placeholder="Buscar por BPIN o nombre…",
                               label_visibility="collapsed", key="busq_d")
    with fcd2:
        ejecutores_d = sorted(df_descent_hitos["EJECUTOR"].drop_nulls().unique().to_list())
        sel_eje_d = st.multiselect("Ejecutor (Descent.)", ejecutores_d,
                                   placeholder="Todos los ejecutores",
                                   label_visibility="collapsed", key="ms_eje_d")

    df_proy_d = df_descent_hitos
    if busq_d:
        term = busq_d.strip().lower()
        if "NOMBRE DEL PROYECTO" in df_proy_d.columns:
            df_proy_d = df_proy_d.filter(
                pl.col("NOMBRE DEL PROYECTO").str.to_lowercase().str.contains(term, literal=True)
                | pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(term, literal=True)
            )
        else:
            df_proy_d = df_proy_d.filter(
                pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(term, literal=True)
            )
    if sel_eje_d:
        df_proy_d = df_proy_d.filter(pl.col("EJECUTOR").is_in(sel_eje_d))

    df_proy_d = df_proy_d.sort(["EJECUTOR", "BPIN"])
    st.markdown(
        f"<div style='font-size:0.73rem;color:{C['muted']};margin:0.4rem 0 0.6rem'>"
        f"<strong style='color:{C['azul_oscuro']}'>{df_proy_d.height}</strong> proyecto(s) encontrado(s)"
        "</div>", unsafe_allow_html=True,
    )

    rows_d_html = []
    for r in df_proy_d.to_dicts():
        eje  = html.escape(r.get("EJECUTOR") or "—")
        bpin = html.escape(str(r.get("BPIN") or "—"))
        nom  = html.escape(r.get("NOMBRE DEL PROYECTO") or "—")
        est  = r.get("ESTADO PROYECTO") or ""
        af   = r.get("AVANCE FÍSICO")
        an   = r.get("AVANCE FINANCIERO")
        def _fmt_pct(v):
            if v is None: return "—"
            try:
                fv = float(v)
                if fv <= 1.0001: fv *= 100
                return f"{fv:.1f}%"
            except Exception:
                return "—"
        rows_d_html.append(f"""
        <tr class="proy-data-row">
            <td class="proy-ent" style="white-space:normal;font-size:0.74rem">{eje}</td>
            <td><span class="bpin-tag">{bpin}</span></td>
            <td class="proy-nombre">{nom}</td>
            <td>{_estado_tooltip_html(est, r)}</td>
            <td style="text-align:center">{_fmt_pct(af)}</td>
            <td style="text-align:center">{_fmt_pct(an)}</td>
        </tr>""")

    st.markdown(f"""
    <table class="proy-table">
    <thead><tr>
        <th style="width:130px">Ejecutor</th>
        <th style="width:110px">BPIN</th>
        <th>Nombre del proyecto</th>
        <th style="width:175px">Estado proyecto</th>
        <th style="width:90px">Avance<br>físico</th>
        <th style="width:90px">Avance<br>financiero</th>
    </tr></thead>
    <tbody>{''.join(rows_d_html) if rows_d_html else
        f'<tr><td colspan="6" style="padding:1rem;text-align:center;color:{C["muted"]};font-style:italic">'
        'Sin proyectos para los filtros activos.</td></tr>'}
    </tbody></table>
    """, unsafe_allow_html=True)

elif tab_d_proyectos is not None:
  with tab_d_proyectos:
    st.warning("No se encontró la tabla **OtrosEjecutoresDescentralizadas**.")

if tab_d_evaluacion is not None:
  with tab_d_evaluacion:
    st.markdown("<div class='section-heading'>Evaluación del modelo ejecutor</div>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.78rem;color:{C['muted']};margin-bottom:0.4rem'>"
        "Calificaciones promedio por ejecutor (Entidades Descentralizadas).</div>"
        f"<div style='font-size:0.72rem;color:{C['azul_medio']};background:#eff6ff;"
        f"border-left:3px solid {C['azul_medio']};padding:0.45rem 0.7rem;border-radius:4px;"
        "margin-bottom:1rem'>"
        "<strong>Nota:</strong> esta pestaña usa siempre la <b>fecha de corte registrada en "
        "el archivo</b>. El filtro de fecha de corte del panel lateral no aplica aquí.</div>",
        unsafe_allow_html=True,
    )

    # Importante: pasamos file_bytes directamente — sin fecha_corte_override —
    # para que la evaluación se mantenga estable frente al archivo y no cambie
    # cuando el usuario alterne el filtro general.
    df_eval_d, cols_eval_ok_d, eval_errores_d, df_eval_raw_d = procesar_descentralizadas(file_bytes)

    if eval_errores_d:
        _render_eval_errors(eval_errores_d, "Descentralizadas")

    if df_eval_d is None or df_eval_d.height == 0:
        st.info("No se encontraron datos de evaluación para Descentralizadas.")
    else:
        col_entidad_d   = "EJECUTOR"
        label_entidad_d = "Ejecutor"
        max_score_d     = 100.0

        tabs_eval_d = st.tabs([
            "Desempeño en contratación",
            "Información a tiempo",
            "Ejecución del proyecto",
            "Calidad de la información",
        ])

        for i, (col_cal, label_cal) in enumerate(zip(COLS_EVAL, COLS_EVAL_LABELS)):
            with tabs_eval_d[i]:
                if col_cal not in cols_eval_ok_d:
                    st.info(f"No hay datos disponibles para «{label_cal}» debido a errores en el archivo.")
                    continue

                filas_d = []
                for row in df_eval_d.sort(col_cal, descending=True, nulls_last=True).to_dicts():
                    nombre = row.get(col_entidad_d) or "Sin nombre"
                    score  = row.get(col_cal)

                    comentario_html = "—"
                    if df_eval_raw_d is not None and col_cal in df_eval_raw_d.columns:
                        sub         = df_eval_raw_d.filter(pl.col(col_entidad_d) == nombre)
                        n_total     = sub.height
                        n_con_cal   = int(sub[col_cal].drop_nulls().len())
                        n_no_aplica = n_total - n_con_cal
                        n_cero      = int((sub[col_cal] == 0).sum())   if n_con_cal > 0 else 0
                        n_max       = int((sub[col_cal] == 100).sum()) if n_con_cal > 0 else 0
                        vals_ok     = sub[col_cal].drop_nulls()
                        v_min       = float(vals_ok.min()) if n_con_cal > 0 else None
                        v_max_v     = float(vals_ok.max()) if n_con_cal > 0 else None

                        def _bpin_proy_d(val_filtro):
                            f = sub.filter(pl.col(col_cal) == val_filtro)
                            if f.height == 0: return None
                            bp = (f.to_dicts()[0].get("BPIN") or "").strip()
                            return bp if bp else None

                        proy_bajo = _bpin_proy_d(v_min)   if v_min  is not None and v_min  < 60  else None
                        proy_alto = _bpin_proy_d(v_max_v) if v_max_v is not None and v_max_v >= 80 else None

                        partes = []
                        if score is None:
                            partes.append(
                                f"Ninguno de los <strong>{n_total} proyecto(s)</strong> de este ejecutor "
                                f"aplica para este criterio."
                            )
                            comentario_html = " ".join(partes)
                            filas_d.append(f"""<tr>
                                <td class="entidad-name">{html.escape(nombre)}</td>
                                <td style="color:{C['muted']}">—</td>
                                <td class="eval-comment eval-no-aplica">{comentario_html}</td>
                            </tr>""")
                            continue

                        if n_no_aplica == 0:
                            partes.append(
                                f"Calificación calculada sobre los "
                                f"<strong>{n_con_cal} {'proyecto' if n_con_cal == 1 else 'proyectos'}</strong> "
                                f"del ejecutor que aplican para este criterio."
                            )
                        else:
                            partes.append(
                                f"Calificación calculada sobre "
                                f"<strong>{n_con_cal} de {n_total} proyectos</strong>. "
                                f"Los {n_no_aplica} restantes son <em>no aplicables</em>."
                            )

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
                                    f"{v_min:.0f} puntos y el más alto {v_max_v:.0f}."
                                )
                            else:
                                partes.append(
                                    f"Los proyectos obtuvieron resultados entre "
                                    f"{v_min:.0f} y {v_max_v:.0f} puntos."
                                )

                        if n_cero == 1:
                            extra = f" (BPIN {html.escape(proy_bajo)})" if proy_bajo and v_min == 0 else ""
                            partes.append(
                                f"Un proyecto{extra} obtuvo cero puntos, lo que reduce el promedio."
                            )
                        elif n_cero > 1:
                            partes.append(
                                f"{n_cero} proyectos obtuvieron cero puntos, lo que arrastra el promedio."
                            )
                        elif proy_bajo:
                            partes.append(
                                f"El proyecto con menor resultado es el BPIN {html.escape(proy_bajo)} "
                                f"con {v_min:.0f} puntos."
                            )

                        if n_max == 1 and n_con_cal > 1:
                            extra = f" (BPIN {html.escape(proy_alto)})" if proy_alto else ""
                            partes.append(f"Por otro lado, un proyecto{extra} alcanzó 100 puntos.")
                        elif n_max > 1:
                            partes.append(f"Por otro lado, {n_max} proyectos alcanzaron 100 puntos.")
                        elif proy_alto and n_max == 0 and n_con_cal > 1:
                            partes.append(
                                f"El proyecto con mejor desempeño es el BPIN "
                                f"{html.escape(proy_alto)} con {v_max_v:.0f} puntos."
                            )
                        comentario_html = " ".join(partes) if partes else "—"

                    color_bar, _nivel = eval_color(score, max_score_d)
                    bg_map = {
                        C["verde_medio"]: "#d1fae5",
                        C["cian"]:        "#e0f7fa",
                        C["naranja"]:     "#fff7ed",
                        C["salmon"]:      "#fee2e2",
                    }
                    bg_pill = bg_map.get(color_bar, "#f1f5f9")
                    filas_d.append(f"""<tr>
                        <td class="entidad-name">{html.escape(nombre)}</td>
                        <td style="white-space:nowrap">
                            <span class="eval-score-pill" style="background:{bg_pill};color:{color_bar}">
                                {score:.2f}
                            </span>
                        </td>
                        <td class="eval-comment">{comentario_html}</td>
                    </tr>""")

                if not filas_d:
                    st.info("No hay registros con calificación para este criterio.")
                else:
                    st.markdown(f"""
                    <table class="eval-table">
                    <thead><tr>
                        <th style="width:22%">{label_entidad_d}</th>
                        <th style="width:14%">Calificación promedio &nbsp;(escala 0–{max_score_d:.0f})</th>
                        <th>Comentario</th>
                    </tr></thead>
                    <tbody>{"".join(filas_d)}</tbody>
                    </table>
                    """, unsafe_allow_html=True)

# ── TAB Reporte semanal de alertas (Descentralizadas) ────────────────────────
if tab_d_alertas is not None and df_descent_hitos is not None:
  with tab_d_alertas:
    st.markdown("<div class='section-heading'>Reporte semanal de alertas</div>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.78rem;color:{C['muted']};margin-bottom:1rem'>"
        "Conteo de proyectos con semáforo <strong>naranja, rojo o negro</strong> por ejecutor "
        "y estado, basado en los hitos 1-4 de Descentralizadas.</div>",
        unsafe_allow_html=True,
    )

    ALERTAS_NRN_D = {
        "hito_1_val": ["101-150", "151-180", ">180"],
        "hito_2_val": ["101-150", "151-180", ">180"],
        "hito_3_val": ["16-30", "31-45", ">45"],
        "hito_4_val": ["1.1-3", "3.1-6", ">6"],
    }
    ALERTA_COLOR_D = {
        "101-150": (C["naranja"], "#fff7ed"), "31-45":   (C["naranja"], "#fff7ed"),
        "1.1-3":   (C["naranja"], "#fff7ed"), "16-30":   (C["naranja"], "#fff7ed"),
        "151-180": (C["naranja_osc"], "#ffedd5"), "46-60": (C["naranja_osc"], "#ffedd5"),
        "3.1-6":   (C["naranja_osc"], "#ffedd5"),
        ">180":    (C["text"], "#e2e8f0"), ">60": (C["text"], "#e2e8f0"),
        ">6":      (C["text"], "#e2e8f0"), ">45": (C["text"], "#e2e8f0"),
    }
    def _pill_alerta_d(clasi):
        fg, bg = ALERTA_COLOR_D.get(clasi, (C["muted"], "#f1f5f9"))
        return (
            f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'border:1px solid {fg}40;border-radius:12px;padding:1px 7px;'
            f'font-size:0.63rem;font-weight:700;margin:1px 2px;white-space:nowrap">'
            f'{clasi}</span>'
        )

    def _comentario_reporte_d(estado_up, conteos_hito, n_total_estado):
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
            n_negro = conteos_hito.get(">180", 0)
            if n_negro > 0:
                partes.append(
                    f"<strong>{n_negro} proyecto(s) en alerta negra</strong> "
                    f"(más de 180 días sin avance)."
                )
        elif estado_up == "CONTRATADO SIN ACTA DE INICIO":
            n_negro = conteos_hito.get(">45", 0)
            if n_negro:
                partes.append(f"<strong>{n_negro}</strong> superan los 45 días sin acta de inicio.")
        elif estado_up == "CONTRATADO EN EJECUCIÓN":
            n_negro = conteos_hito.get(">6", 0)
            if n_negro:
                partes.append(
                    f"<strong>{n_negro}</strong> con más de 6 meses de horizonte vencido."
                )
        return " ".join(partes)

    REPORTE_CONFIG_D = [
        {"estado": "SIN CONTRATAR", "label": "Sin contratar",
         "hitos": [("clasi_1", "hito_1_val"), ("clasi_2", "hito_2_val")],
         "color_est": (C["cian"], "#e0f7fa")},
        {"estado": "CONTRATADO SIN ACTA DE INICIO", "label": "Contratado sin acta de inicio",
         "hitos": [("clasi_3", "hito_3_val")],
         "color_est": (C["azul_medio"], "#dbeafe")},
        {"estado": "CONTRATADO EN EJECUCIÓN", "label": "Contratado en ejecución",
         "hitos": [("clasi_4", "hito_4_val")],
         "color_est": (C["verde_medio"], "#d1fae5")},
    ]

    ejecutores_rep = sorted(df_descent_hitos["EJECUTOR"].drop_nulls().unique().to_list())
    reporte_rows_d = []
    for cfg in REPORTE_CONFIG_D:
        estado_up = cfg["estado"]
        df_estado = df_descent_hitos.filter(pl.col("ESTADO PROYECTO") == estado_up)
        n_total_est = df_estado.height
        if n_total_est == 0:
            continue

        conteos_global: dict = {}
        for clasi_col, hito_col in cfg["hitos"]:
            if clasi_col not in df_descent_hitos.columns:
                continue
            for alerta in ALERTAS_NRN_D.get(hito_col, []):
                n = int(df_estado.filter(pl.col(clasi_col) == alerta).height)
                if n > 0:
                    conteos_global[alerta] = conteos_global.get(alerta, 0) + n
        n_total_alerta = sum(conteos_global.values())

        filas_eje = []
        for eje in ejecutores_rep:
            df_eje = df_estado.filter(pl.col("EJECUTOR") == eje)
            if df_eje.height == 0:
                continue
            conteos_eje: dict = {}
            for clasi_col, hito_col in cfg["hitos"]:
                if clasi_col not in df_descent_hitos.columns:
                    continue
                for alerta in ALERTAS_NRN_D.get(hito_col, []):
                    n = int(df_eje.filter(pl.col(clasi_col) == alerta).height)
                    if n > 0:
                        conteos_eje[alerta] = conteos_eje.get(alerta, 0) + n
            n_eje_alerta = sum(conteos_eje.values())
            if n_eje_alerta == 0:
                continue
            pills = "".join(_pill_alerta_d(k) for k in sorted(conteos_eje, key=lambda x: conteos_eje[x], reverse=True))
            filas_eje.append((eje, df_eje.height, n_eje_alerta, pills, conteos_eje))

        if not filas_eje:
            continue

        fg_est, bg_est = cfg["color_est"]
        reporte_rows_d.append(
            f'<tr style="background:{bg_est}20">'
            f'<td colspan="4" style="padding:0.55rem 0.9rem;border-bottom:2px solid {fg_est}30">'
            f'<span style="font-family:\'Montserrat\',sans-serif;font-size:0.67rem;font-weight:800;'
            f'text-transform:uppercase;letter-spacing:0.8px;color:{fg_est}">'
            f'{cfg["label"]}</span>'
            f'<span style="font-size:0.7rem;color:{C["muted"]};font-weight:400;margin-left:0.6rem">'
            f'{n_total_est} proyecto(s) en este estado · {n_total_alerta} con alerta</span>'
            f'</td></tr>'
        )
        for eje, n_eje_total, n_eje_alerta, pills_html, conteos_eje in filas_eje:
            com_eje = _comentario_reporte_d(estado_up, conteos_eje, n_eje_alerta)
            reporte_rows_d.append(f"""<tr>
                <td style="font-weight:600;font-size:0.81rem;color:{C['azul_oscuro']};
                    padding:0.65rem 0.9rem;vertical-align:top">{html.escape(eje)}</td>
                <td style="padding:0.65rem 0.9rem;vertical-align:top">
                    <span style="display:inline-block;background:{bg_est};color:{fg_est};
                        border:1px solid {fg_est}40;border-radius:12px;padding:2px 9px;
                        font-size:0.65rem;font-weight:700;white-space:nowrap">
                        {html.escape(cfg['label'])}
                    </span>
                </td>
                <td style="padding:0.65rem 0.9rem;vertical-align:top;text-align:center">
                    <div style="font-family:'DM Mono',monospace;font-size:1.1rem;font-weight:800;
                        color:{C['azul_oscuro']};line-height:1">{n_eje_alerta}</div>
                    <div style="font-size:0.62rem;color:{C['muted']};margin-top:2px">de {n_eje_total}</div>
                    <div style="margin-top:4px">{pills_html}</div>
                </td>
                <td style="padding:0.65rem 0.9rem;vertical-align:top;
                    font-size:0.75rem;color:{C['text']};line-height:1.6">{com_eje}</td>
            </tr>""")

    _color_muted_d = C["muted"]
    st.markdown(f"""
    <table class="reporte-table">
    <thead><tr>
        <th style="width:22%">Ejecutor</th>
        <th style="width:24%">Estado del proyecto</th>
        <th style="width:15%">N.° proyectos<br>con alerta</th>
        <th>Comentario</th>
    </tr></thead>
    <tbody>{"".join(reporte_rows_d) if reporte_rows_d else
        f'<tr><td colspan="4" style="padding:1.2rem;color:{_color_muted_d};font-style:italic;text-align:center">'
        f'No se encontraron proyectos con alertas naranja, roja o negra.</td></tr>'
    }
    </tbody></table>
    """, unsafe_allow_html=True)

elif tab_d_alertas is not None:
  with tab_d_alertas:
    st.warning("No se encontró la tabla **OtrosEjecutoresDescentralizadas**.")


# ═════════════════════════════════════════════════════════════════════════════
# VISTA MUNICIPIOS — solo Proyectos (sin hitos, sin contratos, sin evaluación)
# ═════════════════════════════════════════════════════════════════════════════
if tab_m_proyectos is not None and df_municipios is not None:
  with tab_m_proyectos:
    st.markdown("<div class='section-heading'>Proyectos · Municipios</div>",
                unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.78rem;color:{C['muted']};margin-bottom:1rem'>"
        "Listado de proyectos por municipio. Esta tabla no contiene fechas de hitos "
        "ni datos de contratos: por eso no se calculan alertas ni evaluación.</div>",
        unsafe_allow_html=True,
    )

    fmc1, fmc2 = st.columns([2, 1.6])
    with fmc1:
        busq_m = st.text_input("busq_munic", placeholder="Buscar por BPIN o nombre…",
                               label_visibility="collapsed", key="busq_m")
    with fmc2:
        ejecutores_m = sorted(df_municipios["EJECUTOR"].drop_nulls().unique().to_list())
        sel_eje_m = st.multiselect("Municipio", ejecutores_m,
                                   placeholder="Todos los municipios",
                                   label_visibility="collapsed", key="ms_eje_m")

    df_proy_m = df_municipios
    if busq_m:
        term = busq_m.strip().lower()
        if "NOMBRE DEL PROYECTO" in df_proy_m.columns:
            df_proy_m = df_proy_m.filter(
                pl.col("NOMBRE DEL PROYECTO").str.to_lowercase().str.contains(term, literal=True)
                | pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(term, literal=True)
            )
        else:
            df_proy_m = df_proy_m.filter(
                pl.col("BPIN").cast(pl.Utf8).str.to_lowercase().str.contains(term, literal=True)
            )
    if sel_eje_m:
        df_proy_m = df_proy_m.filter(pl.col("EJECUTOR").is_in(sel_eje_m))

    df_proy_m = df_proy_m.sort(["EJECUTOR", "BPIN"])
    st.markdown(
        f"<div style='font-size:0.73rem;color:{C['muted']};margin:0.4rem 0 0.6rem'>"
        f"<strong style='color:{C['azul_oscuro']}'>{df_proy_m.height}</strong> proyecto(s) encontrado(s)"
        "</div>", unsafe_allow_html=True,
    )

    rows_m_html = []
    for r in df_proy_m.to_dicts():
        eje    = html.escape(r.get("EJECUTOR") or "—")
        bpin   = html.escape(str(r.get("BPIN") or "—"))
        nom    = html.escape(r.get("NOMBRE DEL PROYECTO") or "—")
        sector = html.escape(r.get("SECTOR") or "—")
        est    = html.escape(r.get("ESTADO PROYECTO") or "")
        af     = r.get("AVANCE FÍSICO")
        an     = r.get("AVANCE FINANCIERO")
        def _fmt_pct(v):
            if v is None: return "—"
            try:
                fv = float(v)
                if fv <= 1.0001: fv *= 100
                return f"{fv:.1f}%"
            except Exception:
                return "—"

        # Estado con tooltip de COMENTARIOS CALIFICACIÓN (si el proyecto
        # tiene comentario registrado).
        _coment_m = (r.get("COMENTARIOS CALIFICACIÓN") or "").strip()
        if _coment_m:
            _coment_h = html.escape(_coment_m).replace("\n", "<br>")
            estado_m_html = (
                f'<div class="coment-wrap">'
                f'<span class="estado-tag">{est or "—"}</span>'
                f'<div class="coment-tip-box">'
                f'<div class="coment-tip-title">Comentario calificación</div>'
                f'<div class="coment-tip-body">{_coment_h}</div>'
                f'</div></div>'
            )
        else:
            estado_m_html = f'<span class="estado-tag">{est or "—"}</span>'

        rows_m_html.append(f"""
        <tr class="proy-data-row">
            <td class="proy-ent" style="white-space:normal;font-size:0.74rem">{eje}</td>
            <td><span class="bpin-tag">{bpin}</span></td>
            <td class="proy-nombre">{nom}</td>
            <td style="font-size:0.74rem;color:{C['muted']};white-space:normal">{sector}</td>
            <td>{estado_m_html}</td>
            <td style="text-align:center">{_fmt_pct(af)}</td>
            <td style="text-align:center">{_fmt_pct(an)}</td>
        </tr>""")

    st.markdown(f"""
    <table class="proy-table">
    <thead><tr>
        <th style="width:130px">Ejecutor</th>
        <th style="width:100px">BPIN</th>
        <th>Nombre del proyecto</th>
        <th style="width:130px">Sector</th>
        <th style="width:140px">Estado proyecto</th>
        <th style="width:80px">Avance<br>físico</th>
        <th style="width:80px">Avance<br>financiero</th>
    </tr></thead>
    <tbody>{''.join(rows_m_html) if rows_m_html else
        f'<tr><td colspan="7" style="padding:1rem;text-align:center;color:{C["muted"]};font-style:italic">'
        'Sin proyectos para los filtros activos.</td></tr>'}
    </tbody></table>
    """, unsafe_allow_html=True)

elif tab_m_proyectos is not None:
  with tab_m_proyectos:
    st.warning("No se encontró la tabla **OtrosEjecutoresMunicipios** en el archivo.")
