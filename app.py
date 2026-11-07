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
        df_esc, MAPA_MODALIDADES, "Sin especificar"
    )

    gdf_barrios = obtener_geometrias_barrios(ruta_geojson)
    gdf_barrios_plot = gdf_barrios.copy()
    gdf_barrios_plot["geometry"] = gdf_barrios_plot.geometry.simplify(
        tolerance=0.00008,
        preserve_topology=True,
    )

    puntos_validos = df_esc[
        df_esc["LATITUD"].between(-90, 90)
        & df_esc["LONGITUD"].between(-180, 180)
    ][["_row_id", "LATITUD", "LONGITUD"]].copy()

    mapa_registro_barrio: dict[int, tuple[str, ...]] = {}
    if not puntos_validos.empty:
        gdf_puntos = gpd.GeoDataFrame(
            puntos_validos[["_row_id"]].copy(),
            geometry=gpd.points_from_xy(
                puntos_validos["LONGITUD"],
                puntos_validos["LATITUD"],
            ),
            crs="EPSG:4326",
        )
        cruce = gpd.sjoin(
            gdf_puntos,
            gdf_barrios[["NOMBRE_BARRIO_GEOJSON", "geometry"]],
            how="left",
            predicate="within",
        )
        cruce = cruce.dropna(subset=["NOMBRE_BARRIO_GEOJSON"])
        if not cruce.empty:
            agrupado = cruce.groupby("_row_id")["NOMBRE_BARRIO_GEOJSON"].agg(
                lambda valores: tuple(sorted(set(valores.astype(str))))
            )
            mapa_registro_barrio = {
                int(indice): nombres for indice, nombres in agrupado.items()
            }

    totales_nivel = {}
    for columna, etiqueta in MAPA_NIVELES.items():
        totales_nivel[etiqueta] = (
            int(es_uno(df_esc[columna]).sum()) if columna in df_esc.columns else 0
        )

    demanda = {
        "Nivel": [
            "Educación Temprana / CDI",
            "Inicial",
            "Primaria",
            "Secundaria",
            "Superior",
        ],
        "Alumnos_INDEC": [7321, 11116, 46040, 50204, 16331],
        "Escuelas": [
            totales_nivel.get("Educación Temprana / CDI", 0),
            totales_nivel.get("Inicial", 0),
            totales_nivel.get("Primaria", 0),
            totales_nivel.get("Secundaria", 0),
            totales_nivel.get("Superior", 0),
        ],
    }
    df_demanda = pd.DataFrame(demanda)
    df_demanda["Ratio_Alumnos_x_Escuela"] = (
        df_demanda["Alumnos_INDEC"]
        .div(df_demanda["Escuelas"].replace(0, pd.NA))
        .round(0)
        .astype("Int64")
    )

    return (
        df_esc,
        gdf_barrios,
        gdf_barrios_plot,
        mapa_registro_barrio,
        df_demanda,
    )


# -----------------------------------------------------------------------------
# Comprobación de archivos requeridos
# -----------------------------------------------------------------------------
if not ARCHIVO_ESCUELAS.exists():
    st.error("No se encontró **ESCUELAS_DEFINITIVA.xlsx**.")
    st.stop()

if not ARCHIVO_BARRIOS.exists():
    st.error("No se encontró **BarriosCorrientes.geojson**.")
    st.stop()

marca_excel = (ARCHIVO_ESCUELAS.stat().st_mtime_ns, ARCHIVO_ESCUELAS.stat().st_size)
marca_geojson = (ARCHIVO_BARRIOS.stat().st_mtime_ns, ARCHIVO_BARRIOS.stat().st_size)

try:
    (
        df_escuelas,
        gdf_barrios,
        gdf_barrios_plot,
        mapa_registro_barrio,
        df_demanda,
    ) = cargar_datos(
        str(ARCHIVO_ESCUELAS),
        marca_excel,
        str(ARCHIVO_BARRIOS),
        marca_geojson,
    )
except Exception as error:
    st.error(f"No se pudieron preparar los datos: {error}")
    st.stop()


# -----------------------------------------------------------------------------
# 1. Filtros laterales (multiselect vacíos por defecto)
# -----------------------------------------------------------------------------
st.sidebar.title("Filtros del tablero")

barrios_disponibles = sorted(
    df_escuelas["BARRIOS_CORREGIDO"].dropna().astype(str).unique().tolist()
)
barrios_sel = st.sidebar.multiselect(
    "Seleccionar barrio(s):",
    options=barrios_disponibles,
    placeholder="Todos los barrios (o seleccioná uno o más)",
)

niveles_validos = [
    (columna, etiqueta)
    for columna, etiqueta in MAPA_NIVELES.items()
    if columna in df_escuelas.columns
]
nombres_niveles_disponibles = [etiqueta for _, etiqueta in niveles_validos]

niveles_sel = st.sidebar.multiselect(
    "Filtrar por niveles:",
    options=nombres_niveles_disponibles,
    default=[],
    placeholder="Seleccionar uno o más niveles...",
)

orden_modalidades = [
    "Común",
    "Especial",
    "Técnica",
    "Artística",
    "Rural",
    "Jóvenes y Adultos (EPJA)",
    "Contexto de Encierro",
    "Bilingüe",
]
modalidades_presentes = [
    modalidad
    for modalidad in orden_modalidades
    if modalidad in set(df_escuelas["Modalidad_Display"].dropna().astype(str))
]

modalidades_sel = st.sidebar.multiselect(
    "Filtrar por modalidad:",
    options=modalidades_presentes,
    default=[],
    placeholder="Seleccionar modalidad(es)...",
)

# -----------------------------------------------------------------------------
# Lógica de filtrado progresivo y cálculo de cobertura dinámica
# -----------------------------------------------------------------------------
df_nivel_modalidad = df_escuelas

if niveles_sel:
    mascara_niveles = pd.Series(False, index=df_nivel_modalidad.index)
    for columna, etiqueta in MAPA_NIVELES.items():
        if etiqueta in niveles_sel and columna in df_nivel_modalidad.columns:
            mascara_niveles |= es_uno(df_nivel_modalidad[columna])
    df_nivel_modalidad = df_nivel_modalidad[mascara_niveles]

if modalidades_sel:
    df_nivel_modalidad = df_nivel_modalidad[
        df_nivel_modalidad["Modalidad_Display"].isin(modalidades_sel)
    ]

ids_filtrados = set(df_nivel_modalidad["_row_id"].astype(int).tolist())
barrios_con_oferta = {
    barrio
    for row_id in ids_filtrados
    for barrio in mapa_registro_barrio.get(row_id, ())
}
barrios_totales = set(gdf_barrios["NOMBRE_BARRIO_GEOJSON"].astype(str))
nombres_sin_oferta_dinamico = sorted(barrios_totales - barrios_con_oferta)
total_sin_oferta_dinamico = len(nombres_sin_oferta_dinamico)
gdf_barrios_sin_escuelas = gdf_barrios_plot[
    gdf_barrios_plot["NOMBRE_BARRIO_GEOJSON"].isin(nombres_sin_oferta_dinamico)
].copy()

df_filtrado = df_nivel_modalidad
if barrios_sel:
    df_filtrado = df_filtrado[
        df_filtrado["BARRIOS_CORREGIDO"].astype(str).isin(barrios_sel)
    ]
df_filtrado = df_filtrado.copy()


# -----------------------------------------------------------------------------
# 2. Encabezado y KPIs Dinámicos con Tooltip Metodológico
# -----------------------------------------------------------------------------
st.title("Establecimientos Educativos en Corrientes - INDEC vs Oferta")

if len(niveles_sel) == 1:
    nivel_activo = niveles_sel[0]
    poblacion_kpi = POBLACION_INDEC_NIVELES.get(nivel_activo, {}).get("texto", POBLACION_INDEC_TOTAL)
    etiqueta_poblq = f"Población ({nivel_activo})"
    
    # Obtener el ratio específico del nivel activo desde el dataframe de demanda
    fila_demanda_nivel = df_demanda[df_demanda["Nivel"] == nivel_activo]
    if not fila_demanda_nivel.empty:
        val_ratio = fila_demanda_nivel.iloc[0]["Ratio_Alumnos_x_Escuela"]
        ratio_kpi = f"{val_ratio:,}".replace(",", ".") if pd.notna(val_ratio) else "Sin datos"
    else:
        ratio_kpi = "-"
    etiqueta_ratio = f"Ratio alumnos/escuela ({nivel_activo})"
elif len(niveles_sel) > 1:
    poblacion_kpi = "Múltiple"
    etiqueta_poblq = "Población Escolarizada"
    ratio_kpi = "-"
    etiqueta_ratio = "Ratio alumnos / escuela"
else:
    poblacion_kpi = POBLACION_INDEC_TOTAL
    etiqueta_poblq = "Población Escolarizada"
    ratio_kpi = "-"
    etiqueta_ratio = "Ratio alumnos / escuela"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Establecimientos filtrados", f"{len(df_filtrado):,}".replace(",", "."))

k2.metric(
    etiqueta_poblq,
    poblacion_kpi,
    help="⚠️ Dato correspondiente al Censo INDEC 2022 (departamento Capital). Nota metodológica: no se encuentra desagregado por barrio ni por modalidad."
)

k3.metric(etiqueta_ratio, ratio_kpi, help="Relación entre la demanda poblacional del INDEC y la oferta de establecimientos para el nivel seleccionado.")

if not df_filtrado.empty:
    conteo_barrios = df_filtrado["BARRIOS_CORREGIDO"].value_counts()
    top_barrio = conteo_barrios.index[0]
    top_cantidad = int(conteo_barrios.iloc[0])
    k4.metric("Mayor concentración", f"{top_barrio} ({top_cantidad})")
else:
    k4.metric("Mayor concentración", "Sin datos")

etiqueta_sin_oferta = "Barrios sin oferta" if not niveles_sel else f"Barrios sin oferta ({', '.join(niveles_sel)})"
k5.metric(
    etiqueta_sin_oferta,
    total_sin_oferta_dinamico,
    help="Barrios catastrales que no registran establecimientos activos según los niveles y modalidades filtrados.",
)

st.markdown("---")

# -----------------------------------------------------------------------------
# Coordenadas de enfoque del mapa (manejadas de forma limpia mediante filtros)
# -----------------------------------------------------------------------------
centro = dict(CENTRO_CORRIENTES)
zoom_val = ZOOM_INICIAL

if barrios_sel and not df_filtrado.empty:
    df_puntos_zoom = df_filtrado.dropna(subset=["LATITUD", "LONGITUD"])
    if not df_puntos_zoom.empty:
        centro = {
            "lat": float(df_puntos_zoom["LATITUD"].mean()),
            "lon": float(df_puntos_zoom["LONGITUD"].mean()),
        }
        zoom_val = 12.8 if len(barrios_sel) > 1 else 13.5


# -----------------------------------------------------------------------------
# 3. Mapa y gráficos superiores
# -----------------------------------------------------------------------------
col_mapa, col_grafico = st.columns([1.1, 0.9])

with col_mapa:
    st.subheader("Distribución territorial de establecimientos")

    c_capas1, c_capas2, c_capas3, c_capas4 = st.columns(4)
    ver_barrios = c_capas1.checkbox("Límites de barrios", value=True)
    ver_sin_oferta = c_capas2.checkbox("Destacar sin oferta", value=True)
    ver_escuelas = c_capas3.checkbox("Ver establecimientos", value=True)
    criterio_color = c_capas4.radio(
        "Colorear por:",
        ["Nivel educativo", "Modalidad"],
        horizontal=True,
    )

    df_puntos = df_filtrado[
        df_filtrado["LATITUD"].between(-90, 90)
        & df_filtrado["LONGITUD"].between(-180, 180)
    ].dropna(subset=["LATITUD", "LONGITUD"]).copy()

    campo_color = "Nivel_Oferta" if criterio_color == "Nivel educativo" else "Modalidad_Display"
    paleta_actual = COLORES_NIVELES if criterio_color == "Nivel educativo" else COLORES_MODALIDADES
    etiqueta_color = "Nivel educativo" if criterio_color == "Nivel educativo" else "Modalidad"

    if ver_escuelas and not df_puntos.empty:
        argumentos_mapa = {
            "data_frame": df_puntos,
            "lat": "LATITUD",
            "lon": "LONGITUD",
            "color": campo_color,
            "color_discrete_map": paleta_actual,
            "hover_name": "NOMBRE_DISPLAY",
            "custom_data": [
                "CUE_DISPLAY",
                "BARRIOS_CORREGIDO",
                "Niveles_Disponibles",
                "Modalidades_Disponibles",
            ],
            "center": centro,
            "zoom": zoom_val,
            "height": 520,
            "labels": {campo_color: etiqueta_color},
        }
        if hasattr(px, "scatter_map"):
            fig_mapa = px.scatter_map(
                **argumentos_mapa,
                map_style="open-street-map",
            )
        else:
            fig_mapa = px.scatter_mapbox(
                **argumentos_mapa,
                mapbox_style="open-street-map",
            )

        plantilla_hover = (
            "<b>%{hovertext}</b>"
            "<br><b>CUE:</b> %{customdata[0]}"
            "<br><b>Barrio:</b> %{customdata[1]}"
            "<br><b>Niveles disponibles:</b> %{customdata[2]}"
            "<br><b>Modalidades disponibles:</b> %{customdata[3]}"
            "<extra></extra>"
        )
        for traza in fig_mapa.data:
            traza.update(
                hovertemplate=plantilla_hover,
                marker={"size": 10, "opacity": 0.92},
            )
    else:
        df_vacio = pd.DataFrame(
            {"LATITUD": [centro["lat"]], "LONGITUD": [centro["lon"]]}
        )
        if hasattr(px, "scatter_map"):
            fig_mapa = px.scatter_map(
                df_vacio,
                lat="LATITUD",
                lon="LONGITUD",
                center=centro,
                zoom=zoom_val,
                height=520,
                map_style="open-street-map",
            )
        else:
            fig_mapa = px.scatter_mapbox(
                df_vacio,
                lat="LATITUD",
                lon="LONGITUD",
                center=centro,
                zoom=zoom_val,
                height=520,
                mapbox_style="open-street-map",
            )
        for traza in fig_mapa.data:
            traza.update(opacity=0, showlegend=False, hoverinfo="skip")

    clase_traza_mapa = getattr(go, "Scattermap", None)
    if clase_traza_mapa is None:
        clase_traza_mapa = getattr(go, "Scattermapbox", None)

    if ver_barrios and clase_traza_mapa is not None:
        longitudes_limites = []
        latitudes_limites = []
        for geometria in gdf_barrios_plot.geometry:
            for poligono in extraer_poligonos(geometria):
                x, y = poligono.exterior.xy
                longitudes_limites.extend(list(x) + [None])
                latitudes_limites.extend(list(y) + [None])
                for anillo in poligono.interiors:
                    xi, yi = anillo.xy
                    longitudes_limites.extend(list(xi) + [None])
                    latitudes_limites.extend(list(yi) + [None])
        fig_mapa.add_trace(
            clase_traza_mapa(
                lon=longitudes_limites,
                lat=latitudes_limites,
                mode="lines",
                line={"width": 1.15, "color": "#75A9C8"},
                name="Límites de barrios",
                hoverinfo="skip",
            )
        )

    if ver_sin_oferta and not gdf_barrios_sin_escuelas.empty and clase_traza_mapa is not None:
        longitudes_sin_oferta = []
        latitudes_sin_oferta = []
        for geometria in gdf_barrios_sin_escuelas.geometry:
            for poligono in extraer_poligonos(geometria):
                x, y = poligono.exterior.xy
                longitudes_sin_oferta.extend(list(x) + [None])
                latitudes_sin_oferta.extend(list(y) + [None])
        if longitudes_sin_oferta:
            fig_mapa.add_trace(
                clase_traza_mapa(
                    lon=longitudes_sin_oferta,
                    lat=latitudes_sin_oferta,
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(239, 68, 68, 0.20)",
                    line={"width": 1.7, "color": COLOR_SIN_OFERTA},
                    name="Barrios sin oferta",
                    legendgroup="sin_oferta",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

    fig_mapa.update_layout(
        template="plotly_dark",
        margin={"l": 0, "r": 0, "t": 12, "b": 0},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"color": COLOR_TEXTO, "size": 11},
            "bgcolor": "rgba(11, 18, 32, 0.72)",
        },
        hovermode="closest",
        font={"color": COLOR_TEXTO},
    )

    st.plotly_chart(
        fig_mapa,
        use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": False},
        key="mapa_interactivo",
    )

with col_grafico:
    st.subheader("Top 15: distribución de establecimientos por barrio")
    top_barrios = (
        df_filtrado["BARRIOS_CORREGIDO"]
        .dropna()
        .astype(str)
        .value_counts()
        .head(15)
        .rename_axis("Barrio")
        .reset_index(name="Cantidad_Escuelas")
    )

    if not top_barrios.empty:
        fig_barras = px.bar(
            top_barrios,
            x="Cantidad_Escuelas",
            y="Barrio",
            orientation="h",
            text_auto=True,
            color_discrete_sequence=[COLOR_CELESTE],
        )
        fig_barras.update_layout(
            template="plotly_dark",
            yaxis={"autorange": "reversed"},
            margin={"l": 0, "r": 10, "t": 10, "b": 10},
            xaxis_title="Cantidad de establecimientos",
            yaxis_title="",
            height=520,
            font={"color": COLOR_TEXTO},
        )
        st.plotly_chart(fig_barras, use_container_width=True)
    else:
        st.info("No hay establecimientos para los filtros seleccionados.")

st.markdown("---")


# -----------------------------------------------------------------------------
# 4. Demanda INDEC vs oferta y distribución
# -----------------------------------------------------------------------------
col_tabla, col_dona = st.columns([1.2, 0.8])

with col_tabla:
    st.subheader("Demanda INDEC vs oferta de establecimientos (Capital)")
    st.dataframe(
        df_demanda,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Nivel": "Nivel educativo",
            "Alumnos_INDEC": st.column_config.NumberColumn(
                "Alumnos INDEC (demanda)", format="%d"
            ),
            "Escuelas": st.column_config.NumberColumn(
                "Establecimientos", format="%d"
            ),
            "Ratio_Alumnos_x_Escuela": st.column_config.NumberColumn(
                "Ratio alumnos / establecimiento", format="%d"
            ),
        },
    )

with col_dona:
    if len(barrios_sel) == 1:
        sufijo_barrio = f"- {barrios_sel[0]}"
    elif len(barrios_sel) > 1:
        sufijo_barrio = f"- {len(barrios_sel)} barrios"
    else:
        sufijo_barrio = "- Corrientes Capital"

    if criterio_color == "Nivel educativo":
        st.subheader(f"Distribución por nivel {sufijo_barrio}")
        distribucion = (
            df_filtrado["Nivel_Oferta"].value_counts().rename_axis("Nivel").reset_index(name="Cantidad")
        )
        if not distribucion.empty:
            fig_distribucion = px.pie(
                distribucion,
                names="Nivel",
                values="Cantidad",
                hole=0.45,
                color="Nivel",
                color_discrete_map=COLORES_NIVELES,
            )
            fig_distribucion.update_layout(
                template="plotly_dark",
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                height=320,
                font={"color": COLOR_TEXTO},
            )
            st.plotly_chart(fig_distribucion, use_container_width=True)
        else:
            st.info("No hay datos para construir la distribución por nivel.")
    else:
        st.subheader(f"Oferta por modalidad {sufijo_barrio}")
        distribucion = (
            df_filtrado["Modalidad_Display"]
            .value_counts()
            .rename_axis("Modalidad")
            .reset_index(name="Cantidad")
        )
        if not distribucion.empty:
            fig_distribucion = px.bar(
                distribucion,
                x="Cantidad",
                y="Modalidad",
                orientation="h",
                text_auto=True,
                color="Modalidad",
                color_discrete_map=COLORES_MODALIDADES,
            )
            fig_distribucion.update_layout(
                template="plotly_dark",
                yaxis={"autorange": "reversed"},
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                xaxis_title="Cantidad de establecimientos",
                yaxis_title="",
                height=320,
                font={"color": COLOR_TEXTO},
            )
            st.plotly_chart(fig_distribucion, use_container_width=True)
        else:
            st.info("No hay datos para construir la distribución por modalidad.")


# -----------------------------------------------------------------------------
# 5. Metodología, Fuentes y Limitaciones actualizadas
# -----------------------------------------------------------------------------
st.markdown("---")
with st.expander("📚 Metodología, fuentes y limitaciones del tablero"):
    st.markdown(
        """
### 1. Fuentes y fechas de datos
- **Padrón de establecimientos:** Portal de Datos Abiertos de la Municipalidad de Corrientes (dataset de establecimientos educativos) https://datos.ciudaddecorrientes.gov.ar/dataset/establecimientos-educativos. Última actualización registrada en 2025 (frecuencia de actualización anual). De tres dataset originales se conservó el que contenia todos los establecimientos. Del total de registros, se depuraron y procesaron estrictamente **332 establecimientos educativos formales válidos** (excluyendo educación no formal y servicios sin oferta en los niveles principales).
- **Población y demanda (INDEC):** Censo Nacional de Población, Hogares y Viviendas 2022, INDEC (Apartado "Educación", Cuadro 2.7.3 - Provincia de Corrientes, departamento Capital). https://www.indec.gob.ar/indec/web/Nivel4-Tema-2-41-165. Corresponde a la población en viviendas particulares que asiste a algún establecimiento educativo, abierta por nivel.
- **Geometrías:** límites barriales de la Municipalidad de Corrientes provistos por el tutor de prácticas a través de mensajería instantánea, los cuales fueron procesados, unificados (*dissolve*) y simplificados utilizando **QGIS** para estandarizar las unidades barriales como capas vectoriales optimizadas.

### 2. Supuestos y criterios metodológicos
- **Conteo por nivel:** se utiliza el criterio de *establecimientos que ofrecen el nivel*, permitiendo contar adecuadamente los edificios que albergan más de un nivel educativo (por ejemplo, escuelas con anexo de jardín) sin sumarlos de forma excluyente.
- **Tramos etarios / niveles:**
  * *Materna / CDI:* 0 a 3 años (7.321 asistencias).
  * *Inicial:* salas 4 y 5 (11.116 asistencias).
  * *Primaria:* 46.040 asistencias.
  * *Secundaria:* 50.204 asistencias.
  * *Superior / terciario:* 16.331 asistencias.
- **Barrios sin oferta dinámicos:** se identifican mediante una relación espacial vectorial (*Spatial Join*) entre las coordenadas de los establecimientos filtrados y los polígonos barriales. Cuando el usuario selecciona un nivel específico (ej. Secundaria), el contador suma de forma estricta los barrios que carecen de establecimientos habilitados para dicho nivel.

### 3. Límites del tablero
- **Demanda poblacional (INDEC 2022) y Superior Universitario/posgrado:** La base de datos municipal no contiene relevamiento de educación formal de grado universitario o posgrados amplios, lo que excluye del conteo de población asistente a estos últimos y reduce la referencia de 161.863 a **131.012 estudiantes**, logrando así un cruce fiel en función de los niveles que coinciden en ambas bases de datos. Adicionalmente, se aclara que las cifras censales de demanda están estructuradas por niveles tradicionales, por lo que la población de Jóvenes y Adultos (EPJA) se encuentra implícitamente contemplada dentro de los totales generales de primaria y secundaria del Censo, mientras que en la oferta municipal se registra de forma desagregada por modalidad.
- **Coordenadas:** el 82% de los establecimientos en el padrón oficial poseen ubicación marcada como "aproximada", o bien proceden de fuentes abiertas municipales, lo cual puede generar leves desplazamientos espaciales en los límites vecinales al realizar el cruce.
- **Casos rurales o periféricos:** establecimientos rurales específicos o ubicados en parajes y asentamientos alejados se evalúan según su coordenada frente al polígono correspondiente.
- **Desfase temporal (INDEC 2022 vs. padrón 2025):** se cruzan datos de demanda poblacional del Censo Nacional 2022 con un padrón de oferta educativa actualizado a 2025. Esto implica que la foto demográfica y la infraestructura escolar no corresponden estrictamente al mismo año calendario, lo cual debe considerarse al analizar ratios de cobertura en zonas de expansión urbana.
"""
    )
