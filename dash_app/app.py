import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import plotly.express as px
from dash import Dash, dcc, html, dash_table, Input, Output, callback

# 1. Configurar la conexión a la base de datos
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# 2. Leer los datos
# 2. Obtener datos de eventos
def obtener_datos():
    query = """
        SELECT
            uuid,
            evento,
            municipio,
            "eventType",
            clasification,
            fecha_inicio,
            fecha_fin,
            tarifas,
            lugar,
            latitud,
            longitud,
            url
        FROM eventos_culturales
    """
    return pd.read_sql(query, engine)


df = obtener_datos()

# Normalizar coordenadas
df["latitud"] = pd.to_numeric(
    df["latitud"], errors="coerce"
)
df["longitud"] = pd.to_numeric(
    df["longitud"], errors="coerce"
)

# Normalizar fechas
for columna in ["fecha_inicio", "fecha_fin"]:
    df[columna] = pd.to_datetime(
        df[columna], errors="coerce"
    )

# Normalizar valores de filtros
for columna in ["municipio", "eventType", "clasification"]:
    df[columna] = (
        df[columna]
        .fillna("Sin especificar")
        .astype(str)
    )


# ==========================================
# 3. OPCIONES DE FILTROS
# ==========================================

def opciones_filtro(columna):
    valores = sorted(df[columna].unique())

    return [
        {"label": valor, "value": valor}
        for valor in valores
    ]


# ==========================================
# 4. CREAR MAPA
# ==========================================

def crear_mapa(datos):

    df_mapa = datos.dropna(
        subset=["latitud", "longitud"]
    ).copy()

    df_mapa = df_mapa[
        df_mapa["latitud"].between(-90, 90)
        & df_mapa["longitud"].between(-180, 180)
        & ~(
            (df_mapa["latitud"] == 0)
            & (df_mapa["longitud"] == 0)
        )
    ]

    # Conteo de eventos únicos por municipio
    df_mapa["# Eventos"] = (
        df_mapa.groupby("municipio")["uuid"]
        .transform("nunique")
    )

    # Escala: 1 evento = 8 px, 10+ = 30 px
    df_mapa["tamaño_marcador"] = np.interp(
        df_mapa["# Eventos"].clip(1, 10),
        [1, 10],
        [12, 30]
    )

    fig = px.scatter_map(
        df_mapa,
        lat="latitud",
        lon="longitud",
        hover_name="evento",
        hover_data={
            "municipio": True,
            "# Eventos": True,
            "lugar": True,
            "latitud": False,
            "longitud": False,
            "tamaño_marcador": False
        },
        zoom=6,
        center={
            "lat": 29.1,
            "lon": -110.9
        },
        map_style="open-street-map"
    )

    fig.update_traces(
        marker={
            "size": df_mapa["tamaño_marcador"].tolist(),
            "color": "#0077B6",
            "opacity": 0.8
        }
    )

    fig.update_layout(
        height=600,
        margin={
            "l": 0,
            "r": 0,
            "t": 0,
            "b": 0
        },
        showlegend=False
    )

    return fig


# ==========================================
# 5. PREPARAR TABLA
# ==========================================

COLUMNAS_TABLA = [
    "evento",
    "municipio",
    "eventType",
    "clasification",
    "fecha_inicio",
    "fecha_fin",
    "tarifas",
    "lugar"
]

def crear_tabla(datos):

    tabla = datos[COLUMNAS_TABLA].copy()

    # Formatear fechas para visualización
    for columna in ["fecha_inicio", "fecha_fin"]:
        tabla[columna] = tabla[columna].dt.strftime(
            "%d/%m/%Y %H:%M"
        )

    tabla = tabla.fillna("")

    return tabla.to_dict("records")


# ==========================================
# 6. APLICACIÓN DASH
# ==========================================

app = Dash(__name__)
server = app.server

app.title = "Radar Cultural Sonora"

app.layout = html.Div(

    [

        html.H1(
            "Radar de Eventos Culturales",
            style={"textAlign": "center"}
        ),

        html.H3("Filtros"),

        html.Div(
            [

                html.Div(
                    [
                        html.Label("Municipio"),

                        dcc.Dropdown(
                            id="filtro-municipio",
                            options=opciones_filtro("municipio"),
                            multi=True,
                            placeholder="Todos los municipios"
                        )
                    ],
                    style={"flex": "1"}
                ),

                html.Div(
                    [
                        html.Label("Tipo de evento"),

                        dcc.Dropdown(
                            id="filtro-eventType",
                            options=opciones_filtro("eventType"),
                            multi=True,
                            placeholder="Todos los tipos"
                        )
                    ],
                    style={"flex": "1"}
                ),

                html.Div(
                    [
                        html.Label("Clasificación"),

                        dcc.Dropdown(
                            id="filtro-clasification",
                            options=opciones_filtro("clasification"),
                            multi=True,
                            placeholder="Todas las clasificaciones"
                        )
                    ],
                    style={"flex": "1"}
                )

            ],
            style={
                "display": "flex",
                "gap": "20px",
                "marginBottom": "30px"
            }
        ),

        html.H2("Mapa de eventos culturales"),

        dcc.Graph(
            id="mapa-eventos"
        ),

        html.H2("Listado de eventos"),

        html.Div(
            id="contador-eventos",
            style={"marginBottom": "12px"}
        ),

        dash_table.DataTable(
            id="tabla-eventos",

            columns=[
                {"name": col, "id": col}
                for col in COLUMNAS_TABLA
            ],

            page_size=10,

            sort_action="native",

            filter_action="native",

            style_table={
                "overflowX": "auto"
            },

            style_cell={
                "textAlign": "left",
                "padding": "10px",
                "minWidth": "120px",
                "maxWidth": "300px",
                "whiteSpace": "normal"
            },

            style_header={
                "backgroundColor": "#0077B6",
                "color": "white",
                "fontWeight": "bold"
            },

            style_data_conditional=[
                {
                    "if": {"row_index": "odd"},
                    "backgroundColor": "#F4F8FB"
                }
            ]
        )

    ],

    style={
        "maxWidth": "1400px",
        "margin": "40px auto",
        "padding": "20px",
        "fontFamily": "Arial"
    }
)


# ==========================================
# 7. CALLBACK: FILTROS -> MAPA + TABLA
# ==========================================

@callback(
    Output("mapa-eventos", "figure"),
    Output("tabla-eventos", "data"),
    Output("contador-eventos", "children"),

    Input("filtro-municipio", "value"),
    Input("filtro-eventType", "value"),
    Input("filtro-clasification", "value")
)
def actualizar_dashboard(
    municipios,
    tipos,
    clasificaciones
):

    datos = df.copy()

    if municipios:
        datos = datos[
            datos["municipio"].isin(municipios)
        ]

    if tipos:
        datos = datos[
            datos["eventType"].isin(tipos)
        ]

    if clasificaciones:
        datos = datos[
            datos["clasification"].isin(clasificaciones)
        ]

    fig = crear_mapa(datos)

    tabla = crear_tabla(datos)

    contador = (
        f"Total de eventos: {datos['uuid'].nunique()}"
    )

    return fig, tabla, contador


# ==========================================
# 8. INICIAR APLICACIÓN
# ==========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8050,
        debug=False
    )