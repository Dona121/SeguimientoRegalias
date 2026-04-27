"""
constants.py
Configuración de página, paleta de colores, inyección de CSS global,
constantes de negocio (INTERVALOS, SEMAFOROS, COLS_EVAL, COLUMNAS_ESPERADAS).
"""
import streamlit as st
import polars as pl
import pandas as pd
import io
import html
import json
import logging
import urllib.parse
import urllib.request
import streamlit.components.v1 as components
import datetime as _dt
from datetime import date
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter

_log = logging.getLogger(__name__)


st.set_page_config(
    page_title="Seguimiento Regalías",
    layout="wide",
    initial_sidebar_state="expanded",
)

C = {
    "azul_oscuro":  "#003d6c",
    "azul_medio":   "#1754ab",
    "verde_oscuro": "#005931",
    "verde_medio":  "#17743d",
    "cian":         "#47b1d5",
    "naranja":      "#d88c16",
    "naranja_osc":  "#cf7000",
    "cafe":         "#9b5b1e",
    "salmon":       "#e68878",
    "bg":           "#e8edf5",
    "white":        "#ffffff",
    "text":         "#1a2332",
    "muted":        "#6b7280",
    "border":       "#e2e8f0",
}


def inject_css():
    """Inyecta CSS global y JS de tooltips. Llamar desde app.py después de set_page_config."""
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Montserrat', sans-serif;
        color: {C['text']};
    }}

    /* ── Fondo del área principal con gradiente institucional ── */
    .stApp {{
        background:
            radial-gradient(ellipse at 0% 0%, rgba(0,61,108,0.10) 0%, transparent 55%),
            radial-gradient(ellipse at 100% 100%, rgba(0,89,49,0.08) 0%, transparent 55%),
            linear-gradient(160deg, #dde5f0 0%, #e8edf5 40%, #eaf0f0 100%);
        min-height: 100vh;
    }}

    /* Controlar padding del contenedor principal de Streamlit */
    .block-container {{
        padding-top: 3.5rem !important;
        padding-left: 2.5rem !important;
        padding-right: 2.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 1400px !important;
    }}

    /* ── Sidebar oscuro ── */
    section[data-testid="stSidebar"] > div {{
        background: #001f3f;
        padding-top: 1.5rem;
    }}
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span:not([data-baseweb="tag"] span),
    section[data-testid="stSidebar"] div {{
        color: rgba(255,255,255,0.95) !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] section {{
        background: rgba(255,255,255,0.08) !important;
        border: 1.5px dashed rgba(255,255,255,0.25) !important;
        border-radius: 8px !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] section *{{
        color: rgba(255,255,255,0.85) !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] button {{
        background: rgba(255,255,255,0.12) !important;
        color: white !important;
        border: 1px solid rgba(255,255,255,0.3) !important;
        border-radius: 6px !important;
    }}
    span[data-baseweb="tag"] {{
        background: {C['azul_medio']} !important;
        color: white !important;
        max-width: 160px !important;
        border-radius: 4px !important;
    }}
    span[data-baseweb="tag"] span {{
        color: white !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        overflow: hidden !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        max-width: 130px !important;
        display: block !important;
    }}
    section[data-testid="stSidebar"] [data-baseweb="select"] > div:first-child {{
        flex-wrap: wrap !important;
        gap: 4px !important;
        padding: 6px 8px !important;
        background: rgba(255,255,255,0.07) !important;
        border-color: rgba(255,255,255,0.18) !important;
        border-radius: 6px !important;
    }}
    section[data-testid="stSidebar"] [data-baseweb="select"] [class*="singleValue"],
    section[data-testid="stSidebar"] [data-baseweb="select"] [class*="placeholder"] {{
        color: white !important;
        font-weight: 500 !important;
    }}
    section[data-testid="stSidebar"] .stMultiSelect label,
    section[data-testid="stSidebar"] .stSelectbox label {{
        color: rgba(255,255,255,0.6) !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
        margin-bottom: 0.2rem !important;
    }}
    .sidebar-section {{
        font-family: 'Montserrat', sans-serif;
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: {C['cian']} !important;
        margin: 1.5rem 0 0.7rem 0;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid rgba(71,177,213,0.3);
    }}

    /* ── Botón de recarga en sidebar ──
       Usamos múltiples selectores en cascada porque la estructura DOM del
       <button> de Streamlit varía entre versiones: a veces vive dentro de
       .stButton, otras dentro de [data-testid="stButton"], y siempre tiene
       un atributo `kind`. El selector button[kind] es el más confiable.
       Limitamos al sidebar con section[data-testid="stSidebar"] para no
       afectar otros botones de la app (como el de descarga de Excel). */
    section[data-testid="stSidebar"] button[kind],
    section[data-testid="stSidebar"] [data-testid="stButton"] button,
    section[data-testid="stSidebar"] .stButton button {{
        background: rgba(71,177,213,0.12) !important;
        color: {C['cian']} !important;
        border: 1.5px solid rgba(71,177,213,0.35) !important;
        border-radius: 8px !important;
        font-family: 'Montserrat', sans-serif !important;
        font-size: 0.74rem !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        box-shadow: none !important;
        transition: background 0.15s, border-color 0.15s, color 0.15s !important;
    }}
    /* Texto interno: Streamlit envuelve el label en <p>/<div> que heredan
       el color blanco global del sidebar. Forzamos el cian. */
    section[data-testid="stSidebar"] button[kind] *,
    section[data-testid="stSidebar"] [data-testid="stButton"] button *,
    section[data-testid="stSidebar"] .stButton button * {{
        color: {C['cian']} !important;
    }}
    /* Hover: intensificar fondo y pasar texto a blanco */
    section[data-testid="stSidebar"] button[kind]:hover,
    section[data-testid="stSidebar"] [data-testid="stButton"] button:hover,
    section[data-testid="stSidebar"] .stButton button:hover {{
        background: rgba(71,177,213,0.25) !important;
        border-color: {C['cian']} !important;
        color: #ffffff !important;
    }}
    section[data-testid="stSidebar"] button[kind]:hover *,
    section[data-testid="stSidebar"] [data-testid="stButton"] button:hover *,
    section[data-testid="stSidebar"] .stButton button:hover * {{
        color: #ffffff !important;
    }}
    /* Active y focus: tono más intenso, texto blanco */
    section[data-testid="stSidebar"] button[kind]:active,
    section[data-testid="stSidebar"] button[kind]:focus,
    section[data-testid="stSidebar"] button[kind]:focus-visible,
    section[data-testid="stSidebar"] [data-testid="stButton"] button:active,
    section[data-testid="stSidebar"] [data-testid="stButton"] button:focus {{
        background: rgba(71,177,213,0.35) !important;
        border-color: {C['cian']} !important;
        color: #ffffff !important;
        outline: none !important;
        box-shadow: 0 0 0 2px rgba(71,177,213,0.25) !important;
    }}
    section[data-testid="stSidebar"] button[kind]:active *,
    section[data-testid="stSidebar"] button[kind]:focus *,
    section[data-testid="stSidebar"] [data-testid="stButton"] button:active *,
    section[data-testid="stSidebar"] [data-testid="stButton"] button:focus * {{
        color: #ffffff !important;
    }}

    /* ── Header ── */
    .page-header {{
        background: linear-gradient(120deg, {C['azul_oscuro']} 0%, {C['verde_oscuro']} 100%);
        border-radius: 12px;
        margin: 0 0 0.8rem 0;
        padding: 1.8rem 2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 4px 24px rgba(0,61,108,0.22);
        position: relative;
        z-index: 1;
    }}
    .page-header h1 {{
        font-family: 'Montserrat', sans-serif;
        font-size: 1.6rem;
        font-weight: 800;
        color: white;
        margin: 0 0 0.15rem 0;
    }}
    .page-header p {{
        color: rgba(255,255,255,0.6);
        margin: 0;
        font-size: 0.82rem;
        font-weight: 400;
    }}

    /* ── Filtros horizontales ── */
    .filter-bar {{
        background: {C['white']};
        border-radius: 10px;
        padding: 0.85rem 1.2rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        display: flex;
        align-items: center;
        gap: 1rem;
        flex-wrap: wrap;
    }}
    .filter-label {{
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: {C['muted']};
        white-space: nowrap;
    }}

    /* ── KPI principal ── */
    .kpi-main {{
        background: {C['azul_oscuro']};
        border-radius: 12px;
        padding: 1.4rem 1.6rem;
        color: white;
        height: 100%;
        box-shadow: 0 4px 20px rgba(0,61,108,0.22), 0 1px 4px rgba(0,0,0,0.1);
    }}
    .kpi-main .label {{
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: rgba(255,255,255,0.6);
        margin-bottom: 0.4rem;
    }}
    .kpi-main .value {{
        font-family: 'Montserrat', sans-serif;
        font-size: 2.8rem;
        font-weight: 800;
        line-height: 1;
        color: white;
    }}
    .kpi-main .sub {{
        font-size: 0.78rem;
        color: rgba(255,255,255,0.5);
        margin-top: 0.2rem;
    }}

    /* ── KPI secundario ── */
    .kpi-sec {{
        background: #ffffff;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        border-left: 4px solid;
        box-shadow: 0 3px 16px rgba(0,40,90,0.13), 0 1px 3px rgba(0,0,0,0.07);
        height: 100%;
    }}
    .kpi-sec .label {{
        font-size: 0.63rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: {C['muted']};
        margin-bottom: 0.3rem;
    }}
    .kpi-sec .value {{
        font-family: 'Montserrat', sans-serif;
        font-size: 1.6rem;
        font-weight: 800;
        line-height: 1;
    }}
    .kpi-sec .sub {{
        font-size: 0.7rem;
        color: {C['muted']};
        margin-top: 0.15rem;
    }}
    .kpi-stack {{
        display: flex;
        flex-direction: column;
        height: 100%;
        gap: 0;
    }}
    .kpi-stack .kpi-sec {{
        flex: 1;
        height: auto;
        padding: 0.7rem 1.2rem;
    }}
    .kpi-estados {{
        background: #ffffff;
        border-radius: 10px;
        padding: 0.85rem 1.1rem;
        box-shadow: 0 3px 16px rgba(0,40,90,0.13), 0 1px 3px rgba(0,0,0,0.07);
        height: 100%;
    }}
    .kpi-estados-title {{
        font-size: 0.63rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: {C['muted']};
        margin-bottom: 0.55rem;
    }}
    .kpi-estados-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0 1.2rem;
    }}
    .estado-kpi-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.28rem 0;
        border-bottom: 1px solid {C['border']};
        font-size: 0.78rem;
    }}
    .estado-kpi-row:last-child {{ border-bottom: none; }}
    .estado-kpi-label {{
        display: flex;
        align-items: center;
        gap: 6px;
        color: {C['muted']};
        font-weight: 500;
        font-size: 0.72rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 80%;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }}
    .estado-kpi-n {{
        font-family: 'DM Mono', monospace;
        font-weight: 800;
        font-size: 1.05rem;
        color: {C['azul_oscuro']};
        min-width: 2rem;
        text-align: right;
        line-height: 1;
    }}

    /* ── Section heading ── */
    .section-heading {{
        font-family: 'Montserrat', sans-serif;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: {C['azul_oscuro']};
        border-bottom: 2px solid {C['cian']};
        padding-bottom: 0.45rem;
        margin: 0 0 1rem 0;
    }}

    /* ── Tabs ── */
    div[data-testid="stTabs"] [role="tablist"] {{
        background: rgba(255,255,255,0.70);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        border-radius: 10px 10px 0 0;
        padding: 0 1rem;
        border-bottom: 2px solid {C['border']};
        gap: 0;
    }}
    div[data-testid="stTabs"] [role="tab"] {{
        font-family: 'Montserrat', sans-serif !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        color: {C['muted']} !important;
        padding: 0.75rem 1.2rem !important;
        border-bottom: 2px solid transparent !important;
        margin-bottom: -2px !important;
    }}
    div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
        color: {C['azul_oscuro']} !important;
        border-bottom-color: {C['cian']} !important;
    }}
    div[data-testid="stTabs"] [data-testid="stTabsContent"] {{
        background: #ffffff;
        border-radius: 0 0 12px 12px;
        padding: 1.4rem;
        box-shadow: 0 4px 24px rgba(0,40,90,0.10), 0 1px 4px rgba(0,0,0,0.06);
    }}

    /* ── Summary table ── */
    .summary-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.83rem;
        background: #ffffff;
        border-radius: 8px;
        overflow: hidden;
    }}
    .summary-table thead tr {{
        background: {C['azul_oscuro']};
        color: white;
    }}
    .summary-table th {{
        padding: 0.7rem 0.9rem;
        font-family: 'Montserrat', sans-serif;
        font-size: 0.64rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        text-align: left;
        white-space: nowrap;
        line-height: 1.4;
    }}
    .summary-table td {{
        padding: 0.65rem 0.9rem;
        border-bottom: 1px solid {C['border']};
        vertical-align: middle;
        background: #ffffff;
    }}
    .summary-table tbody tr:nth-child(even) td {{ background: #f7fafd; }}
    .summary-table tbody tr:last-child td {{ border-bottom: none; }}
    .summary-table tbody tr:hover td {{ background: #e8f3ff !important; transition: background 0.15s; }}
    .summary-table .col-total {{
        background: {C['azul_oscuro']} !important;
        font-family: 'DM Mono', monospace;
        font-weight: 700;
        font-size: 0.83rem;
        color: #ffffff !important;
        border-left: 2px solid rgba(255,255,255,0.2);
        text-align: center;
    }}
    .summary-table thead .col-total {{
        background: {C['azul_medio']} !important;
        font-size: 0.64rem;
        font-family: 'Montserrat', sans-serif;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
    }}
    .summary-table tbody tr:nth-child(even) .col-total {{ background: {C['azul_oscuro']} !important; }}
    .summary-table tbody tr:hover .col-total {{ background: {C['azul_medio']} !important; }}
    .entidad-name {{
        font-weight: 600;
        font-size: 0.83rem;
        color: {C['azul_oscuro']};
    }}
    .dias-val {{
        font-family: 'DM Mono', monospace;
        font-size: 0.8rem;
        font-weight: 500;
    }}
    .null-cell {{ color: {C['border']}; }}

    /* ── Badges ── */
    .badge {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 3px 9px;
        border-radius: 20px;
        font-size: 0.68rem;
        font-weight: 700;
        margin-left: 5px;
        vertical-align: middle;
        cursor: help;
        position: relative;
    }}
    .badge-green  {{ background: #d1fae5; color: #065f46; }}
    .badge-yellow {{ background: #fef3c7; color: #92400e; }}
    .badge-orange {{ background: #ffedd5; color: #9a3412; }}
    .badge-red    {{ background: #fee2e2; color: #991b1b; }}
    .badge-black  {{ background: #1e293b; color: #f1f5f9; }}
    .badge-dot {{
        width: 8px; height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
        display: inline-block;
    }}
    .badge-green  .badge-dot {{ background: #059669; }}
    .badge-yellow .badge-dot {{ background: #d97706; }}
    .badge-orange .badge-dot {{ background: #ea580c; }}
    .badge-red    .badge-dot {{ background: #dc2626; }}
    .badge-black  .badge-dot {{ background: #94a3b8; }}
    .badge-tooltip {{
        display: none;
        position: fixed;
        background: {C['text']};
        color: white;
        font-family: 'Montserrat', sans-serif;
        font-size: 0.72rem;
        font-weight: 400;
        line-height: 1.5;
        padding: 0.55rem 0.8rem;
        border-radius: 8px;
        width: 240px;
        text-align: left;
        text-transform: none;
        letter-spacing: 0;
        z-index: 99999;
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        pointer-events: none;
        white-space: normal;
    }}
    .badge-tooltip::after {{
        content: '';
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        border: 5px solid transparent;
    }}
    .badge-tooltip.tip-arriba::after {{
        top: 100%;
        border-top-color: {C['text']};
    }}
    .badge-tooltip.tip-abajo::after {{
        bottom: 100%;
        border-bottom-color: {C['text']};
    }}

    /* ── Evaluación — calificación card ── */
    .eval-card {{
        background: #ffffff;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        box-shadow: 0 2px 12px rgba(0,40,90,0.09);
        margin-bottom: 0.6rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }}
    .eval-bar-wrap {{ flex: 1; }}
    .eval-label {{
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: {C['muted']};
        margin-bottom: 0.3rem;
    }}
    .eval-bar-bg {{
        background: {C['border']};
        border-radius: 6px;
        height: 10px;
        overflow: hidden;
        margin-bottom: 0.2rem;
    }}
    .eval-bar-fill {{
        height: 100%;
        border-radius: 6px;
        transition: width 0.4s ease;
    }}
    .eval-score {{
        font-family: 'DM Mono', monospace;
        font-size: 1.1rem;
        font-weight: 700;
        min-width: 3rem;
        text-align: right;
        color: {C['azul_oscuro']};
    }}

    /* ── Detail table ── */
    .detail-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.81rem;
        margin-top: 0.4rem;
    }}
    .detail-table th {{
        background: #f1f5f9;
        color: {C['azul_oscuro']};
        font-family: 'Montserrat', sans-serif;
        font-size: 0.63rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        padding: 0.5rem 0.85rem;
        text-align: left;
        border-bottom: 2px solid {C['border']};
    }}
    .detail-table td {{
        padding: 0.55rem 0.85rem;
        border-bottom: 1px solid {C['border']};
        vertical-align: middle;
    }}
    .detail-table tbody tr:last-child td {{ border-bottom: none; }}
    .detail-table tbody tr.row-green  td {{ background: #f0fdf4; }}
    .detail-table tbody tr.row-yellow td {{ background: #fffbeb; }}
    .detail-table tbody tr.row-orange td {{ background: #fff7ed; }}
    .detail-table tbody tr.row-black  td {{ background: #f1f5f9; }}
    .detail-table tbody tr.row-green:hover  td {{ background: #dcfce7 !important; }}
    .detail-table tbody tr.row-yellow:hover td {{ background: #fef3c7 !important; }}
    .detail-table tbody tr.row-orange:hover td {{ background: #ffedd5 !important; }}
    .detail-table tbody tr.row-black:hover  td {{ background: #e2e8f0 !important; }}
    .detail-table tbody tr:hover td {{ background: #f0f6ff; }}
    .bpin-tag {{
        font-family: 'DM Mono', monospace;
        font-size: 0.7rem;
        background: #f1f5f9;
        color: {C['muted']};
        padding: 2px 6px;
        border-radius: 4px;
    }}
    .estado-tag {{
        font-size: 0.7rem;
        background: #eff6ff;
        color: {C['azul_medio']};
        padding: 2px 7px;
        border-radius: 4px;
        font-weight: 500;
        white-space: nowrap;
    }}

    /* ── Expander ── */
    div[data-testid="stExpander"] > details {{
        border-radius: 10px !important;
        overflow: hidden !important;
        box-shadow: 0 2px 10px rgba(0,40,90,0.08) !important;
        margin-bottom: 0.5rem !important;
        border: none !important;
    }}
    div[data-testid="stExpander"] > details > summary {{
        background: #ffffff !important;
        border: none !important;
        border-left: 4px solid {C['azul_oscuro']} !important;
        border-radius: 10px !important;
        font-family: 'Montserrat', sans-serif !important;
        font-weight: 700 !important;
        font-size: 0.84rem !important;
        color: {C['azul_oscuro']} !important;
        padding: 0.75rem 1.1rem !important;
        transition: background 0.15s, border-color 0.15s !important;
    }}
    div[data-testid="stExpander"] > details > summary:hover {{
        background: #f0f7ff !important;
        border-left-color: {C['cian']} !important;
    }}
    div[data-testid="stExpander"] > details[open] > summary {{
        border-radius: 10px 10px 0 0 !important;
        border-left-color: {C['cian']} !important;
        background: #f8fbff !important;
    }}
    div[data-testid="stExpander"] > details > div {{
        border: none !important;
        border-left: 4px solid {C['cian']} !important;
        border-radius: 0 0 10px 10px !important;
        background: #ffffff !important;
        padding: 0.2rem 1rem 0.8rem 1rem !important;
    }}

    /* ── Tooltip encabezado tabla ── */
    .th-wrap {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
        cursor: default;
        position: relative;
    }}
    .th-icon {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: rgba(255,255,255,0.2);
        color: white;
        font-size: 0.6rem;
        font-weight: 700;
        cursor: help;
        line-height: 1;
        flex-shrink: 0;
    }}
    .th-tooltip {{
        visibility: hidden;
        opacity: 0;
        position: absolute;
        top: calc(100% + 8px);
        left: 50%;
        transform: translateX(-50%);
        background: {C['text']};
        color: white;
        font-family: 'Montserrat', sans-serif;
        font-size: 0.73rem;
        font-weight: 400;
        line-height: 1.55;
        padding: 0.6rem 0.85rem;
        border-radius: 8px;
        white-space: normal;
        width: 230px;
        text-align: left;
        text-transform: none;
        letter-spacing: 0;
        z-index: 9999;
        box-shadow: 0 4px 18px rgba(0,0,0,0.28);
        pointer-events: none;
        transition: opacity 0.15s ease;
    }}
    .th-tooltip strong {{
        display: block;
        margin-bottom: 4px;
        font-size: 0.75rem;
        color: {C['cian']};
    }}
    .th-tooltip::before {{
        content: '';
        position: absolute;
        top: -6px;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
        border-top: none;
        border-bottom-color: {C['text']};
    }}
    .th-wrap:hover .th-tooltip {{ visibility: visible; opacity: 1; }}

    /* ── Download button ── */
    .stDownloadButton > button {{
        background: {C['verde_oscuro']} !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-family: 'Montserrat', sans-serif !important;
        font-size: 0.83rem !important;
        padding: 0.5rem 1.4rem !important;
    }}
    .stDownloadButton > button:hover {{ background: {C['verde_medio']} !important; }}

    /* ── Multiselect / selectbox ── */
    span[data-baseweb="tag"] {{
        background: {C['azul_medio']} !important;
        color: white !important;
        border-radius: 4px !important;
    }}
    span[data-baseweb="tag"] span {{ color: white !important; font-size: 0.75rem !important; }}

    /* ── Tarjeta de error ── */
    .error-card {{
        background: #fff5f5;
        border: 1.5px solid #fca5a5;
        border-left: 5px solid #dc2626;
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        margin: 1rem 0;
    }}
    .error-card .error-title {{
        font-family: 'Montserrat', sans-serif;
        font-size: 0.95rem;
        font-weight: 700;
        color: #991b1b;
        margin-bottom: 0.4rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }}
    .error-card .error-body {{
        font-size: 0.83rem;
        color: #7f1d1d;
        line-height: 1.6;
        margin-bottom: 0.8rem;
    }}
    .error-card .error-fix {{
        background: #fef2f2;
        border-radius: 6px;
        padding: 0.6rem 0.9rem;
        font-size: 0.8rem;
        color: #991b1b;
        border: 1px solid #fca5a5;
    }}
    .error-card .error-fix strong {{
        display: block;
        margin-bottom: 0.3rem;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: #dc2626;
    }}
    .error-cols {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-top: 0.5rem;
    }}
    .col-missing {{
        background: #fee2e2;
        color: #991b1b;
        font-family: 'Montserrat', monospace;
        font-size: 0.73rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 4px;
        border: 1px solid #fca5a5;
    }}
    .col-wrong-type {{
        background: #fff7ed;
        color: #9a3412;
        font-family: 'Montserrat', monospace;
        font-size: 0.73rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 4px;
        border: 1px solid #fed7aa;
    }}
    .ref-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 0.78rem;
        margin-top: 0.8rem;
        border-radius: 8px;
        overflow: hidden;
    }}
    .ref-table th {{
        background: #f1f5f9;
        color: {C['azul_oscuro']};
        font-weight: 700;
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        padding: 0.45rem 0.75rem;
        text-align: left;
        border-bottom: 2px solid {C['border']};
    }}
    .ref-table td {{
        padding: 0.4rem 0.75rem;
        border-bottom: 1px solid {C['border']};
        color: {C['text']};
    }}
    .ref-table tr:last-child td {{ border-bottom: none; }}
    .ref-table code {{
        background: #f1f5f9;
        padding: 1px 6px;
        border-radius: 3px;
        font-size: 0.72rem;
        color: {C['azul_medio']};
    }}

    /* ── Tooltip de cálculo de días ── */
    .dias-tip-wrap {{
        position: relative;
        display: inline-block;
    }}
    .dias-val-link {{
        font-family: 'DM Mono', monospace;
        font-weight: 600;
        font-size: 0.8rem;
        border-bottom: 1px dashed {C['azul_medio']};
        cursor: help;
        padding-bottom: 1px;
    }}
    .dias-tip-box {{
        display: none;
        position: fixed;
        background: {C['azul_oscuro']};
        color: #ffffff;
        border-radius: 8px;
        padding: 0.75rem 0.9rem;
        width: 255px;
        box-shadow: 0 8px 28px rgba(0,20,60,0.35);
        z-index: 99999;
        pointer-events: none;
        font-size: 0.74rem;
        line-height: 1.5;
    }}
    .dias-tip-box::after {{
        content: '';
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        border: 6px solid transparent;
    }}
    .dias-tip-box.tip-abajo::after {{
        bottom: 100%;
        border-bottom-color: {C['azul_oscuro']};
    }}
    .dias-tip-box.tip-arriba::after {{
        top: 100%;
        border-top-color: {C['azul_oscuro']};
    }}
    .dias-tip-title {{
        font-family: 'Montserrat', sans-serif;
        font-size: 0.62rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: {C['cian']};
        margin-bottom: 0.5rem;
    }}
    .dias-tip-row {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.5rem;
        margin: 0.15rem 0;
    }}
    .dias-tip-lbl {{
        color: rgba(255,255,255,0.6);
        font-size: 0.7rem;
        flex-shrink: 0;
    }}
    .dias-tip-val {{
        font-family: 'DM Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        color: #ffffff;
        text-align: right;
    }}
    .dias-tip-op {{
        font-size: 0.65rem;
        color: rgba(255,255,255,0.4);
        margin: 0.1rem 0;
        padding-left: 0.2rem;
    }}
    .dias-tip-sep {{
        border-top: 1px solid rgba(255,255,255,0.15);
        margin: 0.4rem 0 0.35rem;
    }}
    .dias-tip-result {{
        font-family: 'DM Mono', monospace;
        font-weight: 800;
        font-size: 0.88rem;
        color: {C['cian']};
        text-align: right;
    }}
    .dias-tip-nota {{
        font-size: 0.65rem;
        color: rgba(255,255,255,0.45);
        margin-top: 0.45rem;
        line-height: 1.4;
        border-top: 1px solid rgba(255,255,255,0.08);
        padding-top: 0.35rem;
    }}

    /* ══════════════════════════════════════════════════════════════
       TOOLTIP ESTADO PROYECTO — una columna, dinámico vía JS
       ══════════════════════════════════════════════════════════════ */
    .etip-trigger {{
        position: relative;
        cursor: pointer;
    }}
    /* El popup NUNCA se muestra por CSS hover — solo JS lo controla.
     * Los estilos de posición/tamaño se aplican inline via JS cuando
     * el popup se mueve al document.body. Aquí solo van los estilos
     * de apariencia que deben heredarse. */
    .etip-popup {{
        display: none;
        position: fixed;
        z-index: 99999;
        width: 380px;
        max-height: 86vh;
        overflow-y: auto;
        overflow-x: hidden;
        background: #1a2332;
        border-radius: 12px;
        padding: 0.9rem 1.1rem;
        box-shadow: 0 8px 40px rgba(0,0,0,0.45);
        color: rgba(255,255,255,0.85);
        font-size: 0.71rem;
        line-height: 1.55;
        pointer-events: none;
        top: 0;
        left: 0;
        box-sizing: border-box;
    }}
    .etip-popup::-webkit-scrollbar {{ width: 4px; }}
    .etip-popup::-webkit-scrollbar-track {{ background: transparent; }}
    .etip-popup::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.18); border-radius: 2px; }}
    /* Separador entre secciones */
    .etip-sep {{
        border: none;
        border-top: 1px solid rgba(255,255,255,0.08);
        margin: 0.5rem 0;
    }}
    .etip-estado {{
        display: block;
        font-family: 'Montserrat', sans-serif;
        font-size: 0.66rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #47b1d5;
        margin-bottom: 0.3rem;
    }}
    .etip-desc {{
        font-size: 0.70rem;
        color: rgba(255,255,255,0.58);
        margin: 0 0 0;
        line-height: 1.55;
    }}
    .etip-section-title {{
        font-family: 'Montserrat', sans-serif;
        font-size: 0.56rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #47b1d5;
        margin: 0 0 0.2rem;
    }}
    .etip-row {{
        font-size: 0.69rem;
        color: rgba(255,255,255,0.80);
        margin-bottom: 0.14rem;
        line-height: 1.5;
        word-break: break-word;
    }}
    .etip-small {{
        font-size: 0.64rem;
        color: rgba(255,255,255,0.46);
        line-height: 1.4;
        word-break: break-word;
        margin-bottom: 0.12rem;
    }}
    .etip-label {{
        color: rgba(255,255,255,0.42);
        font-weight: 600;
    }}
    .etip-i {{
        font-size: 0.65rem;
        opacity: 0.6;
        font-style: normal;
        margin-left: 2px;
    }}
    .etip-accion {{
        margin-top: 0;
        background: rgba(71,177,213,0.09);
        border-left: 3px solid #47b1d5;
        border-radius: 4px;
        padding: 0.38rem 0.7rem;
        font-size: 0.68rem;
        color: rgba(255,255,255,0.75);
        line-height: 1.5;
        word-break: break-word;
    }}
    .etip-accion-label {{
        display: block;
        font-size: 0.56rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #47b1d5;
        margin-bottom: 0.12rem;
    }}
    /* Filas de fechas en dos columnas con flex */
    .etip-fechas {{
        display: flex;
        flex-direction: column;
        gap: 0;
    }}
    .etip-fecha-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        padding: 0.18rem 0;
        gap: 0.5rem;
    }}
    .etip-fecha-row:last-child {{ border-bottom: none; }}
    .etip-fecha-lbl {{
        color: rgba(255,255,255,0.48);
        font-size: 0.62rem;
        white-space: nowrap;
        flex-shrink: 0;
    }}
    .etip-fecha-val {{
        color: rgba(255,255,255,0.88);
        font-family: 'DM Mono', monospace;
        font-size: 0.63rem;
        white-space: nowrap;
        text-align: right;
    }}
    </style>
    """, unsafe_allow_html=True)

    # ── JS unificado: tooltips dinámicos (etip + dias + badge) + toggle contratos ──
    components.html("""
    <script>
    (function() {
      var doc = window.parent.document;
      var win = window.parent;

      // ── Toggle contratos ─────────────────────────────────────────────────
      function initToggleCtto() {
        doc.querySelectorAll('.ctto-toggle').forEach(function(btn) {
          if (btn._cttoInit) return;
          btn._cttoInit = true;
          btn.addEventListener('click', function() {
            var id  = btn.getAttribute('data-target');
            var row = doc.getElementById(id);
            if (!row) return;
            var open = row.classList.toggle('visible');
            btn.classList.toggle('open', open);
          });
        });
      }

      // ── Posicionador genérico para dias-tip-box y badge-tooltip ──────────
      function positionTipSmall(trigger, tip, tipH, tipW) {
        var rect = trigger.getBoundingClientRect();
        var margin = 10;
        var spaceBelow = win.innerHeight - rect.bottom;
        var spaceAbove = rect.top;

        tip.style.display = 'block';
        tip.classList.remove('tip-abajo', 'tip-arriba');

        if (spaceBelow >= tipH + margin || spaceBelow >= spaceAbove) {
          tip.style.top    = (rect.bottom + 8) + 'px';
          tip.style.bottom = 'auto';
          tip.classList.add('tip-abajo');
        } else {
          tip.style.top    = (rect.top - tipH - 8) + 'px';
          tip.style.bottom = 'auto';
          tip.classList.add('tip-arriba');
        }
        var left = rect.left + rect.width / 2 - tipW / 2;
        left = Math.max(8, Math.min(left, win.innerWidth - tipW - 8));
        tip.style.left = left + 'px';
      }

      // ── Posicionador dinámico para etip-popup ────────────────────────────
      // IMPORTANTE: el popup se MUEVE al body del documento principal al activarse.
      // Esto lo saca del stacking context de .proy-table (border-radius + overflow:hidden)
      // que atrapa position:fixed y causa el desborde visual.
      function posicionarEtip() {
        doc.querySelectorAll('.etip-trigger').forEach(function(trigger) {
          if (trigger._etipInit) return;
          trigger._etipInit = true;

          // El popup hijo — guardamos referencia y lo movemos al body
          var popup = trigger.querySelector('.etip-popup');
          if (!popup) return;

          // Guardamos la referencia al trigger en el popup para poder volver
          popup._ownerTrigger = trigger;

          trigger.addEventListener('mouseenter', function() {
            // 1. Mover al body si no está ya ahí
            if (popup.parentNode !== doc.body) {
              doc.body.appendChild(popup);
            }

            var vw = win.innerWidth;
            var vh = win.innerHeight;

            // 2. Posicionar fuera de vista para medir dimensiones reales
            popup.style.cssText = [
              'display:block',
              'visibility:hidden',
              'position:fixed',
              'left:-9999px',
              'top:-9999px',
              'width:380px',
              'max-height:86vh',
              'overflow-y:auto',
              'overflow-x:hidden',
              'z-index:99999',
              'box-sizing:border-box',
              'background:#1a2332',
              'border-radius:12px',
              'padding:0.9rem 1.1rem',
              'box-shadow:0 8px 40px rgba(0,0,0,0.45)',
              'color:rgba(255,255,255,0.85)',
              'font-size:0.71rem',
              'line-height:1.55',
              'pointer-events:none',
            ].join(';');

            // 3. Medir altura real
            var pr = popup.getBoundingClientRect();
            var pw = 380;
            var ph = Math.min(pr.height || 360, vh * 0.86);

            // 4. Posición del trigger en el viewport del parent
            var rect = trigger.getBoundingClientRect();

            // 5. Calcular posición horizontal: derecha, luego izquierda, luego borde
            var left;
            if (rect.right + pw + 14 <= vw) {
              left = rect.right + 10;
            } else if (rect.left - pw - 14 >= 0) {
              left = rect.left - pw - 10;
            } else {
              left = Math.max(8, vw - pw - 12);
            }

            // 6. Calcular posición vertical: alinear con fila, subir si se sale
            var top = rect.top;
            if (top + ph > vh - 12) {
              top = Math.max(8, vh - ph - 12);
            }

            // 7. Aplicar posición final y mostrar
            popup.style.left       = left + 'px';
            popup.style.top        = top  + 'px';
            popup.style.visibility = 'visible';
          });

          trigger.addEventListener('mouseleave', function() {
            popup.style.display    = 'none';
            popup.style.visibility = 'hidden';
          });
        });
      }

      // ── dias-tip-box y badge-tooltip ─────────────────────────────────────
      function initTooltips() {
        doc.querySelectorAll('.dias-tip-wrap').forEach(function(wrap) {
          if (wrap._tipInit) return;
          wrap._tipInit = true;
          var tip = wrap.querySelector('.dias-tip-box');
          if (!tip) return;
          wrap.addEventListener('mouseenter', function() { positionTipSmall(wrap, tip, 220, 255); });
          wrap.addEventListener('mouseleave', function() { tip.style.display = 'none'; });
        });

        doc.querySelectorAll('.badge').forEach(function(badge) {
          if (badge._tipInit) return;
          badge._tipInit = true;
          var tip = badge.querySelector('.badge-tooltip');
          if (!tip) return;
          badge.addEventListener('mouseenter', function() { positionTipSmall(badge, tip, 110, 240); });
          badge.addEventListener('mouseleave', function() { tip.style.display = 'none'; });
        });
      }

      function initAll() {
        initToggleCtto();
        initTooltips();
        posicionarEtip();
      }

      var observer = new MutationObserver(function() { initAll(); });
      observer.observe(doc.body, { childList: true, subtree: true });
      initAll();
    })();
    </script>
    """, height=0)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES DE VALIDACIÓN
# ─────────────────────────────────────────────────────────────────────────────
TABLA_ESPERADA = "MatrizSeguimientoEvaluacion"

COLUMNAS_ESPERADAS = {
    "ENTIDAD O SECRETARIA":                 ("texto",  [pl.Utf8, pl.String]),
    "BPIN":                                 ("texto",  [pl.Utf8, pl.String]),
    "NOMBRE PROYECTO":                      ("texto",  [pl.Utf8, pl.String]),
    "ESTADO PROYECTO":                      ("texto",  [pl.Utf8, pl.String]),
    "ESTADO CONTRATO":                      ("texto",  [pl.Utf8, pl.String]),
    "CPI":                                  ("número", [pl.Float32, pl.Float64, pl.Int32, pl.Int64]),
    "SPI":                                  ("número", [pl.Float32, pl.Float64, pl.Int32, pl.Int64]),
    "FECHA APROBACIÓN PROYECTO":            ("fecha",  [pl.Date, pl.Datetime]),
    "FECHA DE APERTURA DEL PRIMER PROCESO": ("fecha",  [pl.Date, pl.Datetime]),
    "FECHA SUSCRIPCION":                    ("fecha",  [pl.Date, pl.Datetime]),
    "FECHA ACTA INICIO":                    ("fecha",  [pl.Date, pl.Datetime]),
    "HORIZONTE DEL PROYECTO":               ("fecha",  [pl.Date, pl.Datetime]),
    "FECHA DE FINALIZACIÓN":                ("fecha",  [pl.Date, pl.Datetime]),
    "FECHA DE CORTE GESPROY":               ("fecha",  [pl.Date, pl.Datetime]),
}

TIPO_LABEL = {
    "texto":  "Texto",
    "número": "Número decimal",
    "fecha":  "Fecha",
}

TIPO_EJEMPLO = {
    "texto":  "Ej: «Infraestructura», «SIN CONTRATAR»",
    "número": "Ej: 0, 1.5, 0.87  (sin letras ni símbolos)",
    "fecha":  "Ej: 15/03/2024  (formato fecha de Excel)",
}

# ─────────────────────────────────────────────────────────────────────────────
# INTERVALOS Y SEMÁFOROS
# ─────────────────────────────────────────────────────────────────────────────
INTERVALOS = {
    "hito_1_val": [
        ("0-100",   0,   100),
        ("101-150", 101, 150),
        ("151-180", 151, 180),
        (">180",    181, None),
    ],
    "hito_2_val": [
        ("0-100",   0,   100),
        ("101-150", 101, 150),
        ("151-180", 151, 180),
        (">180",    181, None),
    ],
    # ── Hito 3 actualizado por la entidad ──
    "hito_3_val": [
        ("0-15",  0,  15),
        ("16-30", 16, 30),
        ("31-45", 31, 45),
        (">45",   46, None),
    ],
    # hito_4_val no usa INTERVALOS — se clasifica en meses en data.py
    "hito_5_val": [
        ("0-100",   0,   100),
        ("101-150", 101, 150),
        ("151-180", 151, 180),
        (">180",    181, None),
    ],
}

SEMAFOROS = {
    "hito_1_val": {
        "0-100":   ("green",  "Verde",   "Proyecto dentro de los tiempos para su primera apertura del proceso de contratación."),
        "101-150": ("yellow", "Naranja", "Proyecto en alerta: más de 100 días sin apertura del primer proceso precontractual."),
        "151-180": ("orange", "Rojo",    "Proyecto en alerta roja: más de 150 días sin apertura del primer proceso precontractual."),
        ">180":    ("black",  "Negro",   "Proyecto en alerta negra: más de 180 días sin apertura del primer proceso precontractual."),
    },
    "hito_2_val": {
        "0-100":   ("green",  "Verde",   "Proyecto dentro de los tiempos para la firma del primer contrato."),
        "101-150": ("yellow", "Naranja", "Proyecto en alerta: más de 100 días sin firma del primer contrato."),
        "151-180": ("orange", "Rojo",    "Proyecto en alerta roja: más de 150 días sin firma del primer contrato."),
        ">180":    ("black",  "Negro",   "Proyecto en alerta negra: más de 180 días sin firma del primer contrato."),
    },
    # ── Hito 3 actualizado por la entidad ──
    "hito_3_val": {
        "0-15":  ("green",  "Verde",   "El proyecto registró su acta de inicio dentro de los primeros 15 días desde la suscripción. Gestión oportuna."),
        "16-30": ("yellow", "Naranja", "Han transcurrido entre 16 y 30 días desde la suscripción del contrato sin acta de inicio. Se recomienda acelerar el proceso."),
        "31-45": ("orange", "Rojo",    "Han transcurrido entre 31 y 45 días desde la suscripción sin acta de inicio. Situación crítica que requiere atención inmediata."),
        ">45":   ("black",  "Negro",   "Más de 45 días sin acta de inicio desde la suscripción del contrato. Requiere intervención urgente."),
    },
    "hito_4_val": {
        "0-1":   ("green",  "Verde",   "Proyecto presenta horizonte vigente."),
        "1.1-3": ("yellow", "Naranja", "Proyecto con horizonte vencido entre 1 y 3 meses."),
        "3.1-6": ("orange", "Rojo",    "Proyecto con horizonte vencido mayor a 3 meses."),
        ">6":    ("black",  "Negro",   "Proyecto con horizonte vencido mayor a 6 meses."),
    },
    "hito_5_val": {
        "0-100":   ("green",  "Verde",   "Proyecto dentro de los tiempos para pasar a estado 'Para cierre'."),
        "101-150": ("yellow", "Naranja", "Proyecto en alerta: más de 100 días desde su terminación sin pasar a 'Para cierre'."),
        "151-180": ("orange", "Rojo",    "Proyecto en alerta roja: más de 150 días desde su terminación."),
        ">180":    ("black",  "Negro",   "Proyecto en alerta negra: más de 180 días desde su terminación."),
    },
}

TABLA_DESCENTRALIZADAS = "OtrosEjecutoresDescentralizadas"
COLS_EVAL = [
    "CALIFICACIÓN DESEMPEÑO EN LA CONTRATACIÓN",
    "CALIFICACIÓN INFORMACIÓN A TIEMPO",
    "CALIFICACIÓN EJECUCIÓN DEL PROYECTO",
    "CALIFICACIÓN CALIDAD INFORMACIÓN",
]
COLS_EVAL_LABELS = [
    "Desempeño en contratación",
    "Información a tiempo",
    "Ejecución del proyecto",
    "Calidad de la información",
]
