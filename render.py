"""
render.py
Funciones de renderizado HTML y helpers de presentación visual.
Incluye: badge_html, _pill, _fmt_date, _dias_tooltip, eval_color,
         _clasificar_promedio, _contratos_panel, _calcular_clasi_modal,
         constantes de color de estado.
"""
from constants import C, INTERVALOS, SEMAFOROS
import streamlit as st
import polars as pl
import html
import logging

_log = logging.getLogger(__name__)


# ── Mapa color → clase CSS por hito (evita colisiones entre hitos con mismas claves) ──
_BADGE_BY_HITO = {
    "hito_1_val": {
        "0-100":   "badge-green",
        "101-150": "badge-yellow",
        "151-180": "badge-orange",
        ">180":    "badge-black",
    },
    "hito_2_val": {
        "0-100":   "badge-green",
        "101-150": "badge-yellow",
        "151-180": "badge-orange",
        ">180":    "badge-black",
    },
    # ── Hito 3 actualizado ──
    "hito_3_val": {
        "0-15":  "badge-green",
        "16-30": "badge-yellow",
        "31-45": "badge-orange",
        ">45":   "badge-black",
    },
    "hito_4_val": {
        "0-1":   "badge-green",
        "1.1-3": "badge-yellow",
        "3.1-6": "badge-orange",
        ">6":    "badge-black",
    },
    "hito_5_val": {
        "0-100":   "badge-green",
        "101-150": "badge-yellow",
        "151-180": "badge-orange",
        ">180":    "badge-black",
    },
}

# Mapa plano de clasi → clase badge (usado donde no se conoce el hito)
_BADGE_PLANO = {
    "0-100":   "badge-green",  "0-30":  "badge-green",  "0-1":   "badge-green",  "0-15":  "badge-green",
    "101-150": "badge-yellow", "31-45": "badge-yellow", "1.1-3": "badge-yellow", "16-30": "badge-yellow",
    "151-180": "badge-orange", "46-60": "badge-orange", "3.1-6": "badge-orange",
    ">180":    "badge-black",  ">60":   "badge-black",  ">6":    "badge-black",  ">45":   "badge-black",
}

# Mapa plano de badge-class → row-class
_ROW_CLS_MAP = {
    "badge-green":  "row-green",
    "badge-yellow": "row-yellow",
    "badge-orange": "row-orange",
    "badge-black":  "row-black",
}


def badge_html(val, hito_key=None):
    """Genera badge con punto de color semáforo y tooltip con mensaje."""
    if val is None:
        return ""
    val_str = str(val)
    # Buscar clase por hito primero, caer al mapa plano si no hay hito
    if hito_key and hito_key in _BADGE_BY_HITO:
        cls = _BADGE_BY_HITO[hito_key].get(val_str, "badge-yellow")
    else:
        cls = _BADGE_PLANO.get(val_str, "badge-yellow")

    tooltip_html = ""
    if hito_key and hito_key in SEMAFOROS and val_str in SEMAFOROS[hito_key]:
        _, color_nombre, mensaje = SEMAFOROS[hito_key][val_str]
        tooltip_html = (
            f'<span class="badge-tooltip">'
            f'<strong style="color:#47b1d5;display:block;margin-bottom:3px">● {color_nombre}</strong>'
            f'{mensaje}'
            f'</span>'
        )

    return (
        f'<span class="badge {cls}">'
        f'<span class="badge-dot"></span>'
        f'{val_str}'
        f'{tooltip_html}'
        f'</span>'
    )


def badge_cls_from_hito(clasi_val, hito_col):
    """Devuelve la clase CSS del badge dado un valor de clasificación y la columna de hito."""
    if not clasi_val:
        return ""
    return _BADGE_BY_HITO.get(hito_col, _BADGE_PLANO).get(str(clasi_val), "badge-yellow")


def row_cls_from_badge(badge_cls_str):
    """Devuelve la clase CSS de fila a partir de la clase del badge."""
    return _ROW_CLS_MAP.get(badge_cls_str, "")


def _calcular_clasi_modal(df: pl.DataFrame, cols: list) -> dict:
    result: dict = {}
    for col in cols:
        modal = (
            df.filter(pl.col(col).is_not_null())
            .group_by(["ENTIDAD O SECRETARIA", col])
            .agg(pl.len().alias("_n"))
            .sort(["ENTIDAD O SECRETARIA", "_n"], descending=[False, True])
            .group_by("ENTIDAD O SECRETARIA")
            .first()
            .select(["ENTIDAD O SECRETARIA", col])
        )
        for row in modal.to_dicts():
            ent = row["ENTIDAD O SECRETARIA"]
            if ent not in result:
                result[ent] = {c: None for c in cols}
            result[ent][col] = row[col]
    return result


ESTADO_PROY_COLORS = {
    "SIN CONTRATAR":                 (C["cian"],        "#e0f7fa"),
    "CONTRATADO EN EJECUCIÓN":       (C["verde_medio"], "#d1fae5"),
    "CONTRATADO SIN ACTA DE INICIO": (C["azul_medio"],  "#dbeafe"),
    "TERMINADO":                     (C["muted"],       "#f1f5f9"),
    "PARA CIERRE":                   (C["cafe"],        "#fef3c7"),
}
ESTADO_CONT_COLORS = {
    "EN EJECUCIÓN":  (C["verde_medio"], "#d1fae5"),
    "TERMINADO":     (C["muted"],       "#f1f5f9"),
    "LIQUIDADO":     (C["azul_medio"],  "#dbeafe"),
    "SUSPENDIDO":    (C["naranja_osc"], "#ffedd5"),
    "SIN CONTRATO":  (C["cian"],        "#e0f7fa"),
}
CTTO_ESTADO_COLORS = {
    "EN EJECUCIÓN":  (C["verde_medio"],  "#d1fae5"),
    "EJECUTADO":     (C["verde_oscuro"], "#d1fae5"),
    "TERMINADO":     (C["muted"],        "#f1f5f9"),
    "LIQUIDADO":     (C["azul_medio"],   "#dbeafe"),
    "SUSPENDIDO":    (C["naranja_osc"],  "#ffedd5"),
    "RESCINDIDO":    (C["salmon"],       "#fee2e2"),
    "SUSCRITO":      (C["cian"],         "#e0f7fa"),
}


def _pill(texto, color_map, default_fg=None, default_bg=None):
    if not texto:
        return '<span class="proy-pill proy-pill--empty">—</span>'
    eu = texto.strip().upper()
    fg, bg = color_map.get(eu, (default_fg or C["muted"], default_bg or "#f1f5f9"))
    extra = "font-weight:700;" if eu == "SUSPENDIDO" else ""
    return (
        f'<span class="proy-pill" '
        f'style="background:{bg};color:{fg};border:1px solid {fg}40;{extra}">'
        f'{html.escape(texto)}</span>'
    )


def _fmt_valor(v):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    try:
        return f"$ {v:,.0f}"
    except Exception:
        return str(v)


def _valor_a_gradiente(valor, v_min, v_max):
    if valor is None or v_max == v_min:
        return "#ffffff"
    ratio = max(0.0, min(1.0, (valor - v_min) / (v_max - v_min)))
    r = int(255 - ratio * (255 - 219))
    g = int(255 - ratio * (255 - 234))
    b = int(255 - ratio * (255 - 254))
    return f"rgb({r},{g},{b})"


def _contratos_panel(bpin_str, df_cttos):
    if df_cttos is None:
        return '<div class="ctto-panel"><div class="ctto-panel-empty">Archivo de contratos no disponible.</div></div>'

    bpin_norm = (
        str(bpin_str).strip()
        .replace(".", "").replace("-", "").replace(",", "").replace(" ", "")
    )
    cttos = df_cttos.filter(pl.col("BPIN") == bpin_norm)

    if cttos.height == 0:
        return '<div class="ctto-panel"><div class="ctto-panel-empty">Sin contratos registrados para este proyecto.</div></div>'

    valores     = [r.get("CONTRATO VALOR TOTAL") for r in cttos.to_dicts()]
    valores_num = [v for v in valores if v is not None and isinstance(v, float) and v == v]
    v_min = min(valores_num) if valores_num else 0
    v_max = max(valores_num) if valores_num else 0

    n      = cttos.height
    header = f"""
    <div class="ctto-panel-header">
        <span class="ctto-panel-title">Contratos</span>
        <span class="ctto-panel-count">{n}</span>
    </div>"""

    rows_list = []
    for ctto in cttos.to_dicts():
        valor    = ctto.get("CONTRATO VALOR TOTAL")
        bg_grad  = _valor_a_gradiente(valor, v_min, v_max)
        estado_c = (ctto.get("ESTADO CONTRATO") or "").strip().upper()
        fg_e, bg_e = CTTO_ESTADO_COLORS.get(estado_c, (C["muted"], "#f1f5f9"))
        proceso   = html.escape(ctto.get("NO. PROCESO PRECONTRACTUAL") or "—")
        modalidad = html.escape(ctto.get("MODALIDAD CONTRATACION") or "—")
        tipo      = html.escape(ctto.get("TIPO CONTRATO") or "—")
        objeto    = html.escape(ctto.get("CONTRATO OBJETO") or "—")

        bar_px = 0
        if valor and v_max > v_min:
            bar_px = int(max(6, min(60, (valor - v_min) / (v_max - v_min) * 60)))
        elif valor:
            bar_px = 60

        rows_list.append(f"""<tr style="background:{bg_grad}">
            <td class="ctto-col1"><span class="ctto-proceso">{proceso}</span></td>
            <td style="font-size:0.73rem;color:{C['text']}">{modalidad}</td>
            <td style="font-size:0.73rem;color:{C['muted']}">{tipo}</td>
            <td>
                <div class="ctto-valor-wrap">
                    <span class="ctto-valor">{_fmt_valor(valor)}</span>
                    <div class="ctto-valor-bar" style="width:{bar_px}px"></div>
                </div>
            </td>
            <td><span class="ctto-estado-pill" style="background:{bg_e};color:{fg_e};border:1px solid {fg_e}40">{html.escape(ctto.get("ESTADO CONTRATO") or "—")}</span></td>
            <td><div class="ctto-objeto">{objeto}</div></td>
        </tr>""")

    rows  = "".join(rows_list)
    tabla = f"""
    <div style="border-radius:10px;overflow:hidden;box-shadow:0 1px 10px rgba(0,40,90,0.10);">
    <table class="ctto-table">
    <thead><tr>
        <th class="ctto-col1">No. proceso</th>
        <th>Modalidad</th><th>Tipo</th>
        <th>Valor total</th><th>Estado</th>
        <th>Objeto del contrato</th>
    </tr></thead>
    <tbody>{rows}</tbody>
    </table></div>"""
    return f'<div class="ctto-panel">{header}{tabla}</div>'


def _fmt_date(val):
    if val is None:
        return "—"
    try:
        return val.strftime("%d/%m/%Y")
    except Exception:
        return str(val)


HITO_CALC_META = {
    "hito_1_val": (
        "Fecha aprobación",    "FECHA APROBACIÓN PROYECTO",
        "Fecha corte GESPROY", "FECHA DE CORTE GESPROY",
        "Días desde la aprobación del proyecto hasta el corte, sin proceso de contratación abierto.",
    ),
    "hito_2_val": (
        "Fecha apertura proceso", "FECHA DE APERTURA DEL PRIMER PROCESO",
        "Fecha acta de inicio",   "FECHA ACTA INICIO",
        "Días desde la apertura del primer proceso hasta el acta de inicio.",
    ),
    "hito_3_val": (
        "Fecha suscripción",   "FECHA SUSCRIPCION",
        "Fecha corte GESPROY", "FECHA DE CORTE GESPROY",
        "Días desde la suscripción del contrato hasta el corte, sin acta de inicio.",
    ),
    "hito_4_val": (
        "Horizonte del proyecto", "HORIZONTE DEL PROYECTO",
        "Fecha corte GESPROY",    "FECHA DE CORTE GESPROY",
        "Días de retraso sobre el horizonte (CPI=0, SPI=0). El resultado se muestra en meses.",
    ),
    "hito_5_val": (
        "Fecha finalización",  "FECHA DE FINALIZACIÓN",
        "Fecha corte GESPROY", "FECHA DE CORTE GESPROY",
        "Días entre la fecha de finalización registrada y el corte.",
    ),
}


def _dias_tooltip(r, hito_col):
    meta = HITO_CALC_META.get(hito_col)
    if not meta:
        return ""
    lbl_a, col_a, lbl_b, col_b, nota = meta
    fecha_a = _fmt_date(r.get(col_a))
    fecha_b = _fmt_date(r.get(col_b))
    dias_v  = r.get(hito_col)
    dias_display = f"{dias_v:.0f} días" if dias_v is not None else "—"
    es_h4 = hito_col == "hito_4_val"
    resultado_label = f"{dias_v/30:.1f} meses ({dias_display})" if es_h4 and dias_v else dias_display
    return (
        f'<div class="dias-tip-box">'
        f'  <div class="dias-tip-title">Cálculo del hito</div>'
        f'  <div class="dias-tip-row"><span class="dias-tip-lbl">{lbl_b}</span>'
        f'    <span class="dias-tip-val">{fecha_b}</span></div>'
        f'  <div class="dias-tip-op">menos (−)</div>'
        f'  <div class="dias-tip-row"><span class="dias-tip-lbl">{lbl_a}</span>'
        f'    <span class="dias-tip-val">{fecha_a}</span></div>'
        f'  <div class="dias-tip-sep"></div>'
        f'  <div class="dias-tip-result">= &nbsp;{resultado_label}</div>'
        f'  <div class="dias-tip-nota">{nota}</div>'
        f'</div>'
    )


def eval_color(score, max_score=100.0):
    ratio = score / max_score if max_score > 0 else 0
    if ratio >= 0.8:   return C["verde_medio"],  "Sobresaliente"
    elif ratio >= 0.6: return C["cian"],         "Satisfactorio"
    elif ratio >= 0.4: return C["naranja"],      "Aceptable"
    else:              return C["salmon"],        "Por mejorar"


HITO_KEY_MAP = {
    "clasi_1": "hito_1_val",
    "clasi_2": "hito_2_val",
    "clasi_3": "hito_3_val",
    "clasi_4": "hito_4_val",
    "clasi_5": "hito_5_val",
}
CLASI_TO_HITO = {
    "clasi_1": "hito_1_val",
    "clasi_2": "hito_2_val",
    "clasi_3": "hito_3_val",
    "clasi_4": "hito_4_val",
    "clasi_5": "hito_5_val",
}


def _clasificar_promedio(dias_val, clasi_key):
    """Clasifica el promedio de días según los intervalos del hito."""
    if dias_val is None or (isinstance(dias_val, float) and dias_val != dias_val):
        return None
    hito_col = CLASI_TO_HITO.get(clasi_key)
    if hito_col == "hito_4_val":
        meses = dias_val / 30.0
        if   meses <= 1: return "0-1"
        elif meses <= 3: return "1.1-3"
        elif meses <= 6: return "3.1-6"
        else:            return ">6"
    else:
        intervalos = INTERVALOS.get(hito_col, [])
        for label, lo, hi in intervalos:
            if hi is None and dias_val >= lo:           return label
            if hi is not None and lo <= dias_val <= hi: return label
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Tooltip contextual de estado de proyecto
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_date_short(d):
    if d is None:
        return "—"
    try:
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(d)


def _alerta_nombre(clasi):
    mapa = {
        "0-100": "Verde", "0-30": "Verde", "0-1": "Verde", "0-15": "Verde",
        "101-150": "Naranja", "31-45": "Naranja", "1.1-3": "Naranja", "16-30": "Naranja",
        "151-180": "Rojo", "46-60": "Rojo", "3.1-6": "Rojo",
        ">180": "Negra", ">60": "Negra", ">6": "Negra", ">45": "Negra",
    }
    return mapa.get(str(clasi), str(clasi)) if clasi else "Sin alerta"


def _horizonte_str(row_data):
    h = row_data.get("HORIZONTE DEL PROYECTO")
    c = row_data.get("FECHA DE CORTE GESPROY")
    if h is None:
        return "sin horizonte registrado"
    lbl = _fmt_date_short(h)
    if c is not None and h <= c:
        return f"vencido desde {lbl}"
    return f"vigente hasta {lbl}"


def _comentario_contextual(eu, row_data):
    """Devuelve solo el texto de situación actual, sin título de sección (lo pone tooltip_body)."""
    if row_data is None:
        return ""

    if eu == "SIN CONTRATAR":
        tiene_apertura = row_data.get("FECHA DE APERTURA DEL PRIMER PROCESO") is not None
        if tiene_apertura:
            dias   = row_data.get("hito_2_val")
            alerta = _alerta_nombre(row_data.get("clasi_2"))
            if dias is not None:
                txt = (
                    f"Lleva <strong>{int(dias)} días</strong> desde el inicio del primer "
                    f"proceso precontractual, en espera de la suscripción del contrato. "
                    f"Se encuentra en alerta <strong>{alerta}</strong>."
                )
            else:
                txt = "Tiene proceso precontractual abierto, pero aún no cuenta con contrato suscrito."
        else:
            dias   = row_data.get("hito_1_val")
            alerta = _alerta_nombre(row_data.get("clasi_1"))
            if dias is not None:
                txt = (
                    f"Lleva <strong>{int(dias)} días</strong> desde su aprobación "
                    f"sin registro de proceso precontractual. "
                    f"Se encuentra en alerta <strong>{alerta}</strong>."
                )
            else:
                txt = "No registra proceso precontractual ni contrato. Requiere seguimiento inmediato."
        return f'<div class="etip-row">{txt}</div>'

    elif eu == "CONTRATADO SIN ACTA DE INICIO":
        dias   = row_data.get("hito_3_val")
        alerta = _alerta_nombre(row_data.get("clasi_3"))
        if dias is not None:
            txt = (
                f"Presenta <strong>{int(dias)} días</strong> desde la suscripción "
                f"del contrato sin que se haya formalizado el acta de inicio. "
                f"Se encuentra en alerta <strong>{alerta}</strong>. "
                f"Requiere contar con la programación inicial registrada en GESPROY."
            )
        else:
            txt = "El contrato está suscrito, pero no se ha registrado el acta de inicio ni la programación inicial."
        return f'<div class="etip-row">{txt}</div>'

    elif eu == "CONTRATADO EN EJECUCIÓN":
        cpi       = row_data.get("CPI")
        spi       = row_data.get("SPI")
        h_str     = _horizonte_str(row_data)
        dias_h4   = row_data.get("hito_4_val")
        alerta_h4 = _alerta_nombre(row_data.get("clasi_4"))
        partes    = []
        if cpi is not None or spi is not None:
            try:
                cpi_v = float(cpi) if cpi is not None else None
                spi_v = float(spi) if spi is not None else None
                ind_txt = []
                if cpi_v is not None: ind_txt.append(f"CPI: <strong>{cpi_v:.2f}</strong>")
                if spi_v is not None: ind_txt.append(f"SPI: <strong>{spi_v:.2f}</strong>")
                partes.append(f"Indicadores — {', '.join(ind_txt)}.")
            except Exception:
                pass
        partes.append(f"Horizonte <strong>{h_str}</strong>.")
        if dias_h4 is not None and dias_h4 > 0:
            partes.append(
                f"<strong>{int(dias_h4)} días</strong> ({int(dias_h4)//30} meses) "
                f"con horizonte vencido. Alerta: <strong>{alerta_h4}</strong>."
            )
        txt = " ".join(partes) if partes else "Proyecto en ejecución activa."
        return f'<div class="etip-row">{txt}</div>'

    elif eu == "TERMINADO":
        dias      = row_data.get("hito_5_val")
        alerta    = _alerta_nombre(row_data.get("clasi_5"))
        fecha_fin = _fmt_date_short(row_data.get("FECHA DE FINALIZACIÓN"))
        if dias is not None:
            txt = (
                f"Finalizado desde el <strong>{fecha_fin}</strong>. "
                f"<strong>{int(dias)} días</strong> transcurridos sin pasar a 'Para cierre'. "
                f"Alerta <strong>{alerta}</strong>. En espera de liquidación de contratos."
            )
        else:
            txt = "Proyecto finalizado. En espera de la liquidación de contratos para proceder con el cierre."
        return f'<div class="etip-row">{txt}</div>'

    elif eu == "PARA CIERRE":
        txt = (
            "El proyecto está liquidado y finalizado. En proceso de elaboración "
            "del acto administrativo para formalizar su cierre ante el DNP y el SGR."
        )
        return f'<div class="etip-row">{txt}</div>'

    return ""


def _estado_tooltip_html(est_proy, row_data=None):
    """
    Genera un pill de estado con tooltip contextual en una sola columna.
    El posicionamiento dinámico (izq/der, arriba/abajo) lo hace el JS en constants.py.
    """
    if not est_proy:
        return '<span class="proy-pill proy-pill--empty">—</span>'

    eu = est_proy.strip().upper()
    fg, bg = ESTADO_PROY_COLORS.get(eu, (C["muted"], "#f1f5f9"))

    INFO = {
        "SIN CONTRATAR": {
            "descripcion": (
                "Este estado indica que el proyecto migró a GESPROY pero no cuenta "
                "con su primer proceso precontractual ni con contrato suscrito. "
                "No se ha adelantado ningún tipo de contratación."
            ),
            "estado_anterior": "Ninguno — es el estado inicial del proyecto en GESPROY.",
            "fecha_entrada": (
                "Fecha de aprobación del proyecto. "
                "A partir de esta fecha se calcula el Hito 1 (días sin contratar)."
            ),
            "para_avanzar": "Registrar la fecha de suscripción del primer contrato en GESPROY.",
            "fecha_avance": "Al registrar la suscripción, GESPROY actualiza el estado automáticamente.",
            "requisitos": (
                "No exige requisitos formales para estar en este estado, pero es fundamental "
                "hacer seguimiento riguroso a los tiempos de contratación definidos por el DNP."
            ),
        },
        "CONTRATADO SIN ACTA DE INICIO": {
            "descripcion": (
                "El primer contrato del proyecto ha sido suscrito, pero aún no se ha "
                "dado inicio a la ejecución. Sin el acta de inicio, el contrato no "
                "puede comenzar actividades formalmente."
            ),
            "estado_anterior": "Sin contratar.",
            "fecha_entrada": (
                "Fecha de suscripción del primer contrato. "
                "A partir de aquí se calcula el Hito 3 (días sin acta de inicio)."
            ),
            "para_avanzar": "Registrar la fecha del acta de inicio en GESPROY.",
            "fecha_avance": "GESPROY actualiza el estado automáticamente al registrar el acta.",
            "requisitos": (
                "Contar con la programación inicial y el acta de inicio firmada "
                "por el contratista y la interventoría."
            ),
        },
        "CONTRATADO EN EJECUCIÓN": {
            "descripcion": (
                "El proyecto inició su ejecución. Se miden indicadores de avance "
                "(CPI para costos, SPI para tiempo) y se controla que el horizonte "
                "de ejecución no esté vencido."
            ),
            "estado_anterior": "Contratado sin acta de inicio.",
            "fecha_entrada": (
                "Fecha de acta de inicio. "
                "A partir de aquí se activa el Hito 4 si el horizonte vence "
                "con CPI=0 y SPI=0."
            ),
            "para_avanzar": "Cumplir las metas e indicadores y remitir las actas finales de contratos.",
            "fecha_avance": "No hay fecha automática. El cambio a Terminado se registra manualmente en GESPROY.",
            "requisitos": (
                "El proyecto debe haber finalizado y las entidades sectoriales deben "
                "haber remitido las actas finales como soporte."
            ),
        },
        "TERMINADO": {
            "descripcion": (
                "El proyecto ha cumplido sus metas e indicadores y fue declarado "
                "finalizado. Pueden quedar contratos pendientes de liquidación."
            ),
            "estado_anterior": "Contratado en ejecución.",
            "fecha_entrada": (
                "No hay fecha automática. El cambio se realiza de forma manual "
                "en GESPROY. El Hito 5 mide los días desde la finalización."
            ),
            "para_avanzar": "Liquidar todos los contratos, completar pagos y expedir el acto administrativo de cierre.",
            "fecha_avance": "No hay fecha automática. El paso a Para cierre requiere gestión manual.",
            "requisitos": (
                "Todos los contratos finalizados con sus actas y el proyecto con "
                "metas cumplidas. El acto de cierre es obligatorio para avanzar."
            ),
        },
        "PARA CIERRE": {
            "descripcion": (
                "El proyecto está liquidado y finalizado. Solo falta el acto "
                "administrativo que formaliza su cierre oficial. "
                "Es el último estado del ciclo."
            ),
            "estado_anterior": "Terminado.",
            "fecha_entrada": "No hay fecha automática. Es un registro manual en GESPROY.",
            "para_avanzar": "Expedir el acto administrativo de cierre.",
            "fecha_avance": "No hay estado siguiente. Este es el estado final del proyecto.",
            "requisitos": (
                "Todos los contratos terminados y liquidados, pagos completos "
                "y acto administrativo de cierre expedido por la entidad competente."
            ),
        },
        "SUSPENDIDO": {
            "descripcion": (
                "El proyecto o sus contratos fueron suspendidos temporalmente. "
                "La ejecución y los desembolsos están detenidos."
            ),
            "estado_anterior": "Cualquier estado activo (varía según el momento de la suspensión).",
            "fecha_entrada": "Fecha del acto administrativo de suspensión.",
            "para_avanzar": "Resolver la causal de suspensión y expedir acto de reactivación.",
            "fecha_avance": "Al levantar la suspensión, el proyecto retoma el estado anterior.",
            "requisitos": (
                "Acto administrativo de reactivación firmado. "
                "Revisar si los plazos contractuales deben ajustarse por el tiempo suspendido."
            ),
        },
    }

    info = INFO.get(eu)
    if not info:
        extra = "font-weight:700;" if eu == "SUSPENDIDO" else ""
        return (
            f'<span class="proy-pill" '
            f'style="background:{bg};color:{fg};border:1px solid {fg}40;{extra}">'
            f'{html.escape(est_proy)}</span>'
        )

    # ── Situación actual con datos reales ────────────────────────────────────
    situacion_html = _comentario_contextual(eu, row_data)

    # ── Fechas registradas ────────────────────────────────────────────────────
    fechas_html_rows = ""
    if row_data:
        campos = [
            ("FECHA APROBACIÓN PROYECTO",            "Aprobación"),
            ("FECHA DE APERTURA DEL PRIMER PROCESO", "Apertura proceso"),
            ("FECHA SUSCRIPCION",                    "Suscripción"),
            ("FECHA ACTA INICIO",                    "Acta de inicio"),
            ("HORIZONTE DEL PROYECTO",               "Horizonte"),
            ("FECHA DE FINALIZACIÓN",                "Finalización"),
            ("FECHA DE CORTE GESPROY",               "Corte GESPROY"),
        ]
        filas = []
        for col, lbl in campos:
            v = row_data.get(col)
            if v is not None:
                filas.append(
                    f'<div class="etip-fecha-row">'
                    f'<span class="etip-fecha-lbl">{lbl}</span>'
                    f'<span class="etip-fecha-val">{_fmt_date_short(v)}</span>'
                    f'</div>'
                )
        fechas_html_rows = "".join(filas)

    # ── Tooltip: una sola columna, secciones con separadores ─────────────────
    tooltip_body = (
        f'<span class="etip-estado">{html.escape(est_proy)}</span>'
        f'<p class="etip-desc">{html.escape(info["descripcion"])}</p>'

        f'<hr class="etip-sep">'
        f'<div class="etip-section-title">Situación actual</div>'
        + (situacion_html if situacion_html else f'<div class="etip-row etip-small">Sin datos disponibles.</div>')

        + f'<hr class="etip-sep">'
        f'<div class="etip-section-title">Origen del estado</div>'
        f'<div class="etip-row"><span class="etip-label">Estado anterior: </span>{html.escape(info["estado_anterior"])}</div>'
        f'<div class="etip-row etip-small"><span class="etip-label">Fecha de entrada: </span>{html.escape(info["fecha_entrada"])}</div>'

        + (f'<hr class="etip-sep">'
           f'<div class="etip-section-title">Fechas en GESPROY</div>'
           f'<div class="etip-fechas">{fechas_html_rows}</div>'
           if fechas_html_rows else '')

        + f'<hr class="etip-sep">'
        f'<div class="etip-section-title">Para avanzar</div>'
        f'<div class="etip-row">{html.escape(info["para_avanzar"])}</div>'
        f'<div class="etip-small">{html.escape(info["fecha_avance"])}</div>'

        + f'<hr class="etip-sep">'
        f'<div class="etip-accion">'
        f'<span class="etip-accion-label">Acción sugerida</span>'
        f'{html.escape(info["requisitos"])}'
        f'</div>'
    )

    extra_style = "font-weight:700;" if eu == "SUSPENDIDO" else ""
    # IMPORTANTE: usar <div> para el trigger y popup, NO <span>.
    # Un <span> (inline) no puede contener <div>, <p>, <hr> — el browser
    # los expulsa fuera del contenedor causando el desborde visual.
    # El pill sigue viéndose igual; solo cambia el elemento contenedor.
    return (
        f'<div class="proy-pill etip-trigger" '
        f'style="display:inline-block;background:{bg};color:{fg};border:1px solid {fg}40;{extra_style}cursor:pointer">'
        f'{html.escape(est_proy)}&thinsp;<span class="etip-i">&#9432;</span>'
        f'<div class="etip-popup">{tooltip_body}</div>'
        f'</div>'
    )
