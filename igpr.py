"""
igpr.py
Vista del Índice de Gestión de Proyectos de Regalías (IGPR).
Consolidado de los 5 trimestres disponibles (I-IV 2025 y I 2026).

Estructura de la vista
──────────────────────
1.  Header + KPIs globales (promedio, mejor periodo, total proyectos, % adecuados)
2.  Pestañas:
      a. Resumen general — evolución del promedio por trimestre + tabla matriz
         (entidad × periodo) con código de color por la escala de la Res. 4574.
      b. Detalle por trimestre — selector de vigencia/trimestre + tabla de
         proyectos con desplegables por entidad.
      c. Detalle por entidad — selector de entidad + evolución y tabla de sus
         proyectos a lo largo de todos los trimestres.
      d. Metodología — resumen visual de la Resolución 4574 (estados,
         indicadores, escala diferencial).
"""
from __future__ import annotations

import html
import polars as pl
import streamlit as st

from constants import C
from data_igpr import (
    cargar_igpr,
    resumen_por_periodo,
    resumen_por_entidad_periodo,
    color_por_puntaje,
    clasificar_puntaje,
    ORDEN_TRIMESTRE,
    TRIMESTRE_CORTO,
    UMBRAL_ADECUADO_DEPARTAMENTO,
)


# ─────────────────────────────────────────────────────────────────────────────
# CSS específico de la vista IGPR (se inyecta una sola vez).
# Está alineado al diseño "institucional/sin gradientes" del resto de la app.
# ─────────────────────────────────────────────────────────────────────────────
_CSS_IGPR = f"""
<style>
.igpr-kpi-row {{
    display:grid; grid-template-columns:repeat(4, minmax(0,1fr));
    gap:0.9rem; margin:0.4rem 0 1.2rem 0;
}}
.igpr-kpi {{
    background:{C['white']}; border:1px solid {C['border']};
    border-left:5px solid {C['azul_medio']};
    border-radius:10px; padding:0.85rem 1rem;
}}
.igpr-kpi.is-adecuado  {{ border-left-color:#15803d; }}
.igpr-kpi.is-promedio  {{ border-left-color:{C['azul_medio']}; }}
.igpr-kpi.is-proyectos {{ border-left-color:{C['naranja']}; }}
.igpr-kpi.is-mejor     {{ border-left-color:#1d4ed8; }}
.igpr-kpi .lab {{
    font-size:0.68rem; color:{C['muted']}; font-weight:700;
    text-transform:uppercase; letter-spacing:0.6px; margin:0 0 0.18rem;
}}
.igpr-kpi .val {{
    font-family:'Montserrat',sans-serif; font-size:1.55rem; font-weight:700;
    color:{C['azul_oscuro']}; line-height:1.1;
}}
.igpr-kpi .sub {{ font-size:0.72rem; color:{C['muted']}; margin-top:0.18rem; }}

/* Tabla matriz Entidad × Periodo */
.igpr-matriz {{
    width:100%; border-collapse:separate; border-spacing:0;
    border:1px solid {C['border']}; border-radius:10px; overflow:hidden;
    font-size:0.82rem; background:{C['white']};
}}
.igpr-matriz th, .igpr-matriz td {{
    padding:0.55rem 0.7rem; border-bottom:1px solid {C['border']};
    border-right:1px solid {C['border']}; text-align:center; white-space:nowrap;
}}
.igpr-matriz th:last-child, .igpr-matriz td:last-child {{ border-right:none; }}
.igpr-matriz thead th {{
    background:{C['azul_oscuro']}; color:#fff; font-weight:600;
    text-transform:uppercase; letter-spacing:0.4px; font-size:0.72rem;
}}
.igpr-matriz td.ent {{
    text-align:left; font-weight:600; color:{C['text']};
    background:#f8fafc; min-width:280px; max-width:380px;
    white-space:normal;
}}
.igpr-matriz tr:last-child td {{ border-bottom:none; }}
.igpr-cell {{
    display:inline-block; min-width:54px; padding:0.18rem 0.55rem;
    border-radius:16px; color:#fff; font-weight:700; font-size:0.82rem;
}}
.igpr-cell.sin-dato {{
    background:transparent; color:{C['muted']}; font-weight:500;
}}

/* Leyenda de escala */
.igpr-legend {{
    display:flex; gap:1rem; flex-wrap:wrap; margin:0.4rem 0 0.8rem;
    font-size:0.75rem; color:{C['text']};
}}
.igpr-legend .dot {{
    display:inline-block; width:12px; height:12px; border-radius:50%;
    margin-right:0.35rem; vertical-align:-1px;
}}

/* Tarjeta de proyecto desplegable */
.igpr-proy {{
    background:#fff; border:1px solid {C['border']};
    border-radius:8px; padding:0.55rem 0.75rem;
    margin-bottom:0.45rem;
    display:grid; grid-template-columns: 1fr auto; gap:0.6rem;
    align-items:center;
}}
.igpr-proy .nombre {{
    font-size:0.84rem; color:{C['text']}; font-weight:500; line-height:1.3;
}}
.igpr-proy .bpin {{
    font-size:0.70rem; color:{C['muted']}; font-family:'Consolas',monospace;
    margin-top:0.18rem;
}}
.igpr-proy .pill {{
    display:inline-block; padding:0.22rem 0.7rem; border-radius:14px;
    color:#fff; font-weight:700; font-size:0.78rem;
}}

/* Cards de Metodología */
.igpr-meto-grid {{
    display:grid; grid-template-columns:repeat(auto-fit, minmax(260px,1fr));
    gap:0.9rem; margin-bottom:1rem;
}}
.igpr-meto-card {{
    background:#fff; border:1px solid {C['border']}; border-radius:10px;
    padding:0.9rem 1rem;
}}
.igpr-meto-card h4 {{
    margin:0 0 0.45rem; font-family:'Montserrat',sans-serif;
    font-size:0.95rem; color:{C['azul_oscuro']};
}}
.igpr-meto-card .lab {{
    font-size:0.7rem; text-transform:uppercase; letter-spacing:0.5px;
    color:{C['muted']}; font-weight:700; margin-bottom:0.25rem;
}}
.igpr-meto-card ul {{ margin:0; padding-left:1.1rem; font-size:0.82rem; color:{C['text']}; }}
.igpr-meto-card li {{ margin:0.18rem 0; }}

.igpr-meto-table {{
    width:100%; border-collapse:collapse; font-size:0.82rem;
    border:1px solid {C['border']}; border-radius:8px; overflow:hidden;
    background:#fff;
}}
.igpr-meto-table th, .igpr-meto-table td {{
    padding:0.5rem 0.7rem; border-bottom:1px solid {C['border']}; text-align:left;
}}
.igpr-meto-table thead th {{
    background:#f1f5f9; color:{C['azul_oscuro']}; font-weight:700;
    text-transform:uppercase; letter-spacing:0.4px; font-size:0.72rem;
}}
.igpr-meto-table td.pond {{
    text-align:center; font-weight:700; color:{C['azul_medio']};
}}
.igpr-empty {{
    background:#fff7ed; border:1px dashed #fdba74; border-radius:8px;
    padding:1rem 1.2rem; color:#9a3412; font-size:0.85rem;
}}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de presentación
# ─────────────────────────────────────────────────────────────────────────────
def _pill(p: float | None) -> str:
    """Pildora coloreada con el puntaje (o '—' si no hay dato)."""
    if p is None:
        return f"<span class='igpr-cell sin-dato'>—</span>"
    color = color_por_puntaje(p)
    return f"<span class='igpr-cell' style='background:{color}'>{p:.1f}</span>"


def _leyenda() -> str:
    return (
        "<div class='igpr-legend'>"
        "<span><span class='dot' style='background:#15803d'></span>≥ 80 · Sobresaliente</span>"
        f"<span><span class='dot' style='background:#84cc16'></span>≥ {int(UMBRAL_ADECUADO_DEPARTAMENTO)} · Adecuado</span>"
        "<span><span class='dot' style='background:#f59e0b'></span>40-59 · Limítrofe</span>"
        "<span><span class='dot' style='background:#dc2626'></span>< 40 · Bajo</span>"
        "<span><span class='dot' style='background:#94a3b8'></span>Sin dato</span>"
        "</div>"
    )


def _kpi_card(label: str, value: str, sub: str = "", clase: str = "is-promedio") -> str:
    return (
        f"<div class='igpr-kpi {clase}'>"
        f"<div class='lab'>{html.escape(label)}</div>"
        f"<div class='val'>{value}</div>"
        + (f"<div class='sub'>{html.escape(sub)}</div>" if sub else "")
        + "</div>"
    )


def _periodo_label(vigencia: int, trimestre: str) -> str:
    return f"{TRIMESTRE_CORTO.get(trimestre, '?')} {vigencia}"


# ─────────────────────────────────────────────────────────────────────────────
# Sub-vistas
# ─────────────────────────────────────────────────────────────────────────────
def _resumen_general(df: pl.DataFrame) -> None:
    """Evolución del promedio por trimestre + matriz entidad × periodo."""
    if df.is_empty():
        st.markdown("<div class='igpr-empty'>Aún no se cargó información del IGPR.</div>",
                    unsafe_allow_html=True)
        return

    periodos = resumen_por_periodo(df)
    st.markdown(f"<h4 style='margin:0.4rem 0 0.4rem;color:{C['azul_oscuro']};font-family:Montserrat,sans-serif'>"
                f"Evolución del IGPR (Departamento de Sucre)</h4>",
                unsafe_allow_html=True)

    # Tabla compacta de evolución
    filas = ""
    for r in periodos.iter_rows(named=True):
        per = _periodo_label(r["VIGENCIA"], r["TRIMESTRE EVALUADO"])
        promedio = r["PROMEDIO"]
        cat = clasificar_puntaje(promedio)
        cat_color = color_por_puntaje(promedio)
        filas += (
            f"<tr>"
            f"<td class='ent'>{html.escape(per)}</td>"
            f"<td>{_pill(promedio)}</td>"
            f"<td>{_pill(r['MINIMO'])}</td>"
            f"<td>{_pill(r['MAXIMO'])}</td>"
            f"<td>{r['PROYECTOS']}</td>"
            f"<td><span class='igpr-cell' style='background:{cat_color}'>{cat}</span></td>"
            f"</tr>"
        )

    st.markdown(
        f"""
        <table class='igpr-matriz' style='margin-bottom:1rem'>
          <thead><tr>
            <th style='text-align:left'>Periodo</th>
            <th>Promedio</th>
            <th>Mínimo</th>
            <th>Máximo</th>
            <th>Proyectos</th>
            <th>Categoría</th>
          </tr></thead>
          <tbody>{filas}</tbody>
        </table>
        {_leyenda()}
        """,
        unsafe_allow_html=True,
    )

    # Matriz entidad × periodo
    st.markdown(f"<h4 style='margin:1rem 0 0.4rem;color:{C['azul_oscuro']};font-family:Montserrat,sans-serif'>"
                f"Promedio por entidad y trimestre</h4>",
                unsafe_allow_html=True)

    matriz = resumen_por_entidad_periodo(df)
    if matriz.is_empty():
        st.markdown("<div class='igpr-empty'>No hay entidades con puntaje en este corte.</div>",
                    unsafe_allow_html=True)
        return

    # Orden cronológico de las columnas
    periodos_ord = (
        df.select(["VIGENCIA", "_orden_trim", "TRIMESTRE EVALUADO"])
          .unique()
          .sort(["VIGENCIA", "_orden_trim"])
    )
    cols_periodo = [
        (r["VIGENCIA"], r["TRIMESTRE EVALUADO"])
        for r in periodos_ord.iter_rows(named=True)
    ]

    # Pivot manual a dict {entidad: {(vig, trim): promedio}}
    pivote: dict[str, dict[tuple[int, str], float]] = {}
    for r in matriz.iter_rows(named=True):
        ent = r["ENTIDAD"] or "(Sin entidad)"
        pivote.setdefault(ent, {})[(r["VIGENCIA"], r["TRIMESTRE EVALUADO"])] = r["PROMEDIO"]

    # Promedio global por entidad (para ordenar)
    prom_ent = {
        ent: sum(v.values()) / len(v) if v else None
        for ent, v in pivote.items()
    }
    entidades_orden = sorted(
        pivote.keys(),
        key=lambda e: (prom_ent[e] is None, -(prom_ent[e] or 0))
    )

    header = "<th style='text-align:left'>Entidad</th>" + "".join(
        f"<th>{_periodo_label(v, t)}</th>" for (v, t) in cols_periodo
    ) + "<th>Promedio</th>"

    filas_html = ""
    for ent in entidades_orden:
        # Cada pildora va envuelta en <td>; si la dejamos suelta, Streamlit
        # saca los <span> fuera de la tabla al sanear el HTML.
        celdas = "".join(f"<td>{_pill(pivote[ent].get(p))}</td>" for p in cols_periodo) + \
                 f"<td>{_pill(prom_ent[ent])}</td>"
        filas_html += (
            f"<tr><td class='ent'>{html.escape(ent)}</td>{celdas}</tr>"
        )

    st.markdown(
        f"""
        <div style='overflow-x:auto'>
          <table class='igpr-matriz'>
            <thead><tr>{header}</tr></thead>
            <tbody>{filas_html}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Diagnóstico del descuento 2026 (panel colapsado) ────────────────
    # Muestra cuántos proyectos del trimestre tuvieron al menos una situación
    # marcada SI, junto con el promedio bruto del periodo y el ajustado.
    # El descuento de -10 puntos se aplica al PROMEDIO del periodo cuando al
    # menos un proyecto de la entidad presentó situación.
    flag_col = "PRESENTA ALGUNA SITUACION QUE AFECTA PUNTAJE"
    if flag_col in df.columns:
        df_2026 = df.filter(pl.col("VIGENCIA") == 2026)
        if df_2026.height > 0:
            with st.expander("Diagnóstico · Descuento por situaciones (vigencia 2026)", expanded=False):
                diag = (
                    df_2026
                    .group_by(["PERIODO", "_orden_trim"], maintain_order=True)
                    .agg(
                        pl.col("PUNTAJE").mean().round(2).alias("Promedio_bruto"),
                        pl.col(flag_col).sum().alias("Proyectos_con_situacion"),
                        pl.col("BPIN").n_unique().alias("Total_proyectos"),
                    )
                    .with_columns(
                        pl.when(pl.col("Proyectos_con_situacion") >= 1)
                          .then((pl.col("Promedio_bruto") - 10.0).clip(0.0, 100.0))
                          .otherwise(pl.col("Promedio_bruto"))
                          .round(2)
                          .alias("Promedio_ajustado_(-10_si_hay_situacion)")
                    )
                    .sort("_orden_trim")
                    .drop("_orden_trim")
                )
                st.dataframe(diag.to_pandas(), use_container_width=True, hide_index=True)
                st.caption(
                    "El descuento se aplica al PROMEDIO del periodo cuando al menos "
                    "uno de los proyectos del Departamento de Sucre tiene una situación "
                    "marcada SI en alguna de las 3 columnas (Inconsistencias / "
                    "Irregularidades graves / Modificación de reporte). El descuento "
                    "es de −10 puntos (clamp en 0)."
                )


def _detalle_trimestre(df: pl.DataFrame) -> None:
    """Selector de trimestre + tabla de proyectos con desplegable por entidad."""
    if df.is_empty():
        st.markdown("<div class='igpr-empty'>No hay datos para mostrar.</div>",
                    unsafe_allow_html=True)
        return

    periodos_opciones = (
        df.select(["VIGENCIA", "_orden_trim", "TRIMESTRE EVALUADO", "PERIODO"])
          .unique()
          .sort(["VIGENCIA", "_orden_trim"])
    )
    opciones = [
        (r["PERIODO"], r["VIGENCIA"], r["TRIMESTRE EVALUADO"])
        for r in periodos_opciones.iter_rows(named=True)
    ]
    if not opciones:
        st.markdown("<div class='igpr-empty'>No hay periodos disponibles.</div>",
                    unsafe_allow_html=True)
        return

    labels = [o[0] for o in opciones]
    sel_idx = st.selectbox(
        "Periodo",
        list(range(len(opciones))),
        format_func=lambda i: labels[i],
        index=len(opciones) - 1,  # más reciente por defecto
        key="igpr_sel_periodo",
    )
    sel_vig, sel_trim = opciones[sel_idx][1], opciones[sel_idx][2]

    df_sel = df.filter(
        (pl.col("VIGENCIA") == sel_vig) & (pl.col("TRIMESTRE EVALUADO") == sel_trim)
    )

    if df_sel.is_empty():
        st.markdown("<div class='igpr-empty'>Sin proyectos en este periodo.</div>",
                    unsafe_allow_html=True)
        return

    # KPIs del periodo
    prom = df_sel.select(pl.col("PUNTAJE").mean()).item() or 0.0
    pct_adec = (df_sel.filter(pl.col("PUNTAJE") >= UMBRAL_ADECUADO_DEPARTAMENTO).height
                / df_sel.height) * 100 if df_sel.height else 0
    n_proy = df_sel.height

    st.markdown(
        f"<div class='igpr-kpi-row' style='grid-template-columns:repeat(3,minmax(0,1fr));margin:0.6rem 0 1rem'>"
        + _kpi_card("Promedio del periodo", f"{prom:.1f}", clasificar_puntaje(prom), "is-promedio")
        + _kpi_card("Proyectos medidos", f"{n_proy}", f"En {labels[sel_idx]}", "is-proyectos")
        + _kpi_card("% Adecuados", f"{pct_adec:.0f}%", f"Puntaje ≥ {int(UMBRAL_ADECUADO_DEPARTAMENTO)}", "is-adecuado")
        + "</div>"
        + _leyenda(),
        unsafe_allow_html=True,
    )

    # Agrupado por entidad
    grupos = (
        df_sel.group_by("ENTIDAD", maintain_order=True)
              .agg(
                  pl.col("PUNTAJE").mean().round(1).alias("PROM"),
                  pl.col("BPIN").n_unique().alias("N"),
                  pl.struct(["BPIN", "NOMBRE DEL PROYECTO", "PUNTAJE",
                             *(c for c in ["CLASIFICACIÓN PLAZO PARA EJECUCIÓN"]
                               if c in df_sel.columns)])
                    .alias("PROYS"),
              )
              .sort("PROM", descending=True, nulls_last=True)
    )

    incluir_plazo = "CLASIFICACIÓN PLAZO PARA EJECUCIÓN" in df_sel.columns

    for grp in grupos.iter_rows(named=True):
        ent = grp["ENTIDAD"] or "(Sin entidad)"
        with st.expander(f"{ent} · {grp['N']} proyecto{'s' if grp['N'] != 1 else ''} · Promedio {grp['PROM'] if grp['PROM'] is not None else '—'}",
                         expanded=False):
            proys_html = ""
            proys = sorted(grp["PROYS"],
                           key=lambda p: (-(p["PUNTAJE"] if p["PUNTAJE"] is not None else -1)))
            for p in proys:
                nombre = html.escape(str(p.get("NOMBRE DEL PROYECTO") or "(sin nombre)"))
                bpin = html.escape(str(p.get("BPIN") or "—"))
                punt = p.get("PUNTAJE")
                col = color_por_puntaje(punt)
                pill = f"<span class='pill' style='background:{col}'>{punt:.1f}</span>" if punt is not None \
                    else "<span class='pill' style='background:#94a3b8'>—</span>"
                extra_html = ""
                if incluir_plazo:
                    cls = p.get("CLASIFICACIÓN PLAZO PARA EJECUCIÓN")
                    if cls:
                        extra_html = (
                            f"<div style='font-size:0.7rem;color:{C['muted']};margin-top:0.2rem'>"
                            f"Plazo: <b style='color:{C['text']}'>{html.escape(str(cls))}</b></div>"
                        )
                proys_html += (
                    "<div class='igpr-proy'>"
                    f"<div><div class='nombre'>{nombre}</div>"
                    f"<div class='bpin'>BPIN: {bpin}</div>"
                    f"{extra_html}</div>"
                    f"<div>{pill}</div>"
                    "</div>"
                )
            st.markdown(proys_html, unsafe_allow_html=True)


def _detalle_entidad(df: pl.DataFrame) -> None:
    """Selector de entidad + evolución y proyectos a lo largo del tiempo."""
    if df.is_empty():
        st.markdown("<div class='igpr-empty'>No hay datos para mostrar.</div>",
                    unsafe_allow_html=True)
        return

    entidades = (
        df.select(pl.col("ENTIDAD").fill_null("(Sin entidad)"))
          .unique()
          .sort("ENTIDAD")
          .to_series()
          .to_list()
    )
    if not entidades:
        st.markdown("<div class='igpr-empty'>No hay entidades.</div>",
                    unsafe_allow_html=True)
        return

    sel = st.selectbox("Entidad", entidades, key="igpr_sel_entidad")
    df_sel = df.filter(pl.col("ENTIDAD").fill_null("(Sin entidad)") == sel)

    if df_sel.is_empty():
        st.markdown("<div class='igpr-empty'>Sin proyectos para esta entidad.</div>",
                    unsafe_allow_html=True)
        return

    # Evolución por periodo (un solo grupo, esta entidad)
    evol = (
        df_sel.group_by(["VIGENCIA", "_orden_trim", "TRIMESTRE EVALUADO", "PERIODO"], maintain_order=True)
              .agg(
                  pl.col("PUNTAJE").mean().round(1).alias("PROM"),
                  pl.col("BPIN").n_unique().alias("N"),
              )
              .sort(["VIGENCIA", "_orden_trim"])
    )

    filas = ""
    for r in evol.iter_rows(named=True):
        filas += (
            f"<tr>"
            f"<td class='ent'>{html.escape(r['PERIODO'])}</td>"
            f"<td>{_pill(r['PROM'])}</td>"
            f"<td>{r['N']}</td>"
            f"<td><span class='igpr-cell' style='background:{color_por_puntaje(r['PROM'])}'>"
            f"{clasificar_puntaje(r['PROM'])}</span></td>"
            f"</tr>"
        )

    st.markdown(
        f"""
        <h4 style='margin:0.6rem 0 0.4rem;color:{C['azul_oscuro']};font-family:Montserrat,sans-serif'>
        Evolución de {html.escape(sel)}</h4>
        <table class='igpr-matriz' style='margin-bottom:1rem'>
          <thead><tr>
            <th style='text-align:left'>Periodo</th><th>Promedio</th>
            <th>Proyectos</th><th>Categoría</th>
          </tr></thead>
          <tbody>{filas}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

    # Listado completo de proyectos por trimestre
    st.markdown(f"<h4 style='margin:0.8rem 0 0.4rem;color:{C['azul_oscuro']};font-family:Montserrat,sans-serif'>"
                f"Proyectos por trimestre</h4>",
                unsafe_allow_html=True)

    periodos_ord = (
        df_sel.select(["VIGENCIA", "_orden_trim", "TRIMESTRE EVALUADO", "PERIODO"])
              .unique()
              .sort(["VIGENCIA", "_orden_trim"])
    )

    incluir_plazo = "CLASIFICACIÓN PLAZO PARA EJECUCIÓN" in df_sel.columns

    for r in periodos_ord.iter_rows(named=True):
        sub = df_sel.filter(
            (pl.col("VIGENCIA") == r["VIGENCIA"])
            & (pl.col("TRIMESTRE EVALUADO") == r["TRIMESTRE EVALUADO"])
        ).sort("PUNTAJE", descending=True, nulls_last=True)

        with st.expander(f"{r['PERIODO']} · {sub.height} proyecto{'s' if sub.height != 1 else ''}",
                         expanded=False):
            proys_html = ""
            for p in sub.iter_rows(named=True):
                nombre = html.escape(str(p.get("NOMBRE DEL PROYECTO") or "(sin nombre)"))
                bpin = html.escape(str(p.get("BPIN") or "—"))
                punt = p.get("PUNTAJE")
                col = color_por_puntaje(punt)
                pill = f"<span class='pill' style='background:{col}'>{punt:.1f}</span>" if punt is not None \
                    else "<span class='pill' style='background:#94a3b8'>—</span>"
                extra_html = ""
                if incluir_plazo:
                    cls = p.get("CLASIFICACIÓN PLAZO PARA EJECUCIÓN")
                    if cls:
                        extra_html = (
                            f"<div style='font-size:0.7rem;color:{C['muted']};margin-top:0.2rem'>"
                            f"Plazo: <b style='color:{C['text']}'>{html.escape(str(cls))}</b></div>"
                        )
                proys_html += (
                    "<div class='igpr-proy'>"
                    f"<div><div class='nombre'>{nombre}</div>"
                    f"<div class='bpin'>BPIN: {bpin}</div>"
                    f"{extra_html}</div>"
                    f"<div>{pill}</div>"
                    "</div>"
                )
            st.markdown(proys_html, unsafe_allow_html=True)


def _metodologia() -> None:
    """Resumen visual de la Resolución 4574 de 2025."""
    az = C["azul_oscuro"]
    st.markdown(
        f"""
        <h4 style='margin:0.4rem 0 0.4rem;color:{az};font-family:Montserrat,sans-serif'>
        ¿Qué es el IGPR?</h4>
        <div style='font-size:0.86rem;color:{C['text']};line-height:1.55;
                    background:#fff;border:1px solid {C['border']};
                    border-radius:10px;padding:0.9rem 1.1rem;margin-bottom:0.8rem'>
        El <b>Índice de Gestión de Proyectos de Regalías (IGPR)</b> mide la
        eficiencia de las entidades ejecutoras y beneficiarias en la gestión
        de los proyectos financiados con recursos del Sistema General de
        Regalías. Es elaborado por la <b>Subdirección General del SGR</b> del DNP
        y se calcula trimestralmente con corte al último día del mes a reportar.
        Está regulado por la <b>Resolución 4574 del 30 de diciembre de 2025</b>,
        que entró en vigor el 1° de enero de 2026 y deroga la Resolución 0226
        de 2024.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 3 cards lado a lado: Escala, Estados, Periodicidad
    st.markdown(
        f"""
        <div class='igpr-meto-grid'>

          <div class='igpr-meto-card'>
            <div class='lab'>Escala de medición</div>
            <h4>0 a 100 puntos</h4>
            <ul>
              <li><b>≥ 60</b> · ADECUADO (Departamento Sucre, Capacidad 2)</li>
              <li><b>&lt; 60</b> · NO ADECUADO</li>
              <li>Resultado de entidad: promedio simple de los proyectos medidos.</li>
              <li>Proyecto: <code>Eficiencia × Ponderador Reporte Oportuno</code>.</li>
            </ul>
          </div>

          <div class='igpr-meto-card'>
            <div class='lab'>Estados de medición</div>
            <h4>3 estados del proyecto</h4>
            <ul>
              <li><b>SIN CONTRATAR</b> · desde la migración a GESPROY hasta firmar el primer contrato.</li>
              <li><b>EN EJECUCIÓN</b> · desde el primer contrato hasta el cumplimiento de los indicadores de producto.</li>
              <li><b>TERMINADO</b> · cumplido el alcance; pendiente de cierre.</li>
            </ul>
          </div>

          <div class='igpr-meto-card'>
            <div class='lab'>Periodicidad</div>
            <h4>Trimestral + Anual</h4>
            <ul>
              <li>Reporte mensual a GESPROY · vencimiento el día 15 del mes siguiente.</li>
              <li>El no-reporte oportuno aplica como ponderador a la baja.</li>
              <li>Anual: promedio simple de los 4 trimestres medidos.</li>
            </ul>
          </div>

        </div>
        """,
        unsafe_allow_html=True,
    )

    # Tabla de indicadores por estado
    st.markdown(
        f"<h4 style='margin:0.8rem 0 0.4rem;color:{az};font-family:Montserrat,sans-serif'>"
        f"Indicadores y ponderación por estado</h4>",
        unsafe_allow_html=True,
    )

    indicadores = [
        ("SIN CONTRATAR",
         "—",
         "Eficiencia en la contratación", "100%"),
        ("EN EJECUCIÓN",
         "Con avance físico o financiero",
         "Desempeño en el cronograma · Desempeño en el costo · Brecha avance físico vs financiero",
         "40% · 20% · 40%"),
        ("EN EJECUCIÓN",
         "Sin avance físico ni financiero",
         "Desempeño en el cronograma", "100%"),
        ("TERMINADO",
         "—",
         "Cumplimiento del alcance", "100%"),
    ]

    filas_ind = ""
    for estado, sub, ind, pond in indicadores:
        filas_ind += (
            "<tr>"
            f"<td><b>{estado}</b><div style='font-size:0.72rem;color:{C['muted']}'>{sub}</div></td>"
            f"<td>{ind}</td>"
            f"<td class='pond'>{pond}</td>"
            "</tr>"
        )

    st.markdown(
        f"""
        <table class='igpr-meto-table' style='margin-bottom:1rem'>
          <thead><tr>
            <th>Estado</th><th>Indicador(es)</th>
            <th style='text-align:center'>Ponderación</th>
          </tr></thead>
          <tbody>{filas_ind}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <h4 style='margin:0.8rem 0 0.4rem;color:{az};font-family:Montserrat,sans-serif'>
        Factores que pueden afectar el puntaje</h4>
        <div class='igpr-meto-grid'>

          <div class='igpr-meto-card'>
            <div class='lab'>Descuentos</div>
            <h4>−5 puntos por situación</h4>
            <ul>
              <li>Inconsistencias detectadas en visita de campo.</li>
              <li>Posibles irregularidades graves.</li>
              <li>Modificaciones excesivas al reporte de ejecución.</li>
            </ul>
            <div style='font-size:0.72rem;color:{C['muted']};margin-top:0.5rem'>
              Tope máximo: −10 puntos por entidad y trimestre.
            </div>
          </div>

          <div class='igpr-meto-card'>
            <div class='lab'>Bonificación anual</div>
            <h4>+5 puntos</h4>
            <ul>
              <li>Incremento ≥ 20 puntos frente a la anualidad anterior.</li>
              <li>Si el puntaje resultante supera 95, se ajusta a 100.</li>
            </ul>
          </div>

          <div class='igpr-meto-card'>
            <div class='lab'>Reporte oportuno</div>
            <h4>Ponderador multiplicativo</h4>
            <ul>
              <li>Reporta a tiempo todos los meses obligados → ponderador 100%.</li>
              <li>Reporta tarde uno o más → penaliza progresivamente.</li>
              <li>No reporta ningún mes → ponderador 0%.</li>
            </ul>
          </div>

        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def render_igpr(matriz_bytes: bytes | None) -> None:
    """Pinta toda la vista IGPR. Recibe los bytes de la Matriz de Seguimiento
    para poder construir el catálogo BPIN → ENTIDAD (igual que el notebook)."""
    st.markdown(_CSS_IGPR, unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class='page-header' style='margin-bottom:0.4rem'>
          <div>
            <h1>Índice de Gestión de Proyectos de Regalías</h1>
            <p>Resultado del IGPR — Departamento de Sucre · Resolución 4574 de 2025</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not matriz_bytes:
        st.markdown(
            "<div class='igpr-empty'>No se pudo acceder a la Matriz de Seguimiento "
            "(necesaria para vincular BPIN → entidad). Verifica la fuente de datos en el sidebar.</div>",
            unsafe_allow_html=True,
        )
        return

    with st.spinner("Descargando resultados IGPR (5 trimestres)…"):
        df = cargar_igpr(matriz_bytes)

    if df.is_empty():
        st.markdown(
            "<div class='igpr-empty'>No se pudieron descargar los archivos del IGPR. "
            "Comprueba la conexión y vuelve a intentarlo desde el botón "
            "<b>Recargar datos del repositorio</b> en la barra lateral.</div>",
            unsafe_allow_html=True,
        )
        return

    # Tabs
    tabs = st.tabs([
        "Resumen general",
        "Detalle por trimestre",
        "Detalle por entidad",
        "Metodologia",
    ])

    with tabs[0]:
        _resumen_general(df)

    with tabs[1]:
        _detalle_trimestre(df)

    with tabs[2]:
        _detalle_entidad(df)

    with tabs[3]:
        _metodologia()
