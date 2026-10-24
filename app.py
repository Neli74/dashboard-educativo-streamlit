import streamlit as st
import pandas as pd
import geopandas as gpd
import json
import plotly.express as px

st.set_page_config(page_title="Tablero Educativo Corrientes - INDEC vs Oferta", layout="wide")

# 1. Carga y preparación de bases de datos
@st.cache_data
def cargar_datos():
    df_esc = pd.read_excel("ESCUELAS_DEFINITIVA.xlsx")
    
    # Asignar Nivel Educativo representativo
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

    # Identificar columna de Modalidad si existe en la base
    col_mod = None
    for c in ["MODALIDAD", "modalidad", "Modalidad", "MODALIDAD_NORMALIZADA"]:
        if c in df_esc.columns:
            col_mod = c
            break
    if col_mod:
        df_esc["Modalidad_Display"] = df_esc[col_mod].fillna("Sin modalidad asignada").astype(str)
    else:
        df_esc["Modalidad_Display"] = "Común"

    # Cargar polígonos de barrios
    gdf_barrios = gpd.read_file("barriosmunicipalidad.shp")
    if gdf_barrios.crs is None or gdf_barrios.crs != "EPSG:4326":
        gdf_barrios = gdf_barrios.set_crs(epsg=4326, allow_override=True)
        
    # Demanda censal INDEC (Capital)
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

# 2. Barra lateral: Filtros principales
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

# 4. Sección de Mapa y Gráficos (Estilo interactivo con capas)
col_mapa, col_grafico = st.columns([1.1, 0.9])

with col_mapa:
    st.subheader("Distribución Territorial de Escuelas")
    
    # Controles de capas del mapa
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

    # Paleta cromática contrastante y legible
    paleta_colores = [
        "#E74C3C",  # Rojo / Secundaria
        "#2ECC71",  # Verde esmeralda / Primaria
        "#F39C12",  # Naranja ámbar / Inicial
        "#8E44AD",  # Violeta / Superior
        "#1ABC9C",  # Turquesa / Temprana
        "#3498DB",  # Azul eléctrico / Técnica
        "#E67E22",  # Cobre / Especial
        "#95A5A6"   # Gris plata
    ]

    campo_color = "Nivel_Oferta" if criterio_color == "Nivel Educativo" else "Modalidad_Display"

    # Construcción del mapa
    if ver_escuelas and not df_filtrado.empty:
        kwargs_mapa = {
            "data_frame": df_filtrado,
            "lat": "LATITUD",
            "lon": "LONGITUD",
            "color": campo_color,
            "color_discrete_sequence": paleta_colores,
            "hover_name": "fna",
            "hover_data": {"BARRIOS_CORREGIDO": True, "cue": True, "LATITUD": False, "LONGITUD": False, campo_color: False},
            "zoom": zoom_val,
            "center": {"lat": centro_lat, "lon": centro_lon},
            "height": 470
        }
    else:
        # Mapa base neutro si se ocultan las escuelas
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

    # Agregar polígonos si la casilla está marcada
    if ver_barrios:
        try:
            geojson_barrios = json.loads(gdf_barrios.to_json())
            capas_barrio = [
                {
                    "sourcetype": "geojson",
                    "source": geojson_barrios,
                    "type": "fill",
                    "color": "rgba(41, 128, 185, 0.12)",
                    "below": "traces"
                },
                {
                    "sourcetype": "geojson",
                    "source": geojson_barrios,
                    "type": "line",
                    "color": "#1F618D",
                    "line": {"width": 1.4}
                }
            ]
            if hasattr(px, "scatter_map"):
                fig_mapa.update_layout(map_layers=capas_barrio)
            else:
                fig_mapa.update_layout(mapbox_layers=capas_barrio)
        except Exception:
            pass

    fig_mapa.update_layout(
        margin=dict(l=0, r=0, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    st.plotly_chart(fig_mapa, use_container_width=True)

with col_grafico:
    st.subheader("Distribución de Escuelas por Barrio (Capital)")
    
    top_barrios = df_filtrado["BARRIOS_CORREGIDO"].value_counts().head(14).reset_index()
    top_barrios.columns = ["Barrio", "Cantidad_Escuelas"]
    
    fig_barras = px.bar(
        top_barrios,
        x="Cantidad_Escuelas",
        y="Barrio",
        orientation="h",
        color_discrete_sequence=["#27AE60"]  # Verde oscuro estilizado
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

# 5. Fila Inferior: Demanda INDEC vs Capacidad y Dona por Categoría
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
