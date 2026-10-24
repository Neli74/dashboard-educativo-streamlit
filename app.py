import streamlit as st
import pandas as pd
import geopandas as gpd
import json
import plotly.express as px

st.set_page_config(page_title="Dashboard Educativo Corrientes", layout="wide")

# 1. Carga y preparación de datos
@st.cache_data
def cargar_datos():
    # Cargar escuelas
    df_esc = pd.read_excel("ESCUELAS_DEFINITIVA.xlsx")
    
    # Asignar nivel para colorear puntos
    def definir_nivel(row):
        if row.get("N. SECUNDARIO") == 1:
            return "Secundario"
        elif row.get("N. PRIMARIO") == 1:
            return "Primario"
        elif row.get("N.INICIAL") == 1:
            return "Inicial"
        elif row.get("N. SUPERIOR") == 1:
            return "Superior"
        return "Otro"
    
    df_esc["Nivel_Oferta"] = df_esc.apply(definir_nivel, axis=1)
    
    # Cargar barrios (Shapefile)
    gdf_barrios = gpd.read_file("barriosmunicipalidad.shp")
    if gdf_barrios.crs is None or gdf_barrios.crs != "EPSG:4326":
        gdf_barrios = gdf_barrios.set_crs(epsg=4326, allow_override=True)
        
    # Totales INDEC (Censo 2022 Capital)
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

# Filtrado reactivo
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

# 4. Sección de Mapa Interactivo con Plotly
st.subheader("Mapa Territorial: Polígonos de Barrios y Establecimientos")

centro_lat, centro_lon = -27.4692, -58.8306
zoom_inicial = 11.5

if barrio_sel != "Todos los barrios" and not df_filtrado.empty:
    centro_lat = float(df_filtrado["LATITUD"].mean())
    centro_lon = float(df_filtrado["LONGITUD"].mean())
    zoom_inicial = 13.5

# Mapa base con puntos de escuelas
fig_mapa = px.scatter_mapbox(
    df_filtrado,
    lat="LATITUD",
    lon="LONGITUD",
    color="Nivel_Oferta",
    color_discrete_map={
        "Secundario": "#EF553B",
        "Primario": "#00CC96",
        "Inicial": "#FFA15A",
        "Superior": "#AB63FA",
        "Otro": "#636EFA"
    },
    hover_name="fna",
    hover_data={"BARRIOS_CORREGIDO": True, "cue": True, "LATITUD": False, "LONGITUD": False, "Nivel_Oferta": False},
    zoom=zoom_inicial,
    center={"lat": centro_lat, "lon": centro_lon},
    mapbox_style="open-street-map",
    height=580
)

# Incorporar las capas de polígonos de los barrios
try:
    geojson_barrios = json.loads(gdf_barrios.to_json())
    fig_mapa.update_layout(
        mapbox_layers=[
            {
                "sourcetype": "geojson",
                "source": geojson_barrios,
                "type": "fill",
                "color": "rgba(41, 128, 185, 0.15)",
                "below": "traces"
            },
            {
                "sourcetype": "geojson",
                "source": geojson_barrios,
                "type": "line",
                "color": "#2980b9",
                "line": {"width": 1.2}
            }
        ]
    )
except Exception:
    pass

fig_mapa.update_layout(margin=dict(l=0, r=0, t=10, b=10), legend_title_text="Nivel Educativo")
st.plotly_chart(fig_mapa, use_container_width=True)

st.divider()

# 5. Sección de Tablas y Ratios
col_izq, col_der = st.columns([1, 1])

with col_izq:
    st.subheader("Demanda INDEC vs Capacidad Edilicia")
    st.dataframe(df_demanda, use_container_width=True)

with col_der:
    st.subheader("Top 10 Barrios con más Escuelas")
    top_barrios = df_escuelas["BARRIOS_CORREGIDO"].value_counts().head(10).reset_index()
    top_barrios.columns = ["Barrio", "Cantidad"]
    fig = px.bar(top_barrios, x="Cantidad", y="Barrio", orientation="h", color="Cantidad", color_continuous_scale="Blues")
    fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=0, r=0, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
