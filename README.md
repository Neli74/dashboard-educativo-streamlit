# Streamlit
DASHBOARD EDUCACIÓN Y TERRITORIO - CORRIENTES
PAQUETE AJUSTADO TRAS VALIDAR ESCUELAS_DEFINITIVA.xlsx

CONTENIDO
- app.py: código optimizado, adaptado a GeoJSON y ajustado a las columnas reales del Excel.
- BarriosCorrientes.geojson: límites barriales corregidos.
- requirements.txt: dependencias.
- .streamlit/config.toml: tema oscuro con acentos celestes.

ARCHIVO DE DATOS
Mantener ESCUELAS_DEFINITIVA.xlsx en la misma carpeta que app.py. No se incluye en este ZIP.
La aplicación ya no necesita barriosmunicipalidad.shp ni sus archivos auxiliares.

VALIDACIÓN DE LA BASE ESCOLAR
- 365 filas y 20 columnas en Hoja1.
- 332 registros tienen al menos un indicador de nivel educativo. Los otros 33 no tienen banderas de nivel y quedan fuera cuando están seleccionados los filtros de niveles (comportamiento actual del tablero).
- Hay 2 registros con coordenadas fuera de rango. Se conservan en los datos y en los conteos, pero no se dibujan en el mapa.
- Hay 3 registros sin BARRIOS_CORREGIDO.
- 20 puntos con coordenadas válidas no quedan dentro de ninguno de los polígonos del GeoJSON. Se muestran como puntos, pero no se asignan a un polígono para el cálculo espacial de barrios sin oferta.
- Se incorporó M. COMUN al tooltip para mostrar también esa modalidad cuando está activa. Los registros sin ninguna bandera de modalidad se presentan como "Sin especificar".

ESTRUCTURA ESPERADA DEL REPOSITORIO
/
  app.py
  BarriosCorrientes.geojson
  ESCUELAS_DEFINITIVA.xlsx
  requirements.txt
  /.streamlit/config.toml

STREAMLIT COMMUNITY CLOUD
- Main file path: app.py
- Mantener todos los archivos anteriores en la misma rama.
