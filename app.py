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
    ver_escuelas = c_capas2.checkbox("Ver Establecimientos", value=True)
    criterio_color = c_capas3.radio("Colorear por:", ["Nivel Educativo", "Modalidad"], horizontal=True)

    centro_lat, centro_lon = -27.4692, -58.8306
    zoom_val = 11.5
    if barrio_sel != "Todos los barrios" and not df_filtrado.empty:
        centro_lat = float(df_filtrado["LATITUD"].mean())
        centro_lon = float(df_filtrado["LONGITUD"].mean())
        zoom_val = 13.5

    paleta_colores = [
        "#E74C3C",  # Rojo / Secundaria
        "#2ECC71",  # Verde / Primaria
        "#F39C12",  # Naranja / Inicial
        "#8E44AD",  # Violeta / Temprana
        "#1ABC9C",  # Turquesa
        "#3498DB",  # Azul
        "#E67E22",  # Cobre
        "#95A5A6"   # Gris
    ]

    campo_color = "Nivel_Oferta" if criterio_color == "Nivel Educativo" else "Modalidad_Display"

    # Crear mapa base con puntos o coordenadas neutras
   if ver_escuelas and not df_filtrado.empty:
        kwargs_mapa = {
            "data_frame": df_filtrado,
            "lat": "LATITUD",
            "lon": "LONGITUD",
            "color": campo_color,
            "color_discrete_sequence": paleta_colores,
            "hover_name": "fna",
            "hover_data": {"BARRIOS_CORREGIDO": True, "cue": True, "LATITUD": False, "LONGITUD": False, campo_color: False},
            "labels": {"BARRIOS_CORREGIDO": "Barrio", "cue": "CUE"},
            "zoom": zoom_val,
            "center": {"lat": centro_lat, "lon": centro_lon},
            "height": 470
        }
       
    else:
        df_vacio = pd.DataFrame({"LATITUD": [centro_lat], "LONGITUD": [centro_lon]})
        kwargs_mapa = {
            "data_frame": df_vacio,
            "lat": "LATITUD",
            "lon": "LONGITUD",
            "zoom": zoom_val,
            "center": {"lat": centro_lat, "lon": centro_lon},
            "height": 470,
            "opacity": 0
        }

    if hasattr(px, "scatter_map"):
        fig_mapa = px.scatter_map(**kwargs_mapa, map_style="open-street-map")
    else:
        fig_mapa = px.scatter_mapbox(**kwargs_mapa, mapbox_style="open-street-map")

    # Trazar los límites de los barrios con líneas vectoriales de alta precisión
    if ver_barrios:
        lats_barrios = []
        lons_barrios = []
        for geom in gdf_barrios.geometry:
            if geom is None:
                continue
            if geom.geom_type == "Polygon":
                x, y = geom.exterior.xy
                lons_barrios.extend(x.tolist() + [None])
                lats_barrios.extend(y.tolist() + [None])
            elif geom.geom_type == "MultiPolygon":
                for poly in geom.geoms:
                    x, y = poly.exterior.xy
                    lons_barrios.extend(x.tolist() + [None])
                    lats_barrios.extend(y.tolist() + [None])

        if hasattr(go, "Scattermap"):
            traza_limites = go.Scattermap(
                lat=lats_barrios,
                lon=lons_barrios,
                mode="lines",
                line=dict(width=2, color="#0E6251"),
                name="Límites Barrios",
                hoverinfo="none"
            )
        else:
            traza_limites = go.Scattermapbox(
                lat=lats_barrios,
                lon=lons_barrios,
                mode="lines",
                line=dict(width=2, color="#0E6251"),
                name="Límites Barrios",
                hoverinfo="none"
            )
        fig_mapa.add_trace(traza_limites)

    fig_mapa.update_layout(
        margin=dict(l=0, r=0, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    # Renderizado interactivo con captura de clics
    evento_mapa = st.plotly_chart(
        fig_mapa, 
        use_container_width=True, 
        on_select="rerun", 
        selection_mode="points",
        key="mapa_interactivo"
    )

    # Detalle en pantalla al tocar una escuela
    if evento_mapa and "selection" in evento_mapa and evento_mapa["selection"]["points"]:
        p_sel = evento_mapa["selection"]["points"][0]
        if "point_index" in p_sel and p_sel["point_index"] < len(df_filtrado):
            escuela_tocada = df_filtrado.iloc[p_sel["point_index"]]
            st.success(
                f"🏫 **Establecimiento:** {escuela_tocada['fna']}  \n"
                f"🏘️ **Barrio:** {escuela_tocada['BARRIOS_CORREGIDO']}  \n"
                f"📋 **CUE:** {escuela_tocada['cue']} | **Nivel:** {escuela_tocada['Nivel_Oferta']}"
            )
            
with col_grafico:
    st.subheader("Distribución de Escuelas por Barrio (Capital)")
    
    top_barrios = df_filtrado["BARRIOS_CORREGIDO"].value_counts().head(14).reset_index()
    top_barrios.columns = ["Barrio", "Cantidad_Escuelas"]
    
    fig_barras = px.bar(
        top_barrios,
        x="Cantidad_Escuelas",
        y="Barrio",
        orientation="h",
        color_discrete_sequence=["#27AE60"]
    )
    fig_barras.update_layout(
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=10, t=10, b=10),
        xaxis_title="Cantidad de Escuelas",
        yaxis_title="",
        height=520
    )
    st.plotly_chart(fig_barras, use_container_width=True)

st.markdown("---")

# 5. Fila Inferior: Demanda INDEC vs Oferta y Proporción por Nivel
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
    st.subheader(f"Proporción según {criterio_color}")
    dist = df_filtrado[campo_color].value_counts().reset_index()
    dist.columns = ["Categoria", "Cantidad"]
    
    fig_dona = px.pie(
        dist,
        names="Categoria",
        values="Cantidad",
        hole=0.45,
        color_discrete_sequence=paleta_colores
    )
    fig_dona.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280)
    st.plotly_chart(fig_dona, use_container_width=True)
