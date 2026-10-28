import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Tablero Educativo Corrientes - INDEC vs Oferta", layout="wide")

# 1. Carga y preparación de bases de datos
@st.cache_data
def cargar_datos():
    df_esc = pd.read_excel("ESCUELAS_DEFINITIVA.xlsx")
    
    # Clasificación por nivel educativo (para visualización / gráfico de torta)
    def clasificar_nivel(row):
        if row.get("N. SECUNDARIO") == 1:
            return "Secundaria"
        elif row.get("N. PRIMARIO") == 1:
            return "Primaria"
        elif row.get("N.INICIAL") == 1:
            return "Inicial"
        elif row.get("N. SUPERIOR") == 1:
            return "Superior"
        elif row.get("N. ED. TERMPRANA") == 1:
            return "Educación Temprana / CDI"
        return "Otro / Especial"
    
    df_esc["Nivel_Oferta"] = df_esc.apply(clasificar_nivel, axis=1)

    # Clasificación jerárquica de modalidad
    def clasificar_modalidad_estricta(row):
        if row.get("M. CONTEXTO DE ENCIERRO") == 1:
            return "Contexto de Encierro"
        if row.get("M. EPJA") == 1:
            return "Jóvenes y Adultos (EPJA)"
        if row.get("M. ESPECIAL") == 1:
            return "Especial"
        if row.get("M. TECNICA") == 1:
            return "Técnica"
        if row.get("M. ARTISTICA") == 1:
            return "Artística"
        if row.get("M. RURAL") == 1:
            return "Rural"
        if row.get("M. BILINGÜE") == 1:
            return "Bilingüe"
        return "Común"

    df_esc["Modalidad_Display"] = df_esc.apply(clasificar_modalidad_estricta, axis=1)

    # Cargar capa vectorial de barrios y homogeneizar CRS (WGS84)
    gdf_barrios = gpd.read_file("barriosmunicipalidad.shp")
    bounds = gdf_barrios.total_bounds
    if bounds[0] < -180 or bounds[0] > 180 or bounds[2] < -180 or bounds[2] > 180:
        if gdf_barrios.crs is not None:
            gdf_barrios = gdf_barrios.to_crs(epsg=4326)
        else:
            gdf_barrios = gdf_barrios.set_crs(epsg=22185).to_crs(epsg=4326)
    else:
        if gdf_barrios.crs is None or gdf_barrios.crs != "EPSG:4326":
            gdf_barrios = gdf_barrios.set_crs(epsg=4326, allow_override=True)
        
    cols_sin_geometria = [c for c in gdf_barrios.columns if c != "geometry"]
    col_nombre_shp = None

    for col in cols_sin_geometria:
        serie_txt = gdf_barrios[col].astype(str).str.strip()
        tiene_letras = serie_txt.str.contains(r"[a-zA-Z]", regex=True).mean()
        if tiene_letras > 0.5:
            col_nombre_shp = col
            break

    if col_nombre_shp is None:
        col_nombre_shp = cols_sin_geometria[0]

    gdf_barrios["NOMBRE_BARRIO_SHP"] = gdf_barrios[col_nombre_shp].astype(str).str.strip().str.upper()

    # Demanda INDEC (Censo 2022 - Cuadro 2.7.3) vs Oferta de Establecimientos que ofrecen el nivel
    n_maternal = int(df_esc["N. ED. TERMPRANA"].sum()) if "N. ED. TERMPRANA" in df_esc.columns else 0
    n_inicial = int(df_esc["N.INICIAL"].sum()) if "N.INICIAL" in df_esc.columns else 0
    n_primario = int(df_esc["N. PRIMARIO"].sum()) if "N. PRIMARIO" in df_esc.columns else 0
    n_secundario = int(df_esc["N. SECUNDARIO"].sum()) if "N. SECUNDARIO" in df_esc.columns else 0
    n_superior = int(df_esc["N. SUPERIOR"].sum()) if "N. SUPERIOR" in df_esc.columns else 0

    demanda = {
        "Nivel": ["Materna / CDI (0 a 3)", "Inicial (Salas 4 y 5)", "Primaria", "Secundaria", "Superior"],
        "Alumnos_INDEC": [7321, 11116, 46040, 50204, 16331],
        "Escuelas": [n_maternal, n_inicial, n_primario, n_secundario, n_superior]
    }
    df_demanda = pd.DataFrame(demanda)
    df_demanda["Ratio_Alumnos_x_Escuela"] = (df_demanda["Alumnos_INDEC"] / df_demanda["Escuelas"]).round(0).astype(int)
    
    return df_esc, gdf_barrios, df_demanda

df_escuelas, gdf_barrios, df_demanda = cargar_datos()

# 2. Barra lateral de filtros
st.sidebar.title("Filtros del Tablero")

barrios_disponibles = sorted([b for b in df_escuelas["BARRIOS_CORREGIDO"].dropna().unique()])
barrios_sel = st.sidebar.multiselect(
    "Seleccionar Barrio(s):",
    options=barrios_disponibles,
    placeholder="Todos los barrios (o seleccioná uno o más)"
)

mapa_niveles = {
    "N. SECUNDARIO": "Secundaria",
    "N. PRIMARIO": "Primaria",
    "N.INICIAL": "Inicial",
    "N. SUPERIOR": "Superior",
    "N. ED. TERMPRANA": "Educación Temprana / CDI"
}
niveles_validos = [c for c in mapa_niveles.keys() if c in df_escuelas.columns]
nombres_niveles_disponibles = [mapa_niveles[c] for c in niveles_validos]

niveles_sel = st.sidebar.multiselect(
    "Filtrar por Niveles:",
    options=nombres_niveles_disponibles,
    default=nombres_niveles_disponibles
)

modalidades_unicas = [
    "Común", 
    "Especial", 
    "Técnica", 
    "Artística", 
    "Rural", 
    "Jóvenes y Adultos (EPJA)",
    "Contexto de Encierro
