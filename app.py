import streamlit as st
import pandas as pd
import geopandas as gpd
import json
import plotly.express as px

st.set_page_config(page_title="Tablero Educativo Corrientes - INDEC vs Oferta", layout="wide")

# 1. Carga y preparación de bases de datos
@st.cache_data
def cargar_datos():
    # Cargar escuelas
    df_esc = pd.read_excel("ESCUELAS_DEFINITIVA.xlsx")
    
    # Asignar nivel principal para visualización
    def definir_nivel(row):
        if row.get("N. SECUNDARIO") == 1:
            return "Secundaria"
        elif row.get("N. PRIMARIO") == 1:
            return "Primaria"
        elif row.get("N.INICIAL") == 1:
            return "Inicial"
        elif row.get("N. SUPERIOR") == 1:
            return "Superior"
        return "Otro / Especial"
    
    df_esc["Nivel_Oferta"] = df_esc.apply(definir_nivel, axis=1)
    
    # Cargar barrios (Shapefile)
    gdf_barrios = gpd.read_file("barriosmunicipalidad.shp")
    if gdf_barrios.crs is None or gdf_barrios.crs != "EPSG:4326":
        gdf_barrios = gdf_barrios.set_crs(epsg=4326, allow_override=True)
        
    # Demanda INDEC (Censo Capital) vs Oferta real
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

# 2. Barra lateral de filtros interactivos
st.sidebar.title("Filtros Interactivos")

barrios_disponibles = ["Todos los barrios"] + sorted([b for b in df_escuelas["BARRIOS_CORREGIDO"].dropna().unique()])
barrio_sel = st.sidebar.selectbox("Filtrar por Barrio:", barrios_disponibles)

niveles_check = ["N.INICIAL", "N. PRIMARIO", "N. SECUNDARIO", "N. SUPERIOR"]
niveles_sel = st.sidebar.multiselect("Nivel de Enseñanza:", niveles_check, default=["N.INICIAL", "N. PRIMARIO", "N. SECUNDARIO"])

# Filtrado dinámico
df_filtrado = df_escuelas.copy()
if barrio_sel != "Todos los barrios":
    df_filtrado = df_filtrado[df_filtrado["BARRIOS_CORREGIDO"] == barrio_sel]

if niveles_sel:
    df_filtrado = df_filtrado[df_filtrado[niveles_sel].sum(axis=1) > 0]

# 3. Título principal y Métricas (KPIs)
st.title("Tablero Educativo Corrientes - INDEC vs Oferta")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.metric("Establecimientos (Filtro)", len(df_filtrado))
kpi2.metric("Población Escolarizada", "161.863")
kpi3.metric("Mayor Demanda INDEC", "Secundaria (50.204)")
top_nombre = df_escuelas["BARRIOS_CORREGIDO"].value_counts().index[0]
top_cant = df_escuelas["BARRIOS_CORREGIDO"].value_counts().iloc[0]
kpi4.metric("Barrio con mayor oferta", f"{top_nombre} ({top_cant})")

st.markdown("---")

# 4. Fila Superior: Distribución en Mapa y Gráficos por Barrio (Estilo Grafana)
col_mapa, col_grafico = st.columns([1.1, 0.9])

with col_mapa:
    st.subheader("Distribución de Escuelas (Ctes Cap).")
    
    centro_lat, centro_lon = -27.4692, -58.8306
    zoom_val = 11.5
    if barrio_sel != "Todos los barrios" and not df_filtrado.empty:
        centro_lat = float(df_filtrado["LATITUD"].mean())
        centro_lon = float(df_filtrado["LONGITUD"].mean())
        zoom_val = 13.5

    colores_mapa = {
        "Secundaria": "#EF553B",
        "Primaria": "#2ECC71",
        "Inicial": "#F39C12",
        "Superior": "#9B59B6",
        "Otro / Especial": "#3498DB"
    }

    # Compatibilidad universal Plotly (v5 y v6+)
    kwargs_mapa = {
        "data_frame": df_filtrado,
        "lat": "LATITUD",
        "lon": "LONGITUD",
        "color": "Nivel_Oferta",
        "color_discrete_map": colores_mapa,
        "hover_name": "fna",
        "hover_data": {"BARRIOS_CORREGIDO": True, "cue": True, "LATITUD": False, "LONGITUD": False, "Nivel_Oferta": False},
        "zoom": zoom_val,
        "center": {"lat": centro_lat, "lon": centro_lon},
        "height": 450
    }

    if hasattr(px, "scatter_map"):
        fig_mapa = px.scatter_map(**kwargs_mapa, map_style="open-street-map")
    else:
        fig_mapa = px.scatter_mapbox(**kwargs_mapa, mapbox_style="open-street-map")

    # Polígonos de delimitación de barrios
    try:
        geojson_barrios = json.loads(gdf_barrios.to_json())
        capas_barrio = [
            {
                "sourcetype": "geojson",
                "source": geojson_barrios,
                "type": "fill",
                "color": "rgba(52, 152, 219, 0.12)",
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
        if hasattr(px, "scatter_map"):
            fig_mapa.update_layout(map_layers=capas_barrio)
        else:
            fig_mapa.update_layout(mapbox_layers=capas_barrio)
    except Exception:
        pass

    fig_mapa.update_layout(margin=dict(l=0, r=0, t=10, b=10), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    st.plotly_chart(fig_mapa, use_container_width=True)

with col_grafico:
    st.subheader("Distribución de Escuelas por Barrio (Capital).")
    
    top_barrios = df_filtrado["BARRIOS_CORREGIDO"].value_counts().head(14).reset_index()
    top_barrios.columns = ["Barrio", "Cantidad_Escuelas"]
    
    fig_barras = px.bar(
        top_barrios,
        x="Cantidad_Escuelas",
        y="Barrio",
        orientation="h",
        color_discrete_sequence=["#5cb85c"]  # Tono verde característico de tu panel en Grafana
    )
    fig_barras.update_layout(
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=10, t=10, b=10),
        xaxis_title="Cantidad de Escuelas",
        yaxis_title="",
        height=450
    )
    st.plotly_chart(fig_barras, use_container_width=True)

st.markdown("---")

# 5. Fila Inferior: Tabla INDEC vs Oferta y Gráfico de Torta por Niveles
col_tabla, col_dona = st.columns([1.2, 0.8])

with col_tabla:
    st.subheader("Demanda INDEC vs Oferta de Establecimientos (Capital)")
    st.dataframe(
        df_demanda,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Nivel": "Nivel Educativo",
            "Alumnos_INDEC": st.column_config.NumberColumn("Alumnos INDEC (Demanda)", format="%d"),
            "Escuelas": st.column_config.NumberColumn("Establecimientos", format="%d"),
            "Ratio_Alumnos_x_Escuela": st.column_config.NumberColumn("Ratio Alumnos / Escuela", format="%d")
        }
    )

with col_dona:
    st.subheader("Proporción por Nivel de Oferta")
    dist_niveles = df_filtrado["Nivel_Oferta"].value_counts().reset_index()
    dist_niveles.columns = ["Nivel", "Cantidad"]
    
    fig_dona = px.pie(
        dist_niveles,
        names="Nivel",
        values="Cantidad",
        hole=0.45,
        color="Nivel",
        color_discrete_map=colores_mapa
    )
    fig_dona.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=260)
    st.plotly_chart(fig_dona, use_container_width=True)
