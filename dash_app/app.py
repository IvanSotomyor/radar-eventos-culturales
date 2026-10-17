import os
import pandas as pd
from sqlalchemy import create_engine
import plotly.express as px
from dash import Dash, dcc, html

# 1. Configurar la conexión a la base de datos
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# 2. Leer los datos
def obtener_datos():
    # Solo traemos las columnas necesarias para este gráfico
    query = "SELECT municipio, count(*) as total_eventos FROM eventos_culturales GROUP BY municipio ORDER BY total_eventos DESC"
    df = pd.read_sql(query, engine)
    return df

df = obtener_datos()

# 3. Crear el gráfico
fig = px.bar(
    df, 
    x='municipio', 
    y='total_eventos',
    title='Eventos Culturales por Municipio en Sonora',
    labels={'municipio': 'Municipio', 'total_eventos': 'Cantidad de Eventos'},
    color='total_eventos',
    color_continuous_scale='Viridis'
)
fig.update_layout(xaxis_tickangle=-45)

# 4. Configurar la app de Dash
app = Dash(__name__)
server = app.server
app.title = "Radar Cultural Sonora"

app.layout = html.Div([
    html.H1("Radar de Eventos Culturales", style={'textAlign': 'center', 'fontFamily': 'Arial'}),
    html.P(f"Total de eventos registrados: {len(df)} municipios con eventos.", style={'textAlign': 'center'}),
    dcc.Graph(figure=fig)
], style={'maxWidth': '1000px', 'margin': '40px auto', 'padding': '20px'})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)