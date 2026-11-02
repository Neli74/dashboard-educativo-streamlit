from __future__ import annotations

from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

# -----------------------------------------------------------------------------
# Configuración general y archivos
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Establecimientos Educativos en Corrientes - INDEC vs Oferta",
    page_icon="🏫",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
ARCHIVO_ESCUELAS = BASE_DIR / "ESCUELAS_DEFINITIVA.xlsx"
ARCHIVO_BARRIOS = BASE_DIR / "BarriosCorrientes.geojson"

CENTRO_CORRIENTES = {"lat": -27.4692, "lon": -58.8306}
ZOOM_INICIAL = 11.5

MAPA_NIVELES = {
    "N. SECUNDARIO": "Secundaria",
    "N. PRIMARIO": "Primaria",
    "N.INICIAL": "Inicial",
    "N. SUPERIOR": "Superior",
    "N. ED. TERMPRANA": "Educación Temprana / CDI",
}

MAPA_MODALIDADES = {
    "M. CONTEXTO DE ENCIERRO": "Contexto de Encierro",
    "M. EPJA": "Jóvenes y Adultos (EPJA)",
    "M. ESPECIAL": "Especial",
    "M. TECNICA": "Técnica",
    "M. ARTISTICA": "Artística",
    "M. RURAL": "Rural",
    "M. BILINGÜE": "Bilingüe",
    "M. COMUN": "Común",
}

COLORES_NIVELES = {
    "Secundaria": "#56CCF2",
    "Primaria": "#2D9CDB",
    "Inicial": "#9B8AFB",
    "Superior": "#F2C94C",
    "Educación Temprana / CDI": "#F2994A",
    "Otro / Especial": "#A0AEC0",
}

COLORES_MODALIDADES = {
    "Común": "#56CCF2",
    "Especial": "#9B8AFB",
    "Técnica": "#2D9CDB",
    "Artística": "#F2C94C",
    "Rural": "#27AE80",
    "Jóvenes y Adultos (EPJA)": "#F2994A",
    "Contexto de Encierro": "#EB5757",
    "Bilingüe": "#BB6BD9",
}

COLOR_TEXTO = "#EAF2FF"
COLOR_CELESTE = "#56CCF2"
COLOR_SIN_OFERTA = "#EF4444"

# Población INDEC 2022 total rigurosa (Suma de niveles formales: 7.321 + 11.116 + 46.040 + 50.204 + 16.331 = 131.012)
POBLACION_INDEC_TOTAL = "131.012"
POBLACION_INDEC_NIVELES = {
    "Educación Temprana / CDI": {"valor": 7321, "texto": "7.321 (Materna 0 a 3)"},
    "Inicial": {"valor": 11116, "texto": "11.116 (Salas 4 y 5)"},
    "Primaria": {"valor": 46040, "texto": "46.040"},
    "Secundaria": {"valor": 50204, "texto": "50.204"},
    "Superior": {"valor": 16331, "texto": "16.331"},
}


# -----------------------------------------------------------------------------
# Funciones auxiliares
# -----------------------------------------------------------------------------
def resolver_columna(df: pd.DataFrame, nombres: Iterable[str], obligatoria: bool = False):
    equivalencias = {str(col).strip().casefold(): col for col in df.columns}
    for nombre in nombres:
        encontrada = equivalencias.get(str(nombre).strip().casefold())
        if encontrada is not None:
            return encontrada
    if obligatoria:
        raise ValueError(
            "No se encontró ninguna de estas columnas en la base: "
            + ", ".join(nombres)
        )
    return None


def es_uno(serie: pd.Series) -> pd.Series:
    numerica = pd.to_numeric(serie, errors="coerce").eq(1)
    texto = serie.astype("string").str.strip().str.casefold()
    afirmativos = texto.isin(["true", "sí", "si", "yes", "y"])
    return (numerica | afirmativos).fillna(False)


def formatear_identificador(valor) -> str:
    if pd.isna(valor):
        return "No informado"
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    return str(valor).strip() or "No informado"


def lista_de_flags(df: pd.DataFrame, mapa: dict[str, str], alternativa: str) -> pd.Series:
    disponibles = [(col, etiqueta) for col, etiqueta in mapa.items() if col in df.columns]
    if not disponibles:
        return pd.Series(alternativa, index=df.index, dtype="string")

    banderas = {col: es_uno(df[col]).to_numpy() for col, _ in disponibles}
    resultados = []
    for posicion in range(len(df)):
        etiquetas = [
            etiqueta
            for col, etiqueta in disponibles
            if bool(banderas[col][posicion])
        ]
        resultados.append(" · ".join(etiquetas) if etiquetas else alternativa)
    return pd.Series(resultados, index=df.index, dtype="string")


def clasificar_nivel_original(df: pd.DataFrame) -> pd.Series:
    resultado = pd.Series("Otro / Especial", index=df.index, dtype="string")
    for columna, etiqueta in reversed(list(MAPA_NIVELES.items())):
        if columna in df.columns:
            resultado.loc[es_uno(df[columna])] = etiqueta
    return resultado


def clasificar_modalidad_original(df: pd.DataFrame) -> pd.Series:
    resultado = pd.Series("Común", index=df.index, dtype="string")
    for columna, etiqueta in reversed(list(MAPA_MODALIDADES.items())):
        if columna in df.columns:
            resultado.loc[es_uno(df[columna])] = etiqueta
    return resultado


def extraer_poligonos(geometria) -> list[Polygon]:
    if geometria is None or geometria.is_empty:
        return []
    if isinstance(geometria, Polygon):
        return [geometria]
    if isinstance(geometria, MultiPolygon):
        return list(geometria.geoms)
    if isinstance(geometria, GeometryCollection) or hasattr(geometria, "geoms"):
        resultado = []
        for parte in geometria.geoms:
            resultado.extend(extraer_poligonos(parte))
        return resultado
    return []


def normalizar_geometrias(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    geometrias = []
    for geometria in gdf.geometry:
        if geometria is None or geometria.is_empty:
            geometrias.append(None)
            continue
        if not geometria.is_valid:
            geometria = make_valid(geometria)
        partes = extraer_poligonos(geometria)
        partes = [p for p in partes if not p.is_empty]
        if not partes:
            geometrias.append(None)
            continue
        geometria_final = MultiPolygon(partes)
        if not geometria_final.is_valid:
            geometria_final = make_valid(geometria_final)
            partes_validas = extraer_poligonos(geometria_final)
            geometria_final = MultiPolygon(partes_validas)
        geometrias.append(geometria_final if not geometria_final.is_empty else None)

    resultado = gdf.copy()
    resultado = resultado.set_geometry(gpd.GeoSeries(geometrias, index=resultado.index, crs=gdf.crs))
    resultado = resultado[resultado.geometry.notna() & ~resultado.geometry.is_empty].copy()
    resultado = resultado[resultado.geometry.is_valid].copy()
    return resultado


def obtener_geometrias_barrios(ruta_geojson: str) -> gpd.GeoDataFrame:
    barrios = gpd.read_file(ruta_geojson)
    if barrios.crs is None:
        barrios = barrios.set_crs("EPSG:4326")
    elif barrios.crs.to_epsg() != 4326:
        barrios = barrios.to_crs("EPSG:4326")

    columna_nombre = resolver_columna(
        barrios,
        ["NAM", "NOMBRE", "NOMBRE_BARRIO", "FNA"],
        obligatoria=True,
    )
    barrios["NOMBRE_BARRIO_GEOJSON"] = (
        barrios[columna_nombre].astype("string").str.strip().str.upper()
    )
    barrios = barrios[
        barrios["NOMBRE_BARRIO_GEOJSON"].notna()
        & barrios["NOMBRE_BARRIO_GEOJSON"].ne("")
        & barrios["NOMBRE_BARRIO_GEOJSON"].ne("SIN BARRIO")
    ].copy()
    barrios = normalizar_geometrias(barrios)

    if barrios.empty:
        raise ValueError("El GeoJSON no contiene polígonos barriales válidos.")

    barrios = barrios.dissolve(
        by="NOMBRE_BARRIO_GEOJSON",
        as_index=False,
        aggfunc="first",
    )
    barrios = barrios.sort_values("NOMBRE_BARRIO_GEOJSON").reset_index(drop=True)
    return barrios


# -----------------------------------------------------------------------------
# Carga de datos con FILTRADO ESTRICTO de niveles formales (Exactamente 332 registros)
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner="Preparando establecimientos y límites barriales...")
def cargar_datos(
    ruta_excel: str,
    marca_excel: tuple[int, int],
    ruta_geojson: str,
    marca_geojson: tuple[int, int],
):
    _ = marca_excel, marca_geojson

    df_esc = pd.read_excel(ruta_excel)
    df_esc.columns = [str(col).strip() for col in df_esc.columns]

    # FILTRADO RADICAL: Excluir educación no formal y conservar solo los 332 formales
    cols_niveles_formales = list(MAPA_NIVELES.keys())
    cols_presentes = [c for c in cols_niveles_formales if c in df_esc.columns]
    if cols_presentes:
        mascara_formales = pd.Series(False, index=df_esc.index)
        for col in cols_presentes:
            mascara_formales |= es_uno(df_esc[col])
        df_esc = df_esc[mascara_formales].copy()

    df_esc = df_esc.reset_index(drop=True)
    df_esc["_row_id"] = range(len(df_esc))

    col_barrio = resolver_columna(df_esc, ["BARRIOS_CORREGIDO"], obligatoria=True)
    col_latitud = resolver_columna(df_esc, ["LATITUD", "LATITUDE"], obligatoria=True)
    col_longitud = resolver_columna(df_esc, ["LONGITUD", "LONGITUDE", "LON"], obligatoria=True)
    col_nombre = resolver_columna(
        df_esc,
        ["fna", "nombre", "nombre_establecimiento", "establecimiento", "nom_est"],
    )
    col_cue = resolver_columna(df_esc, ["cue", "CUE", "codigo_unico_establecimiento"])

    if col_barrio != "BARRIOS_CORREGIDO":
        df_esc["BARRIOS_CORREGIDO"] = df_esc[col_barrio]
    df_esc["LATITUD"] = pd.to_numeric(df_esc[col_latitud], errors="coerce")
    df_esc["LONGITUD"] = pd.to_numeric(df_esc[col_longitud], errors="coerce")
    df_esc["NOMBRE_DISPLAY"] = (
        df_esc[col_nombre].fillna("Sin nombre").astype(str).str.strip()
        if col_nombre
        else "Sin nombre"
    )
    df_esc["CUE_DISPLAY"] = (
        df_esc[col_cue].map(formatear_identificador)
        if col_cue
        else "No informado"
    )

    df_esc["Nivel_Oferta"] = clasificar_nivel_original(df_esc)
    df_esc["Modalidad_Display"] = clasificar_modalidad_original(df_esc)

    df_esc["Niveles_Disponibles"] = lista_de_flags(
        df_esc, MAPA_NIVELES, "No especificado"
    )
    df_esc["Modalidades_Disponibles"] = lista_de_flags(
        df_esc, MAPA_MODAL
