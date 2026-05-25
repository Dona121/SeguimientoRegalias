"""
data_igpr.py
Carga y procesamiento de los Excel del IGPR (Índice de Gestión de Proyectos de
Regalías) publicados por el DNP. Replica la lógica del notebook contexto/IGPR.ipynb:

  1. Descarga los 5 Excel de GitHub (4 trimestres 2025 + I trim 2026).
  2. Aplica `limpiar_encabezados()` para deshacer `_x000a_`, dobles espacios,
     fechas embebidas y asteriscos en los nombres de columna.
  3. Filtra los proyectos cuya "ENTIDAD EJECUTORA O BENEFICIARIA (A MEDIR)"
     sea "DEPARTAMENTO DE SUCRE".
  4. Hace join con BPIN para traer ENTIDAD desde la Matriz de Seguimiento
     (consolidando las 3 tablas: Departamento, Descentralizadas, Municipios).
  5. Devuelve un único DataFrame consolidado con columnas:
        BPIN, NOMBRE DEL PROYECTO, ENTIDAD, TRIMESTRE EVALUADO, VIGENCIA,
        PUNTAJE, CLASIFICACIÓN PLAZO PARA EJECUCIÓN (solo en 2026 T1).

Las URLs son raw.githubusercontent.com — mismo patrón que el resto del proyecto.
"""
from __future__ import annotations

import io
import logging
import urllib.request

import polars as pl
import streamlit as st

from constants import TABLA_ESPERADA, TABLA_DESCENTRALIZADAS, TABLA_MUNICIPIOS

_log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# URLs en GitHub Raw — definidas en una sola estructura para que sea fácil
# agregar trimestres futuros (basta con sumar una entrada a TRIMESTRES_IGPR).
# Cada entrada describe:
#   url            → enlace al Excel
#   tabla          → nombre de la tabla (Insertar → Tabla en Excel)
#   col_puntaje    → nombre exacto del campo de puntaje DESPUÉS de limpiar
#                    encabezados (varía trimestre a trimestre)
#   trimestre      → etiqueta legible
#   vigencia       → año
#   extras         → columnas adicionales a conservar (solo aplica al 2026 T1
#                    que trae "CLASIFICACIÓN PLAZO PARA EJECUCIÓN")
# ─────────────────────────────────────────────────────────────────────────────
IGPR_BASE = "https://raw.githubusercontent.com/Dona121/Matriz-Evaluacion-Regalias/main/data/IGPR/"

TRIMESTRES_IGPR: list[dict] = [
    {
        "url":         IGPR_BASE + "Resultados%20IGPR%20-%20I%20trimestre%202025%2006022026.xlsx",
        "tabla":       "IGPR_I_Trimestre_2025",
        "col_puntaje": "IGPR FINAL PROYECTO I TRIM 2025",
        "trimestre":   "PRIMER TRIMESTRE",
        "vigencia":    2025,
        "extras":      [],
    },
    {
        "url":         IGPR_BASE + "Resultados%20IGPR-%20II%20trimestre%202025%2006022026.xlsx",
        "tabla":       "IGPR_II_Trimestre_2025",
        "col_puntaje": "IGPR FINAL PROYECTO II TRIM 2025",
        "trimestre":   "SEGUNDO TRIMESTRE",
        "vigencia":    2025,
        "extras":      [],
    },
    {
        "url":         IGPR_BASE + "Resultados%20IGPR-%20III%20trimestre%202025%2011052026.xlsx",
        "tabla":       "IGPR_III_Trimestre_2025",
        "col_puntaje": "IGPR FINAL PROYECTO III TRIM 2025",
        "trimestre":   "TERCER TRIMESTRE",
        "vigencia":    2025,
        "extras":      [],
    },
    {
        "url":         IGPR_BASE + "Resultados%20IGPR%20-%20IV%20trimestre%202025%2011052026.xlsx",
        "tabla":       "IGPR_IV_Trimestre_2025",
        "col_puntaje": "IGPR PROYECTO FINAL IV TRIM 2025",
        "trimestre":   "CUARTO TRIMESTRE",
        "vigencia":    2025,
        "extras":      [],
    },
    {
        "url":         IGPR_BASE + "Resultados%20IGPR%20-%20I%20trimestre%202026%2015052026.xlsx",
        "tabla":       "IGPR_I_Trimestre_2026",
        "col_puntaje": "IGPR PROYECTO FINAL",
        "trimestre":   "PRIMER TRIMESTRE",
        "vigencia":    2026,
        # La clasificación de plazo solo se reporta a partir de 2026.
        "extras":      ["CLASIFICACIÓN PLAZO PARA EJECUCIÓN"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Orden cronológico canónico — para ordenar y comparar trimestres.
# ─────────────────────────────────────────────────────────────────────────────
ORDEN_TRIMESTRE = {
    "PRIMER TRIMESTRE":  1,
    "SEGUNDO TRIMESTRE": 2,
    "TERCER TRIMESTRE":  3,
    "CUARTO TRIMESTRE":  4,
}

TRIMESTRE_CORTO = {
    "PRIMER TRIMESTRE":  "I",
    "SEGUNDO TRIMESTRE": "II",
    "TERCER TRIMESTRE":  "III",
    "CUARTO TRIMESTRE":  "IV",
}


# ─────────────────────────────────────────────────────────────────────────────
# Escala diferencial de desempeño (Resolución 4574 de 2025, sección 2.6).
# Para Departamentos con capacidad institucional 1/2 el umbral de
# "ADECUADO" es >=60. Sucre está clasificado en Capacidad 1.
# ─────────────────────────────────────────────────────────────────────────────
UMBRAL_ADECUADO_DEPARTAMENTO = 60.0


def clasificar_puntaje(p: float | None) -> str:
    """Convierte el puntaje numérico en la categoría textual del IGPR.

    Sigue la escala de la Resolución 4574 de 2025:
      • < 60   → NO ADECUADO
      • >= 60  → ADECUADO
    Devuelve ``"SIN DATO"`` si el puntaje viene nulo o no es numérico.
    """
    if p is None:
        return "SIN DATO"
    try:
        v = float(p)
    except (TypeError, ValueError):
        return "SIN DATO"
    return "ADECUADO" if v >= UMBRAL_ADECUADO_DEPARTAMENTO else "NO ADECUADO"


def color_por_puntaje(p: float | None) -> str:
    """Devuelve el HEX de color a usar para un puntaje (matriz semáforo)."""
    if p is None:
        return "#94a3b8"  # gris — sin dato
    try:
        v = float(p)
    except (TypeError, ValueError):
        return "#94a3b8"
    if v >= 80:
        return "#15803d"  # verde fuerte — sobresaliente
    if v >= 60:
        return "#84cc16"  # verde lima — adecuado
    if v >= 40:
        return "#f59e0b"  # ámbar — limítrofe
    return "#dc2626"      # rojo — bajo


# ─────────────────────────────────────────────────────────────────────────────
# Carga
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=3600)
def _bajar_bytes(url: str) -> bytes | None:
    """Descarga un Excel y devuelve sus bytes. None si falla."""
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            return r.read()
    except Exception as e:
        _log.warning("No se pudo descargar %s: %s", url, e)
        return None


def _limpiar_encabezados(cols: list[str]) -> list[str]:
    """Replica `limpiar_encabezados` del notebook del cliente.

    Quita los saltos de línea codificados como ``_x000a_`` que Excel inserta
    en los headers multilínea, colapsa dobles espacios, elimina fechas
    embebidas y los asteriscos de notas al pie.
    """
    s = (
        pl.Series(cols)
        .str.replace_all("_x000a_", " ")
        .str.replace_all("  ", " ")
        .str.replace_all(
            r"\((\d{2}/\d{2}/\d{4})\)|(\d{2}/\d{2}/\d{4})", ""
        )
        .str.replace_all(r"(\*)|(\s\*)", "")
        .str.strip_chars()
    )
    return s.to_list()


def _entidades_desde_matriz(matriz_bytes: bytes) -> pl.DataFrame:
    """
    Construye el catálogo BPIN → ENTIDAD a partir de las 3 tablas de
    MatrizSeguimientoEvaluacion.xlsx (Departamento + Descentralizadas +
    Municipios), tal como hace el notebook IGPR.ipynb.
    """
    buf = io.BytesIO(matriz_bytes)
    partes: list[pl.DataFrame] = []

    try:
        dpto = (
            pl.read_excel(buf, table_name=TABLA_ESPERADA, infer_schema_length=0)
            .select("BPIN", "ENTIDAD O SECRETARIA")
            .rename({"ENTIDAD O SECRETARIA": "ENTIDAD"})
        )
        partes.append(dpto)
    except Exception as e:
        _log.warning("No se pudo leer la tabla Departamento: %s", e)

    try:
        buf.seek(0)
        desc = (
            pl.read_excel(buf, table_name=TABLA_DESCENTRALIZADAS, infer_schema_length=0)
            .select("BPIN", "EJECUTOR")
            .rename({"EJECUTOR": "ENTIDAD"})
        )
        partes.append(desc)
    except Exception as e:
        _log.warning("No se pudo leer la tabla Descentralizadas: %s", e)

    try:
        buf.seek(0)
        munic = (
            pl.read_excel(buf, table_name=TABLA_MUNICIPIOS, infer_schema_length=0)
            .select("BPIN", "EJECUTOR")
            .rename({"EJECUTOR": "ENTIDAD"})
        )
        partes.append(munic)
    except Exception as e:
        _log.warning("No se pudo leer la tabla Municipios: %s", e)

    if not partes:
        return pl.DataFrame({"BPIN": [], "ENTIDAD": []}, schema={"BPIN": pl.Utf8, "ENTIDAD": pl.Utf8})

    catalogo = pl.concat(partes).with_columns(pl.col("BPIN").cast(pl.Utf8))
    # En caso de duplicados (un BPIN en dos tablas) nos quedamos con la
    # primera aparición, que sigue el orden Depto → Descent → Munic.
    catalogo = catalogo.unique(subset=["BPIN"], keep="first")
    return catalogo


def _procesar_un_trimestre(file_bytes: bytes,
                           cfg: dict,
                           catalogo_entidades: pl.DataFrame) -> pl.DataFrame | None:
    """Limpia, filtra y enriquece un Excel de IGPR."""
    if not file_bytes:
        return None

    try:
        df = pl.read_excel(io.BytesIO(file_bytes),
                           table_name=cfg["tabla"],
                           infer_schema_length=0)
    except Exception as e:
        _log.warning("No se pudo leer %s: %s", cfg["tabla"], e)
        return None

    # Limpieza de encabezados (deshace _x000a_, fechas, asteriscos, etc.)
    nuevos = _limpiar_encabezados(df.columns)
    df = df.rename(dict(zip(df.columns, nuevos)))

    # Algunas columnas requeridas
    requeridas = ["BPIN", "NOMBRE DEL PROYECTO",
                  "ENTIDAD EJECUTORA O BENEFICIARIA (A MEDIR)",
                  cfg["col_puntaje"]]
    faltan = [c for c in requeridas if c not in df.columns]
    if faltan:
        _log.warning("Faltan columnas en %s: %s — se omite", cfg["tabla"], faltan)
        return None

    cols_select = ["BPIN", "NOMBRE DEL PROYECTO", cfg["col_puntaje"]]
    for extra in cfg.get("extras", []):
        if extra in df.columns:
            cols_select.append(extra)

    df = (
        df.filter(pl.col("ENTIDAD EJECUTORA O BENEFICIARIA (A MEDIR)") == "DEPARTAMENTO DE SUCRE")
          .select(cols_select)
          .with_columns(
              pl.col("BPIN").cast(pl.Utf8),
              pl.lit(cfg["trimestre"]).alias("TRIMESTRE EVALUADO"),
              pl.lit(cfg["vigencia"]).cast(pl.Int32).alias("VIGENCIA"),
          )
          .rename({cfg["col_puntaje"]: "PUNTAJE"})
    )

    # Castear PUNTAJE a Float64 — los Excel suelen venir como string
    df = df.with_columns(
        pl.col("PUNTAJE")
          .cast(pl.Utf8, strict=False)
          .str.replace_all(",", ".")
          .str.strip_chars()
          .cast(pl.Float64, strict=False)
    )

    # Join con catálogo de entidades por BPIN
    df = df.join(catalogo_entidades, on="BPIN", how="left")

    return df


@st.cache_data(show_spinner=False, ttl=3600)
def cargar_igpr(matriz_bytes: bytes) -> pl.DataFrame:
    """Descarga y consolida los 5 Excel del IGPR.

    Parámetros
    ----------
    matriz_bytes : bytes
        Contenido binario de ``MatrizSeguimientoEvaluacion.xlsx`` — necesario
        para construir el catálogo BPIN → ENTIDAD.

    Devuelve
    --------
    polars.DataFrame con columnas:
        BPIN | NOMBRE DEL PROYECTO | ENTIDAD | TRIMESTRE EVALUADO |
        VIGENCIA | PUNTAJE | CLASIFICACIÓN PLAZO PARA EJECUCIÓN
    """
    catalogo = _entidades_desde_matriz(matriz_bytes)

    partes: list[pl.DataFrame] = []
    for cfg in TRIMESTRES_IGPR:
        bts = _bajar_bytes(cfg["url"])
        if bts is None:
            continue
        df_t = _procesar_un_trimestre(bts, cfg, catalogo)
        if df_t is not None and df_t.height > 0:
            partes.append(df_t)

    if not partes:
        return pl.DataFrame(
            schema={
                "BPIN": pl.Utf8,
                "NOMBRE DEL PROYECTO": pl.Utf8,
                "PUNTAJE": pl.Float64,
                "TRIMESTRE EVALUADO": pl.Utf8,
                "VIGENCIA": pl.Int32,
                "ENTIDAD": pl.Utf8,
            }
        )

    consolidado = pl.concat(partes, how="diagonal")

    # Columna auxiliar para ordenar cronológicamente
    consolidado = consolidado.with_columns(
        pl.col("TRIMESTRE EVALUADO")
          .replace_strict(ORDEN_TRIMESTRE, default=99)
          .cast(pl.Int32)
          .alias("_orden_trim"),
        pl.col("TRIMESTRE EVALUADO")
          .replace_strict(TRIMESTRE_CORTO, default="?")
          .alias("TRIM_CORTO"),
    ).with_columns(
        # Etiqueta amigable "I 2025", "II 2025", ...
        (pl.col("TRIM_CORTO") + pl.lit(" ") + pl.col("VIGENCIA").cast(pl.Utf8)).alias("PERIODO"),
    ).sort(["VIGENCIA", "_orden_trim", "ENTIDAD", "PUNTAJE"])

    # Categoría textual (ADECUADO/NO ADECUADO)
    consolidado = consolidado.with_columns(
        pl.col("PUNTAJE").map_elements(clasificar_puntaje, return_dtype=pl.Utf8).alias("CATEGORIA"),
    )

    return consolidado


# ─────────────────────────────────────────────────────────────────────────────
# Agregaciones derivadas — facilitan la vida en igpr.py
# ─────────────────────────────────────────────────────────────────────────────
def resumen_por_periodo(df: pl.DataFrame) -> pl.DataFrame:
    """Promedio simple, mínimo, máximo y conteo por trimestre + vigencia."""
    if df.is_empty():
        return df
    return (
        df.group_by(["VIGENCIA", "TRIMESTRE EVALUADO", "_orden_trim", "PERIODO"], maintain_order=True)
          .agg(
              pl.col("PUNTAJE").mean().round(1).alias("PROMEDIO"),
              pl.col("PUNTAJE").min().round(1).alias("MINIMO"),
              pl.col("PUNTAJE").max().round(1).alias("MAXIMO"),
              pl.col("BPIN").n_unique().alias("PROYECTOS"),
          )
          .sort(["VIGENCIA", "_orden_trim"])
    )


def resumen_por_entidad_periodo(df: pl.DataFrame) -> pl.DataFrame:
    """Promedio por entidad × periodo (matriz para la tabla resumen)."""
    if df.is_empty():
        return df
    return (
        df.group_by(["ENTIDAD", "VIGENCIA", "TRIMESTRE EVALUADO", "_orden_trim", "PERIODO"], maintain_order=True)
          .agg(
              pl.col("PUNTAJE").mean().round(1).alias("PROMEDIO"),
              pl.col("BPIN").n_unique().alias("PROYECTOS"),
          )
          .sort(["ENTIDAD", "VIGENCIA", "_orden_trim"])
    )
