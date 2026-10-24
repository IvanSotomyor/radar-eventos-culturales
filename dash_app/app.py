import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import plotly.express as px
from dash import Dash, dcc, html, dash_table, Input, Output, callback

# ==========================================
# 1. CONEXIÓN A LA BASE DE DATOS
# ==========================================
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# ==========================================
# 2. OBTENER DATOS
# ==========================================
def obtener_datos():
    query = """
        SELECT
            uuid,
            evento,
            municipio,
            event_type,
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


# ==========================================
# 3. NORMALIZACIÓN
# ==========================================
df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")

for columna in ["fecha_inicio", "fecha_fin"]:
    df[columna] = pd.to_datetime(df[columna], errors="coerce")

for columna in ["municipio", "event_type", "clasification"]:
    df[columna] = df[columna].fillna("Sin especificar").astype(str)


# ==========================================
# 4. OPCIONES DE FILTROS
# ==========================================
def opciones_filtro(columna):
    valores = sorted(df[columna].unique())
    return [{"label": valor, "value": valor} for valor in valores]


# ==========================================
# 5. CREAR MAPA
# ==========================================
def crear_mapa(datos):

    df_mapa = datos.dropna(subset=["latitud", "longitud"]).copy()

    df_mapa = df_mapa[
        df_mapa["latitud"].between(-90, 90)
        & df_mapa["longitud"].between(-180, 180)
        & ~((df_mapa["latitud"] == 0) & (df_mapa["longitud"] == 0))
    ]

    df_mapa = df_mapa.drop_duplicates(
        subset=["uuid", "municipio", "latitud", "longitud"]
    )

    df_mapa["# Eventos"] = (
        df_mapa.groupby("municipio")["uuid"].transform("nunique")
    )

    df_mapa["tamaño_marcador"] = np.interp(
        df_mapa["# Eventos"].clip(1, 10), [1, 10], [12, 30]
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
            "tamaño_marcador": False,
        },
        zoom=6,
        center={"lat": 29.1, "lon": -110.9},
        map_style="open-street-map",
    )

    fig.update_traces(
        marker={
            "size": df_mapa["tamaño_marcador"].tolist(),
            "color": "#0077B6",
            "opacity": 0.8,
        }
    )

    fig.update_layout(
        height=600,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        showlegend=False,
    )

    return fig


# ==========================================
# 5b. GRÁFICO DE BARRAS HORIZONTAL POR MUNICIPIO
# ==========================================
def crear_grafico_municipios(datos):
    conteo = (
        datos.groupby("municipio")["uuid"]
        .nunique()
        .reset_index(name="cantidad")
        .sort_values("cantidad", ascending=True)   # 🔧 ascendente para que el mayor quede arriba
    )

    # Top 15: como está ordenado ascendente, tomamos los últimos 15
    top_n = 15
    if len(conteo) > top_n:
        conteo = conteo.tail(top_n)

    fig = px.bar(
        conteo,
        x="cantidad",          # 🔧 x = cantidad (barras horizontales)
        y="municipio",         # 🔧 y = municipio
        orientation="h",       # 🔧 orientación horizontal
        labels={"cantidad": "Eventos únicos"},   # 🔧 sin label para municipio
        color_discrete_sequence=["#0077B6"],
    )

    fig.update_layout(
        height=600,
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        title="Eventos por municipio",
        yaxis_title=None,      # 🔧 quita el título del eje Y (municipio)
        xaxis_title="Eventos únicos",
    )

    return fig


# ==========================================
# 5c. NUEVO: SERIE DE TIEMPO DE EVENTOS
# ==========================================
def crear_serie_tiempo(datos):
    # Solo filas con fecha válida
    df_t = datos.dropna(subset=["fecha_inicio"]).copy()

    if df_t.empty:
        # Figura vacía con mensaje si no hay datos
        fig = px.line(title="Eventos a lo largo del tiempo")
        fig.update_layout(
            height=400,
            xaxis_title="Fecha",
            yaxis_title="Eventos únicos",
            annotations=[{
                "text": "Sin datos de fecha disponibles",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 16, "color": "#888"},
            }],
        )
        return fig

    # Agrupar por fecha (día) y contar uuid únicos
    df_t["fecha_dia"] = df_t["fecha_inicio"].dt.date
    serie = (
        df_t.groupby("fecha_dia")["uuid"]
        .nunique()
        .reset_index(name="cantidad")
        .sort_values("fecha_dia")
    )

    fig = px.line(
        serie,
        x="fecha_dia",
        y="cantidad",
        markers=True,
        color_discrete_sequence=["#0077B6"],
        line_shape="spline",   # 🔧 curvas suaves
    )

    fig.update_layout(
        height=400,
        margin={"l": 40, "r": 20, "t": 40, "b": 40},
        title="Eventos culturales a lo largo del tiempo",
        xaxis_title="Fecha",
        yaxis_title="Eventos únicos",
    )

    # Mejorar legibilidad del eje X
    fig.update_xaxes(tickformat="%d/%m/%Y", tickangle=-45)

    return fig


# ==========================================
# 6. PREPARAR TABLA
# ==========================================
COLUMNAS_TABLA = [
    "evento",
    "municipio",
    "event_type",
    "clasification",
    "fecha_inicio",
    "fecha_fin",
    "tarifas",
    "lugar",
]


def crear_tabla(datos):
    tabla = datos[COLUMNAS_TABLA].copy()

    for columna in ["fecha_inicio", "fecha_fin"]:
        tabla[columna] = tabla[columna].dt.strftime("%d/%m/%Y %H:%M")

    tabla = tabla.fillna("")
    return tabla.to_dict("records")


# ==========================================
# 7. APLICACIÓN DASH
# ==========================================
app = Dash(__name__)
server = app.server
app.title = "Radar Cultural Sonora"

app.layout = html.Div(
    [
        html.H1("Radar de Eventos Culturales", style={"textAlign": "center"}),

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
                            placeholder="Todos los municipios",
                        ),
                    ],
                    style={"flex": "1"},
                ),
                html.Div(
                    [
                        html.Label("Tipo de evento"),
                        dcc.Dropdown(
                            id="filtro-event_type",
                            options=opciones_filtro("event_type"),
                            multi=True,
                            placeholder="Todos los tipos",
                        ),
                    ],
                    style={"flex": "1"},
                ),
                html.Div(
                    [
                        html.Label("Clasificación"),
                        dcc.Dropdown(
                            id="filtro-clasification",
                            options=opciones_filtro("clasification"),
                            multi=True,
                            placeholder="Todas las clasificaciones",
                        ),
                    ],
                    style={"flex": "1"},
                ),
            ],
            style={
                "display": "flex",
                "gap": "20px",
                "marginBottom": "30px",
            },
        ),

        # Mapa y barras lado a lado
        html.H2("Mapa y eventos por municipio"),

        html.Div(
            [
                html.Div(
                    dcc.Graph(id="mapa-eventos"),
                    style={"flex": "1", "minWidth": "0"},
                ),
                html.Div(
                    dcc.Graph(id="grafico-municipios"),
                    style={"flex": "1", "minWidth": "0"},
                ),
            ],
            style={
                "display": "flex",
                "gap": "20px",
                "marginBottom": "30px",
            },
        ),

        # 🔧 NUEVO: serie de tiempo antes de la tabla
        html.H2("Evolución temporal de eventos"),
        dcc.Graph(id="serie-tiempo"),

        html.H2("Listado de eventos"),
        html.Div(id="contador-eventos", style={"marginBottom": "12px"}),

        dash_table.DataTable(
            id="tabla-eventos",
            columns=[{"name": col, "id": col} for col in COLUMNAS_TABLA],
            page_size=10,
            sort_action="native",
            filter_action="native",
            style_table={"overflowX": "auto"},
            style_cell={
                "textAlign": "left",
                "padding": "10px",
                "minWidth": "120px",
                "maxWidth": "300px",
                "whiteSpace": "normal",
            },
            style_header={
                "backgroundColor": "#0077B6",
                "color": "white",
                "fontWeight": "bold",
            },
            style_data_conditional=[
                {
                    "if": {"row_index": "odd"},
                    "backgroundColor": "#F4F8FB",
                }
            ],
        ),
    ],
    style={
        "maxWidth": "1400px",
        "margin": "40px auto",
        "padding": "20px",
        "fontFamily": "Arial",
    },
)


# ==========================================
# 8. CALLBACK: FILTROS -> MAPA + BARRAS + SERIE + TABLA
# ==========================================
@callback(
    Output("mapa-eventos", "figure"),
    Output("grafico-municipios", "figure"),
    Output("serie-tiempo", "figure"),          # 🔧 NUEVO Output
    Output("tabla-eventos", "data"),
    Output("contador-eventos", "children"),
    Input("filtro-municipio", "value"),
    Input("filtro-event_type", "value"),
    Input("filtro-clasification", "value"),
)
def actualizar_dashboard(municipios, tipos, clasificaciones):

    datos = df.copy()

    if municipios:
        datos = datos[datos["municipio"].isin(municipios)]

    if tipos:
        datos = datos[datos["event_type"].isin(tipos)]

    if clasificaciones:
        datos = datos[datos["clasification"].isin(clasificaciones)]

    fig_mapa = crear_mapa(datos)
    fig_barras = crear_grafico_municipios(datos)
    fig_serie = crear_serie_tiempo(datos)      # 🔧 NUEVO
    tabla = crear_tabla(datos)

    contador = f"Total de eventos: {datos['uuid'].nunique()}"

    return fig_mapa, fig_barras, fig_serie, tabla, contador


# ==========================================
# 9. INICIAR
# ==========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)