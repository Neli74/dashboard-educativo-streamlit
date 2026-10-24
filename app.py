import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import plotly.express as px

st.set_page_config(page_title="Dashboard Educativo Corrientes", layout="wide")

# 1. Carga y preparación de datos
@st.cache_data
def cargar_datos():
    # Cargar escuelas
    df_esc = pd.read_excel("ESCUELAS_DEFINITIVA.xlsx")
    
    # Cargar barrios (Shapefile)
    gdf_barrios = gpd.read_file("barriosmunicipalidad.shp")
    if gdf_barrios.crs != "EPSG:4326":
        gdf_barrios = gdf_barrios.to_crs(epsg=4326)
        
    # Cargar totales INDEC (Censo 2022 Capital)
    demanda = {
        "Nivel": ["Maternal / 0 a 3", "Inicial (4 y 5)", "Primario", "Secundario", "Superior"],
        "Alumnos_INDEC": [7321, 11116, 46040, 50204, 16331],
        "Escuelas": [
            int(df_esc["N. ED. TERMPRANA"].sum()),
            int(df_esc["N.INICIAL"].sum()),
            int(df_esc["N. PRIMARIO"].sum()),
            int(df_esc["N. SECUNDARIO"].sum()),
            int(df_esc["N. SUPERIOR"].sum())
        ]
    }
    df_demanda = pd.DataFrame(demanda)
    df_demanda["Ratio_Alumnos_x_Escuela"] = (df_demanda["Alumnos_INDEC"] / df_demanda["Escuelas"]).round(1)
    
    return df_esc, gdf_barrios, df_demanda

df_escuelas, gdf_barrios, df_demanda = cargar_datos()

# 2. Barra lateral con filtros
st.sidebar.title("Filtros del Mapa")

lista_barrios = ["Todos los barrios"] + sorted([b for b in df_escuelas["BARRIOS_CORREGIDO"].dropna().unique()])
barrio_sel = st.sidebar.selectbox("Seleccionar Barrio:", lista_barrios)

niveles_disponibles = ["N.INICIAL", "N. PRIMARIO", "N. SECUNDARIO", "N. SUPERIOR", "N. ED. TERMPRANA"]
nivel_sel = st.sidebar.multiselect("Niveles Educativos a mostrar:", niveles_disponibles, default=["N.INICIAL", "N. PRIMARIO", "N. SECUNDARIO"])

# Filtrar escuelas
df_filtrado = df_escuelas.copy()
if barrio_sel != "Todos los barrios":
    df_filtrado = df_filtrado[df_filtrado["BARRIOS_CORREGIDO"] == barrio_sel]

if nivel_sel:
    condicion = df_filtrado[nivel_sel].sum(axis=1) > 0
    df_filtrado = df_filtrado[condicion]

# 3. Encabezado principal y Métricas (KPIs)
st.title("Mapa y Análisis Educativo: Corrientes Capital")
st.markdown("Visualización integrada de oferta escolar, delimitación de barrios y demanda censal (INDEC).")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Establecimientos Filtrados", len(df_filtrado))
col2.metric("Población Escolarizada", "161.863")
col3.metric("Mayor Demanda", "Secundaria (50.204)")
col4.metric("Barrio con más oferta", "B° Pirayuí (29)")

st.divider()

# 4. Sección de Mapa Interactivo
st.subheader("Mapa Territorial: Polígonos de Barrios y Establecimientos")

centro_lat, centro_lon = -27.4692, -58.8306
zoom_inicial = 12

if barrio_sel != "Todos los barrios" and not df_filtrado.empty:
    centro_lat = float(df_filtrado["LATITUD"].mean())
    centro_lon = float(df_filtrado["LONGITUD"].mean())
    zoom_inicial = 14

m = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom_inicial, tiles="OpenStreetMap")

# Dibujar las áreas de los barrios
try:
    folium.GeoJson(
        gdf_barrios,
        name="Barrios",
        style_function=lambda x: {
            "fillColor": "#3388ff",
            "color": "#185a9d",
            "weight": 1.5,
            "fillOpacity": 0.2
        }
    ).add_to(m)
except Exception:
    pass

# Dibujar los puntos de las escuelas
for _, row in df_filtrado.iterrows():
    color_punto = "blue"
    if row["N. SECUNDARIO"] == 1:
        color_punto = "red"
    elif row["N. PRIMARIO"] == 1:
        color_punto = "green"
    elif row["N.INICIAL"] == 1:
        color_punto = "orange"

    folium.CircleMarker(
        location=[row["LATITUD"], row["LONGITUD"]],
        radius=5,
        color=color_punto,
        fill=True,
        fill_color=color_punto,
        fill_opacity=0.8,
        popup=f"{row['fna']} - {row['BARRIOS_CORREGIDO']}",
        tooltip=str(row["fna"])
    ).add_to(m)

# Renderizar el mapa de forma fluida
st_folium(m, use_container_width=True, height=520, returned_objects=[])
# Coordenadas de Corrientes Capital
centro_lat, centro_lon = -27.4692, -58.8306
zoom_inicial = 12
