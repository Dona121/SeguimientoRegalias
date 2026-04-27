"""
data.py
Carga, validación y procesamiento de datos desde Excel y GitHub.
Incluye: clasificar*, procesar*, _cargar_desde_github, procesar_contratos,
         validar_archivo, th, error_card.
"""
from constants import (
    TABLA_ESPERADA, TABLA_DESCENTRALIZADAS, COLS_EVAL, COLS_EVAL_LABELS,
    INTERVALOS, COLUMNAS_ESPERADAS, TIPO_LABEL, TIPO_EJEMPLO, C,
)
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


def clasificar_hito4_meses(col):
    """Hito 4 se clasifica en meses (días / 30), no en días directos."""
    meses = pl.col(col) / 30.0
    return (
        pl.when(pl.col(col).is_null()).then(None)
        .when(meses <= 1).then(pl.lit("0-1"))
        .when(meses <= 3).then(pl.lit("1.1-3"))
        .when(meses <= 6).then(pl.lit("3.1-6"))
        .otherwise(pl.lit(">6"))
    )

def clasificar(col, intervalos):
    expr = pl.when(pl.col(col).is_null()).then(None)
    for label, lo, hi in intervalos:
        cond = (pl.col(col) >= lo) & (pl.col(col) <= hi) if hi is not None else (pl.col(col) >= lo)
        expr = expr.when(cond).then(pl.lit(label))
    return expr.otherwise(None)

def procesar(file_bytes):
    df = pl.read_excel(io.BytesIO(file_bytes), table_name=TABLA_ESPERADA)

    DATE_COLS = [
        "FECHA APROBACIÓN PROYECTO", "FECHA DE APERTURA DEL PRIMER PROCESO",
        "FECHA SUSCRIPCION", "FECHA ACTA INICIO", "HORIZONTE DEL PROYECTO",
        "FECHA DE FINALIZACIÓN", "FECHA DE CORTE GESPROY",
    ]

    # Cast robusto: maneja pl.Date nativo, Int32/Int64 (serial Excel = días desde 1899-12-30),
    # y Utf8/String (texto "DD/MM/YYYY" o "YYYY-MM-DD") que puede llegar desde GitHub.
    EXCEL_EPOCH = date(1899, 12, 30)
    cast_exprs = []
    for col in DATE_COLS:
        dtype = df[col].dtype
        if dtype == pl.Date:
            # Ya es fecha nativa — no tocar
            cast_exprs.append(pl.col(col))
        elif dtype in (pl.Datetime,):
            # Datetime → extraer solo la parte de fecha
            cast_exprs.append(pl.col(col).dt.date().alias(col))
        elif dtype in (pl.Int32, pl.Int64, pl.UInt32, pl.UInt16):
            # Serial numérico Excel → días desde 1899-12-30
            cast_exprs.append(
                (pl.lit(EXCEL_EPOCH) + pl.duration(days=pl.col(col).cast(pl.Int64)))
                .cast(pl.Date)
                .alias(col)
            )
        elif dtype in (pl.Utf8, pl.String):
            # Texto — limpiar saltos de línea/tabs/espacios antes de parsear.
            # GESPROY puede exportar celdas con \n o \r dentro del valor de fecha.
            cleaned = (
                pl.col(col)
                .str.replace_all(r"[\n\r\t]", " ")
                .str.strip_chars()
            )
            cast_exprs.append(
                pl.coalesce([
                    cleaned.str.to_date("%d/%m/%Y",           strict=False),
                    cleaned.str.to_date("%Y-%m-%d",           strict=False),
                    cleaned.str.to_date("%m/%d/%Y",           strict=False),
                    cleaned.str.to_date("%d-%m-%Y",           strict=False),
                    # Timestamps con T o espacio (ej: "2026-02-15T00:00:00")
                    cleaned.str.to_datetime("%Y-%m-%dT%H:%M:%S", strict=False).dt.date(),
                    cleaned.str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False).dt.date(),
                    cleaned.str.to_datetime("%d/%m/%Y %H:%M:%S", strict=False).dt.date(),
                ]).alias(col)
            )
        else:
            # Fallback genérico para tipos inesperados
            cast_exprs.append(pl.col(col).cast(pl.Date, strict=False))

    df = (
        df.select(
            "ENTIDAD O SECRETARIA", "BPIN", "NOMBRE PROYECTO",
            "ESTADO PROYECTO", "ESTADO CONTRATO",
            "CPI", "SPI",
            *DATE_COLS,
        )
        .with_columns(cast_exprs)
        .with_columns(
            # Hito 1 — omitir si la fecha de aprobación es posterior a la fecha de corte
            pl.when(
                ((pl.col("ESTADO PROYECTO") == "SIN CONTRATAR") | pl.col("ESTADO PROYECTO").is_null() | (pl.col("ESTADO PROYECTO") == "")) &
                (~pl.col("FECHA APROBACIÓN PROYECTO").is_null()) & (~pl.col("FECHA DE CORTE GESPROY").is_null()) &
                (pl.col("FECHA APROBACIÓN PROYECTO") <= pl.col("FECHA DE CORTE GESPROY"))
            ).then((pl.col("FECHA DE CORTE GESPROY") - pl.col("FECHA APROBACIÓN PROYECTO")).dt.total_days()).otherwise(None).alias("hito_1_val"),
            # Hito 2 — clip(0) previene valores negativos por errores de datos
            # (ej: acta firmada antes de apertura del proceso)
            pl.when(
                ((pl.col("ESTADO PROYECTO") == "SIN CONTRATAR") | pl.col("ESTADO PROYECTO").is_null() | (pl.col("ESTADO PROYECTO") == "")) &
                (~pl.col("FECHA DE APERTURA DEL PRIMER PROCESO").is_null())
            ).then(
                (pl.col("FECHA ACTA INICIO") - pl.col("FECHA DE APERTURA DEL PRIMER PROCESO"))
                .dt.total_days().clip(lower_bound=0)
            ).otherwise(None).alias("hito_2_val"),
            # Hito 3
            pl.when(
                (pl.col("ESTADO PROYECTO") == "CONTRATADO SIN ACTA DE INICIO") &
                (~pl.col("FECHA SUSCRIPCION").is_null())
            ).then((pl.col("FECHA DE CORTE GESPROY") - pl.col("FECHA SUSCRIPCION")).dt.total_days()).otherwise(None).alias("hito_3_val"),
            # Hito 4
            pl.when(
                (pl.col("ESTADO PROYECTO") == "CONTRATADO EN EJECUCIÓN") &
                (pl.col("CPI") == 0) & (pl.col("SPI") == 0) &
                (pl.col("HORIZONTE DEL PROYECTO") <= pl.col("FECHA DE CORTE GESPROY"))
            ).then((pl.col("FECHA DE CORTE GESPROY") - pl.col("HORIZONTE DEL PROYECTO")).dt.total_days()).otherwise(None).alias("hito_4_val"),
            # Hito 5
            pl.when(~pl.col("FECHA DE FINALIZACIÓN").is_null()).then(
                (pl.col("FECHA DE CORTE GESPROY") - pl.col("FECHA DE FINALIZACIÓN")).dt.total_days()
            ).otherwise(None).alias("hito_5_val"),
            # Suspendidos — basado en ESTADO CONTRATO
            pl.when(
                pl.col("ESTADO CONTRATO").str.strip_chars().str.to_uppercase() == "SUSPENDIDO"
            ).then(pl.lit(1)).otherwise(None).alias("Suspendidos"),
            # Para cierre
            pl.when(pl.col("ESTADO PROYECTO") == "PARA CIERRE").then(pl.lit(1)).otherwise(None).alias("Para cierre"),
        )
        .with_columns(
            clasificar("hito_1_val", INTERVALOS["hito_1_val"]).alias("clasi_1"),
            clasificar("hito_2_val", INTERVALOS["hito_2_val"]).alias("clasi_2"),
            clasificar("hito_3_val", INTERVALOS["hito_3_val"]).alias("clasi_3"),
            clasificar_hito4_meses("hito_4_val").alias("clasi_4"),
            clasificar("hito_5_val", INTERVALOS["hito_5_val"]).alias("clasi_5"),
        )
    )
    return df

def _validar_cols_eval(df, cols, col_agrup):
    """
    Intenta castear las columnas de calificación a Float64.
    Retorna (df_casteado, errores) donde errores es lista de dicts con info de cada columna problemática.
    """
    errores = []
    cols_ok  = []
    for c in cols:
        if c not in df.columns:
            continue
        dtype_actual = str(df[c].dtype)
        # Verificar si ya es numérico
        if df[c].dtype in (pl.Float32, pl.Float64, pl.Int32, pl.Int64, pl.Int16, pl.UInt32):
            cols_ok.append(c)
            continue
        # Intentar cast — contar cuántos valores se perderían
        casteada = df[c].cast(pl.Float64, strict=False)
        nulos_antes  = df[c].is_null().sum()
        nulos_despues = casteada.is_null().sum()
        perdidos = int(nulos_despues - nulos_antes)
        if perdidos > 0:
            # Mostrar hasta 3 ejemplos de valores problemáticos
            ejemplos = (
                df.filter(df[c].is_not_null() & casteada.is_null())[c]
                .head(3).to_list()
            )
            errores.append({
                "col":        c,
                "tipo":       dtype_actual,
                "perdidos":   perdidos,
                "total":      df.height,
                "ejemplos":   ejemplos,
            })
        else:
            cols_ok.append(c)

    if cols_ok:
        df = df.with_columns([
            pl.col(c).cast(pl.Float64, strict=False) for c in cols_ok
        ])
    return df, cols_ok, errores


def _render_eval_errors(errores, contexto=""):
    """Muestra tarjetas de error amigables para columnas de calificación no numéricas."""
    tipo_amigable = {
        "string": "texto", "utf8": "texto", "str": "texto",
        "bool": "verdadero/falso", "date": "fecha", "datetime": "fecha",
    }
    st.warning(
        f"⚠️ Algunas calificaciones{' de ' + contexto if contexto else ''} "
        f"tienen datos que no pudieron leerse como números. "
        f"Esas columnas se excluyeron del cálculo.",
        icon=None,
    )
    for e in errores:
        pct = round(e["perdidos"] / e["total"] * 100, 1) if e["total"] else 0
        # Convertir tipo técnico a lenguaje amigable
        tipo_raw = e["tipo"].lower()
        tipo_legible = next((v for k, v in tipo_amigable.items() if k in tipo_raw), "no numérico")
        # Formatear ejemplos
        ejemplos_str = " · ".join([f'<code>{html.escape(str(v))}</code>' for v in e["ejemplos"]])
        st.markdown(f"""
<div class="error-card">
  <div class="error-title">&#9888; Calificación con valores incorrectos</div>
  <div class="error-body">
    La columna <strong>{e['col']}</strong> contiene valores de tipo <strong>{tipo_legible}</strong>
    en lugar de números.<br>
    Se encontraron <strong>{e['perdidos']} registro(s) con problemas</strong>
    de un total de {e['total']} ({pct}%).<br>
    Ejemplos de valores problemáticos encontrados: {ejemplos_str}
  </div>
  <div class="error-fix">
    <strong>Cómo corregirlo en Excel</strong>
    Abre el archivo, busca la columna <strong>{e['col']}</strong> y revisa
    que cada celda contenga únicamente un número (por ejemplo: <code>3.5</code>, <code>4</code> o <code>2.75</code>).
    Reemplaza cualquier texto, guion, «N/A» o celda vacía con el valor numérico correspondiente.
    Guarda el archivo y vuelve a cargarlo aquí.
  </div>
</div>""", unsafe_allow_html=True)


@st.cache_data
def procesar_descentralizadas(file_bytes):
    """Lee la tabla de descentralizadas y calcula promedios de calificación por EJECUTOR.
    Retorna (df_promedio, cols_ok, errores, df_raw)."""
    try:
        df = pl.read_excel(io.BytesIO(file_bytes), table_name=TABLA_DESCENTRALIZADAS)
        cols_disponibles = [c for c in COLS_EVAL if c in df.columns]
        if not cols_disponibles or "EJECUTOR" not in df.columns:
            return None, [], [], None
        df, cols_ok, errores = _validar_cols_eval(df, cols_disponibles, "EJECUTOR")
        if not cols_ok:
            return None, [], errores, None
        agg_exprs = [pl.col(c).mean().round(2).alias(c) for c in cols_ok]
        resultado = df.group_by("EJECUTOR").agg(agg_exprs).sort("EJECUTOR")
        raw_cols = ["EJECUTOR"] + cols_ok
        if "NOMBRE PROYECTO" in df.columns: raw_cols.append("NOMBRE PROYECTO")
        if "BPIN" in df.columns:            raw_cols.append("BPIN")
        df_raw = df.select([c for c in raw_cols if c in df.columns])
        return resultado, cols_ok, errores, df_raw
    except Exception:
        _log.exception("procesar_descentralizadas: error inesperado al procesar tabla Descentralizadas")
        return None, [], [], None


@st.cache_data
def procesar_eval_sucre(file_bytes):
    """Calcula promedios de calificación por ENTIDAD O SECRETARIA (tabla Sucre).
    Retorna (df_promedio, cols_ok, errores, df_raw) — df_raw tiene filas individuales."""
    try:
        df = pl.read_excel(io.BytesIO(file_bytes), table_name=TABLA_ESPERADA)
        cols_disponibles = [c for c in COLS_EVAL if c in df.columns]
        if not cols_disponibles or "ENTIDAD O SECRETARIA" not in df.columns:
            return None, [], [], None
        df, cols_ok, errores = _validar_cols_eval(df, cols_disponibles, "ENTIDAD O SECRETARIA")
        if not cols_ok:
            return None, [], errores, None
        agg_exprs = [pl.col(c).mean().round(2).alias(c) for c in cols_ok]
        resultado = df.group_by("ENTIDAD O SECRETARIA").agg(agg_exprs).sort("ENTIDAD O SECRETARIA")
        # Incluir NOMBRE PROYECTO y BPIN si existen para los comentarios
        raw_cols = ["ENTIDAD O SECRETARIA"] + cols_ok
        if "NOMBRE PROYECTO" in df.columns: raw_cols.append("NOMBRE PROYECTO")
        if "BPIN" in df.columns:            raw_cols.append("BPIN")
        df_raw = df.select([c for c in raw_cols if c in df.columns])
        return resultado, cols_ok, errores, df_raw
    except Exception:
        _log.exception("procesar_eval_sucre: error inesperado al procesar tabla Sucre")
        return None, [], [], None

def th(label, titulo, desc):
    return f"""<th><div class="th-wrap">{label}<span class="th-icon">?</span>
    <div class="th-tooltip"><strong>{titulo}</strong>{desc}</div></div></th>"""

# ─────────────────────────────────────────────────────────────────────────────
# VALIDACIÓN
# ─────────────────────────────────────────────────────────────────────────────

def error_card(titulo, cuerpo, solucion):
    return f"""
    <div class="error-card">
        <div class="error-title">&#9888; {titulo}</div>
        <div class="error-body">{cuerpo}</div>
        <div class="error-fix"><strong>Cómo solucionarlo</strong>{solucion}</div>
    </div>"""

def _tipo_amigable(dtype_str):
    """Convierte tipo técnico de Polars a nombre comprensible."""
    d = dtype_str.lower()
    if "utf" in d or "str" in d or "cat" in d: return "Texto"
    if "float" in d or "int" in d:             return "Número"
    if "date" in d or "time" in d:             return "Fecha"
    if "bool" in d:                            return "Verdadero/Falso"
    return dtype_str

def validar_archivo(file_bytes):
    """Retorna (df, errores_html). Si hay errores, df es None."""
    errores = []

    # 1. Verificar que la tabla existe
    try:
        df_raw = pl.read_excel(io.BytesIO(file_bytes), table_name=TABLA_ESPERADA)
    except Exception as e:
        msg = str(e)
        if "table" in msg.lower() or "not found" in msg.lower() or "name" in msg.lower():
            errores.append(error_card(
                "Tabla no encontrada",
                f"No se encontró una tabla con el nombre <b>{TABLA_ESPERADA}</b> en el archivo. "
                f"Es posible que el nombre haya sido cambiado o que los datos no estén definidos como tabla de Excel.",
                f"En Excel, selecciona el rango de datos → <b>Insertar → Tabla</b>, y asegúrate de que el nombre "
                f"sea exactamente <code>{TABLA_ESPERADA}</code> (sin espacios adicionales, respetando mayúsculas)."
            ))
        else:
            errores.append(error_card(
                "Error al leer el archivo",
                f"El archivo no pudo ser leído correctamente.",
                "Verifica que el archivo no esté dañado, que tenga extensión <b>.xlsx</b> y que no esté abierto en Excel al momento de cargarlo."
            ))
        return None, errores

    cols_actuales = set(df_raw.columns)

    # 2. Columnas faltantes
    faltantes = [c for c in COLUMNAS_ESPERADAS if c not in cols_actuales]
    if faltantes:
        chips = "".join(f"<span class='col-missing'>{c}</span>" for c in faltantes)
        errores.append(error_card(
            f"{'Columna faltante' if len(faltantes) == 1 else f'{len(faltantes)} columnas faltantes'}",
            f"Las siguientes columnas no fueron encontradas en la tabla:<div class='error-cols'>{chips}</div>"
            f"<div style='margin-top:0.5rem;font-size:0.79rem;color:#7f1d1d'>Puede que el nombre haya sido modificado por error. "
            f"Compara con la lista de columnas esperadas al final de esta pantalla.</div>",
            "Abre el archivo en Excel, ve a la tabla <b>MatrizSeguimientoEvaluacion</b> y verifica que los encabezados "
            "coincidan exactamente (respeta mayúsculas, tildes y espacios). No renombres las columnas originales."
        ))

    # 3. Tipo de datos incorrecto — solo columnas que sí existen
    tipo_incorrecto = []
    for col, (tipo_label, tipos_validos) in COLUMNAS_ESPERADAS.items():
        if col not in cols_actuales:
            continue
        dtype = df_raw[col].dtype
        if tipo_label == "fecha":
            continue  # el cast strict=False lo maneja en procesar
        if dtype not in tipos_validos:
            tipo_incorrecto.append((col, tipo_label, str(dtype)))

    if tipo_incorrecto:
        chips = "".join(
            f"<span class='col-wrong-type'>{col}</span>"
            for col, _, _ in tipo_incorrecto
        )
        detalles = "".join(
            f"<li style='margin-bottom:4px'><b>{col}</b>: "
            f"el sistema encontró <b>{_tipo_amigable(dtype_actual)}</b>, "
            f"pero esperaba <b>{TIPO_LABEL[tipo_label]}</b> — {TIPO_EJEMPLO[tipo_label]}</li>"
            for col, tipo_label, dtype_actual in tipo_incorrecto
        )
        errores.append(error_card(
            f"{'Tipo de dato incorrecto' if len(tipo_incorrecto) == 1 else f'Tipo de dato incorrecto en {len(tipo_incorrecto)} columnas'}",
            f"Las siguientes columnas tienen un tipo de dato que no corresponde:<div class='error-cols'>{chips}</div>"
            f"<ul style='margin-top:0.6rem;font-size:0.8rem;padding-left:1.2rem'>{detalles}</ul>",
            "En Excel, selecciona la columna señalada y revisa el formato de las celdas (menú <b>Inicio → Número</b>). "
            "Las columnas <b>CPI</b> y <b>SPI</b> deben tener formato <b>Número</b>. "
            "Si los valores están alineados a la izquierda, es probable que estén guardados como texto: "
            "selecciona la columna → <b>Datos → Texto en columnas</b> → finalizar."
        ))

    if errores:
        return None, errores

    return df_raw, []

GITHUB_RAW_URL          = "https://raw.githubusercontent.com/Dona121/Matriz-Evaluacion-Regalias/main/data/MatrizSeguimientoEvaluacion.xlsx"
GITHUB_CONTRATOS_URL    = "https://raw.githubusercontent.com/Dona121/Matriz-Evaluacion-Regalias/main/data/CG-cttos.xlsx"

@st.cache_data(show_spinner=False, ttl=3600)
def _cargar_desde_github(url: str):
    """Descarga el Excel desde GitHub Raw y devuelve los bytes. Cachea 1 hora."""
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read()
    except Exception:
        return None

def _parse_valor(s):
    """
    Convierte string de valor monetario a float.
    Maneja formatos COP: "1,234,567.89", "1.234.567,89", "1234567", etc.
    Definida a nivel de módulo para serialización eficiente en map_elements().
    """
    if s is None:
        return None
    s = str(s).strip().replace("$", "").replace(" ", "")
    if not s or s in ("", "None", "-", "—"):
        return None
    has_comma = "," in s
    has_dot   = "." in s
    try:
        if has_comma and has_dot:
            last_comma = s.rfind(",")
            last_dot   = s.rfind(".")
            if last_dot > last_comma:
                s = s.replace(",", "")
            else:
                s = s.replace(".", "").replace(",", ".")
        elif has_comma:
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")
        elif has_dot:
            parts = s.split(".")
            if len(parts) > 2:
                s = s.replace(".", "")
        return float(s)
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def procesar_contratos(file_bytes):
    """
    Lee y limpia el reporte de contratos de GESPROY.
    Retorna (df, diagnostico_str) — df puede ser None si falla.
    diagnostico tiene info útil para debugging.
    """
    COLS_CONTRATOS = [
        "BPIN",
        "NO. PROCESO PRECONTRACTUAL",
        "MODALIDAD CONTRATACION",
        "TIPO CONTRATO",
        "CONTRATO OBJETO",
        "CONTRATO VALOR TOTAL",
        "ESTADO CONTRATO",
    ]
    diag = []
    try:
        # ── Leer raw sin encabezado (GESPROY exporta 2 filas de meta antes de los datos) ──
        df_raw = pl.read_excel(
            io.BytesIO(file_bytes),
            has_header=False,
            infer_schema_length=0,  # todo como string inicialmente
        )
        diag.append(f"Filas raw: {df_raw.height}, Cols: {df_raw.width}")

        if df_raw.height < 3:
            return None, f"Archivo muy pequeño ({df_raw.height} filas)"

        # ── Detectar fila de encabezados robustamente ────────────────────────
        # Buscar la fila que contiene "BPIN" en alguna celda (puede ser fila 0 o 1)
        header_row_idx = None
        for row_idx in range(min(5, df_raw.height)):
            row_vals = [str(v).strip().upper() for v in df_raw.row(row_idx) if v is not None]
            if "BPIN" in row_vals:
                header_row_idx = row_idx
                break

        if header_row_idx is None:
            diag.append("ERROR: no se encontró fila con 'BPIN'")
            diag.append(f"Fila 0: {list(df_raw.row(0))[:8]}")
            diag.append(f"Fila 1: {list(df_raw.row(1))[:8]}")
            return None, " | ".join(diag)

        diag.append(f"Fila de headers detectada: {header_row_idx}")

        # ── Construir encabezados desde la fila detectada ────────────────────
        encabezados_raw = df_raw.row(header_row_idx)
        encabezados = []
        seen = {}
        for i, v in enumerate(encabezados_raw):
            name = str(v).strip() if v is not None and str(v).strip() not in ("", "None") else f"_col_{i}"
            # Deduplicar nombres repetidos
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            encabezados.append(name)

        # ── Renombrar y saltar filas de encabezado ───────────────────────────
        df = (
            df_raw
            .rename(dict(zip(df_raw.columns, encabezados)))
            .slice(header_row_idx + 1)  # datos empiezan después del header
        )
        diag.append(f"Columnas detectadas (primeras 10): {list(df.columns[:10])}")
        diag.append(f"Filas de datos: {df.height}")

        # ── Verificar columnas necesarias ────────────────────────────────────
        cols_presentes = set(df.columns)
        faltantes = [c for c in COLS_CONTRATOS if c not in cols_presentes]
        if faltantes:
            diag.append(f"ERROR: columnas faltantes: {faltantes}")
            diag.append(f"Columnas disponibles: {sorted(cols_presentes)}")
            return None, " | ".join(diag)

        df = df.select(COLS_CONTRATOS)

        # ── Limpieza ─────────────────────────────────────────────────────────
        # 1. Strip todas las columnas texto
        str_cols = [c for c in COLS_CONTRATOS if c != "CONTRATO VALOR TOTAL"]
        df = df.with_columns([
            pl.col(c).cast(pl.Utf8, strict=False).str.strip_chars().alias(c)
            for c in str_cols
        ])

        # 2. BPIN: forzar string, quitar puntos/comas/espacios/guiones
        df = df.with_columns(
            pl.col("BPIN")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.replace_all(r"[.\-,\s]", "")
            .alias("BPIN")
        )

        # 3. Filtrar filas sin BPIN válido
        df = df.filter(
            pl.col("BPIN").is_not_null() &
            (pl.col("BPIN").str.len_chars() >= 5) &
            (pl.col("BPIN") != "None") &
            (pl.col("BPIN") != "BPIN")  # filtrar si quedó alguna fila de encabezado
        )
        diag.append(f"Filas con BPIN válido: {df.height}")

        # 4. Muestra de BPINs para diagnóstico
        bpins_muestra = df["BPIN"].head(5).to_list()
        diag.append(f"BPINs muestra: {bpins_muestra}")

        # 5. CONTRATO VALOR TOTAL → Float64 (usa _parse_valor definida a nivel de módulo)
        df = df.with_columns(
            pl.col("CONTRATO VALOR TOTAL")
            .cast(pl.Utf8, strict=False)
            .map_elements(_parse_valor, return_dtype=pl.Float64)
            .alias("CONTRATO VALOR TOTAL")
        )

        # 6. Deduplicar y uppercase estado
        df = df.unique()
        df = df.with_columns(
            pl.col("ESTADO CONTRATO")
            .cast(pl.Utf8, strict=False)
            .str.strip_chars()
            .str.to_uppercase()
            .alias("ESTADO CONTRATO")
        )

        return (df if df.height > 0 else None), " | ".join(diag)

    except Exception as e:
        diag.append(f"EXCEPCIÓN: {type(e).__name__}: {e}")
        return None, " | ".join(diag)
