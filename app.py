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
        
    # Selección de columna con nombres de texto
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

    # Cruce espacial liviano
    escuelas_geo = df_esc.dropna(subset=["LATITUD", "LONGITUD"]).copy()
    gdf_escuelas_pts = gpd.GeoDataFrame(
        escuelas_geo,
        geometry=gpd.points_from_xy(escuelas_geo["LONGITUD"], escuelas_geo["LATITUD"]),
        crs="EPSG:4326"
    )
    
    cruce_espacial = gdf_barrios.sjoin(gdf_escuelas_pts, how="left", predicate="contains")
    
    # Identificar nombres de barrios con y sin oferta escolar
    barrios_con_escuelas = cruce_espacial.dropna(subset=["index_right"])["NOMBRE_BARRIO_SHP"].unique()
    todos_los_barrios = gdf_barrios["NOMBRE_BARRIO_SHP"].unique()
    
    nombres_sin_oferta = sorted([b for b in todos_los_barrios if b not in barrios_con_escuelas])
    total_barrios_sin_oferta = len(nombres_sin_oferta)

    gdf_barrios_sin_escuelas = gdf_barrios[gdf_barrios["NOMBRE_BARRIO_SHP"].isin(nombres_sin_oferta)].copy()

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
    
    return df_esc, gdf_barrios, gdf_barrios_sin_escuelas, total_barrios_sin_oferta, nombres_sin_oferta, df_demanda, cols_sin_geometria, col_nombre_shp

df_escuelas, gdf_barrios, gdf_barrios_sin_escuelas, total_sin_oferta, lista_sin_oferta, df_demanda, cols_disponibles, col_usada = cargar_datos()

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
    "Contexto de Encierro", 
    "Bilingüe"
]
modalidades_presentes = [m for m in modalidades_unicas if m in df_escuelas["Modalidad_Display"].values]

modalidades_sel = st.sidebar.multiselect(
    "Filtrar por Modalidad:",
    options=modalidades_presentes,
    default=modalidades_presentes
)

st.sidebar.markdown("---")
st.sidebar.caption(f"📍 **Columna de barrios leída:** `{col_usada}`")
st.sidebar.caption(f"📁 **Columnas detectadas:** {', '.join(cols_disponibles)}")

# Aplicación de filtros
df_filtrado = df_escuelas.copy()

if barrios_sel:
    df_filtrado = df_filtrado[df_filtrado["BARRIOS_CORREGIDO"].isin(barrios_sel)]

if niveles_sel:
    cols_niveles_activas = [col for col, nom in mapa_niveles.items() if nom in niveles_sel and col in df_filtrado.columns]
    if cols_niveles_activas:
        df_filtrado = df_filtrado[df_filtrado[cols_niveles_activas].sum(axis=1) > 0]

if modalidades_sel:
    df_filtrado = df_filtrado[df_filtrado["Modalidad_Display"].isin(modalidades_sel)]

# 3. Encabezado y KPIs
st.title("Tablero Educativo Corrientes - INDEC vs Oferta")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Establecimientos Filtrados", len(df_filtrado))
k2.metric("Población Escolarizada", "161.863")
k3.metric("Mayor Demanda", "Secundaria (50.204)")
if not df_filtrado.empty:
    top_b = df_filtrado["BARRIOS_CORREGIDO"].value_counts().index[0]
    top_c = df_filtrado["BARRIOS_CORREGIDO"].value_counts().iloc[0]
    k4.metric("Mayor concentración", f"{top_b} ({top_c})")
else:
    k4.metric("Mayor concentración", "Sin datos")
k5.metric("Barrios sin Oferta", total_sin_oferta, help="Cantidad de barrios catastrales sin escuelas registradas")

st.markdown("---")

# 4. Sección de Mapa y Gráficos
col_mapa, col_grafico = st.columns([1.1, 0.9])

with col_mapa:
    st.subheader("Distribución Territorial de Escuelas")
    
    c_capas1, c_capas2, c_capas3, c_capas4 = st.columns(4)
    ver_barrios = c_capas1.checkbox("Límites de Barrios", value=True)
    ver_sin_oferta = c_capas2.checkbox("Destacar Sin Oferta", value=True)
    ver_escuelas = c_capas3.checkbox("Ver Escuelas", value=True)
    criterio_color = c_capas4.radio("Colorear por:", ["Nivel Educativo", "Modalidad"], horizontal=True)

    centro_lat, centro_lon = -27.4692, -58.8306
    zoom_val = 11.5
    if barrios_sel and not df_filtrado.empty:
        centro_lat = float(df_filtrado["LATITUD"].mean())
        centro_lon = float(df_filtrado["LONGITUD"].mean())
        zoom_val = 12.8 if len(barrios_sel) > 1 else 13.5

    paleta_colores = [
        "#E74C3C", "#2ECC71", "#F39C12", "#8E44AD", "#1ABC9C", 
        "#3498DB", "#E67E22", "#95A5A6", "#D35400"
    ]

    campo_color = "Nivel_Oferta" if criterio_color == "Nivel Educativo" else "Modalidad_Display"

    if ver_escuelas and not df_filtrado.empty:
        kwargs_mapa = {
            "data_frame": df_filtrado,
            "lat": "LATITUD",
            "lon": "LONGITUD",
            "color": campo_color,
            "color_discrete_sequence": paleta_colores,
            "hover_name": "fna",
            "custom_data": ["BARRIOS_CORREGIDO", "Nivel_Oferta", "Modalidad_Display", "cue"],
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

    if ver_escuelas and not df_filtrado.empty:
        fig_mapa.update_traces(
            hovertemplate="<b>%{hovertext}</b><br>%{customdata[0]}<br>Nivel: %{customdata[1]}<br>Modalidad: %{customdata[2]}<br>CUE: %{customdata[3]}<extra></extra>"
        )

    traza_cls = getattr(go, "Scattermap", getattr(go, "Scattermapbox", None))

    # 1. Límites generales de barrios
    if ver_barrios and traza_cls:
        lats_barrios, lons_barrios = [], []
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

        fig_mapa.add_trace(
            traza_cls(
                lat=lats_barrios,
                lon=lons_barrios,
                mode="lines",
                line=dict(width=1.5, color="#1B4F72"),
                name="Límites Generales",
                hoverinfo="none"
            )
        )

    # 2. Polígonos con detección de cursor activa (relleno interactivo)
    if ver_sin_oferta and not gdf_barrios_sin_escuelas.empty and traza_cls:
        primera_traza = True
        for _, fila in gdf_barrios_sin_escuelas.iterrows():
            geom = fila.geometry
            nom = fila["NOMBRE_BARRIO_SHP"]
            if geom is None:
                continue
            
            poligonos = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
            for poly in poligonos:
                x, y = poly.exterior.xy
                fig_mapa.add_trace(
                    traza_cls(
                        lat=list(y),
                        lon=list(x),
                        mode="lines",
                        fill="toself",
                        fillcolor="rgba(231, 76, 60, 0.25)",
                        line=dict(width=2, color="#E74C3C"),
                        name="Sin Oferta Escolar" if primera_traza else None,
                        showlegend=primera_traza,
                        hoverinfo="text",
                        text=f"⚠️ <b>Barrio sin oferta escolar:</b><br>{nom}"
                    )
                )
                primera_traza = False

    fig_mapa.update_layout(
        margin=dict(l=0, r=0, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    
    evento_mapa = st.plotly_chart(
        fig_mapa, 
        use_container_width=True, 
        on_select="rerun", 
        selection_mode="points",
        key="mapa_interactivo"
    )

    if evento_mapa and "selection" in evento_mapa and evento_mapa["selection"]["points"]:
        p_sel = evento_mapa["selection"]["points"][0]
        if "point_index" in p_sel and p_sel["point_index"] < len(df_filtrado):
            escuela_tocada = df_filtrado.iloc[p_sel["point_index"]]
            st.success(
                f"🏫 **Establecimiento:** {escuela_tocada['fna']}  \n"
                f"🏘️ **Barrio:** {escuela_tocada['BARRIOS_CORREGIDO']}  \n"
                f"📋 **CUE:** {escuela_tocada['cue']} | **Nivel:** {escuela_tocada['Nivel_Oferta']} | **Modalidad:** {escuela_tocada['Modalidad_Display']}"
            )

    if lista_sin_oferta:
        with st.expander(f"⚠️ Ver lista detallada de barrios sin oferta escolar ({total_sin_oferta})"):
            st.write(", ".join(lista_sin_oferta))

with col_grafico:
    st.subheader("Distribución de Escuelas por Barrio (Capital)")
    
    top_barrios = df_filtrado["BARRIOS_CORREGIDO"].value_counts().head(14).reset_index()
    top_barrios.columns = ["Barrio", "Cantidad_Escuelas"]
    
    fig_barras = px.bar(
        top_barrios,
        x="Cantidad_Escuelas",
        y="Barrio",
        orientation="h",
        text_auto=True,
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

# 5. Fila Inferior: Demanda INDEC vs Oferta y Proporción
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
    if len(barrios_sel) == 1:
        sufijo_b = f"- {barrios_sel[0]}"
    elif len(barrios_sel) > 1:
        sufijo_b = f"- {len(barrios_sel)} Barrios"
    else:
        sufijo_b = "- Toda la Capital"

    if criterio_color == "Nivel Educativo":
        st.subheader(f"Distribución por Nivel {sufijo_b}")
        dist = df_filtrado["Nivel_Oferta"].value_counts().reset_index()
        dist.columns = ["Nivel", "Cantidad"]
        fig_sec = px.pie(
            dist,
            names="Nivel",
            values="Cantidad",
            hole=0.45,
            color_discrete_sequence=paleta_colores
        )
        fig_sec.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
    else:
        st.subheader(f"Oferta por Modalidad {sufijo_b}")
        dist = df_filtrado["Modalidad_Display"].value_counts().reset_index()
        dist.columns = ["Modalidad", "Cantidad"]
        
        fig_sec = px.bar(
            dist,
            x="Cantidad",
            y="Modalidad",
            orientation="h",
            text_auto=True,
            color_discrete_sequence=["#3498DB"]
        )
        fig_sec.update_layout(
            yaxis=dict(autorange="reversed"),
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="Cantidad de Establecimientos",
            yaxis_title="",
            height=300
        )

    st.plotly_chart(fig_sec, use_container_width=True)
