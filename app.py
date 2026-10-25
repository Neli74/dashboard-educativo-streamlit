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
    
    # Clasificación por nivel educativo
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
        
    # Localizar la columna de texto con el nombre del barrio
    cols_candidatas = [c for c in gdf_barrios.columns if any(k in c.upper() for k in ["BARRIO", "NOMBRE", "NOMB", "BARR"])]
    col_nombre_shp = cols_candidatas[0] if cols_candidatas else gdf_barrios.columns[0]
    gdf_barrios["NOMBRE_BARRIO_SHP"] = gdf_barrios[col_nombre_shp].astype(str).str.strip().str.upper()

    # DISOLVER: Unificar parcelas y subdivisiones catastrales en polígonos por barrio real
    gdf_barrios_unificados = gdf_barrios.dissolve(by="NOMBRE_BARRIO_SHP", as_index=False)

    # Georreferenciación de escuelas para el cruce espacial
    escuelas_geo = df_esc.dropna(subset=["LATITUD", "LONGITUD"]).copy()
    gdf_escuelas_pts = gpd.GeoDataFrame(
        escuelas_geo,
        geometry=gpd.points_from_xy(escuelas_geo["LONGITUD"], escuelas_geo["LATITUD"]),
        crs="EPSG:4326"
    )
    
    # Left join espacial sobre los barrios consolidados
    cruce_espacial = gdf_barrios_unificados.sjoin(gdf_escuelas_pts, how="left", predicate="contains")
    conteo_escuelas = cruce_espacial.groupby("NOMBRE_BARRIO_SHP")["index_right"].count().reset_index()
    conteo_escuelas.columns = ["NOMBRE_BARRIO_SHP", "CANT_ESCUELAS"]
    
    gdf_barrios_final = gdf_barrios_unificados.merge(conteo_escuelas, on="NOMBRE_BARRIO_
