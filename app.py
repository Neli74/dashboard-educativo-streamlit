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

    # Identificación de modalidad
    col_mod = None
    for c in ["MODALIDAD", "modalidad", "Modalidad", "MODALIDAD_NORMALIZADA"]:
        if c in df_esc.columns:
            col_mod = c
            break
    if col_mod:
        df_esc["Modalidad_Display"] = df_esc[col_mod].fillna("Sin modalidad asignada").astype(str)
    else:
        df_esc["Modalidad_Display"] = "Común"

    # Cargar barrios y asegurar coordenadas en grados (WGS84)
    gdf_barrios = gpd.read_file("barriosmunicipalidad.shp")
    bounds = gdf_barrios.total_bounds
    # Si las coordenadas están en metros (fuera del rango -180 a 180), reproyectar
    if bounds[0] < -180 or bounds[0] > 180 or bounds[2] < -180 or bounds[2] > 180:
        if gdf_barrios.crs is not None:
            gdf_barrios = gdf_barrios.to_crs(epsg=4326)
        else:
            gdf_barrios = gdf_barrios.set_crs(epsg=22185).to_crs(epsg=4326)
    else:
        if gdf_barrios.crs is None or gdf_barrios.crs != "EPSG:4326":
            gdf_barrios = gdf_barrios.set_crs(epsg=4326, allow_override=True)
        
    # Demanda INDEC vs Oferta
    n_maternal = int(df_esc["N. ED. TERMPRANA"].sum()) if "N. ED. TERMPRANA" in df_esc.columns else 32
    n_inicial = int(df_esc["N.INICIAL"].sum()) if "N.INICIAL" in df_esc.columns else 136
    n_primario = int(df_esc["N. PRIMARIO"].sum()) if "N. PRIMARIO" in df_esc.columns else 136
    n_secundario = int(df_esc["N. SECUNDARIO"].sum()) if "N. SECUNDARIO" in df_esc.columns else 98
    n_superior = int(df_esc["N. SUPERIOR"].sum()) if "N. SUPERIOR" in df_esc.columns else 24

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

barrios_lista = ["Todos los barrios"] + sorted([b for b in df_escuelas["BARRIOS_CORREGIDO"].dropna().unique()])
barrio_sel = st.sidebar.selectbox("Seleccionar Barrio:", barrios_lista)

niveles_cols = ["N. ED. TERMPRANA", "N.INICIAL", "N. PRIMARIO", "N. SECUNDARIO", "N. SUPERIOR"]
niveles_presentes = [c for c in niveles_cols if c in df_escuelas.columns]
niveles_sel = st.sidebar.multiselect("Filtrar por Niveles:", niveles_presentes, default=niveles_presentes[:4])

df_filtrado = df_escuelas.copy()
if barrio_sel != "Todos los barrios":
    df_filtrado = df_filtrado[df_filtrado["BARRIOS_CORREGIDO"] == barrio_sel]

if niveles_sel:
    df_filtrado = df_filtrado[df_filtrado[niveles_sel].sum(axis=1) > 0]

# 3. Encabezado y KPIs
st.title("Tablero Educativo Corrientes - INDEC vs Oferta")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Establecimientos Filtrados", len(df_filtrado))
k2.metric("Población Escolarizada", "161.863")
k3.metric("Mayor Demanda", "Secundaria (50.204)")
top_b = df_escuelas["BARRIOS_CORREGIDO"].value_counts().index[0]
top_c = df_escuelas["BARRIOS_CORREGIDO"].value_counts().iloc[0]
k4.metric("Barrio con mayor oferta", f"{top_b} ({top_c})")

st.markdown("---")

# 4. Sección de Mapa y Gráficos
col_mapa, col_grafico = st.columns([1.1, 0.9])

with col_mapa:
    st.subheader("Distribución Territorial de Escuelas")
    
    c_capas1, c_capas2, c_capas3 = st.columns(3)
    ver_barrios = c_capas1.checkbox("Ver Polígonos de Barrios", value=True)
    ver_
