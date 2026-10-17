import os
import json
import requests
import pandas as pd
from sqlalchemy import create_engine

# 1. Obtener datos de la API
url = 'https://cultura.sonora.gob.mx/api/publico/eventos?relations%5B%5D=place&relations%5B%5D=eventDocuments.document&relations%5B%5D=eventType&relations%5B%5D=group&relations%5B%5D=eventItineraries&take=12&skip=0&free=false'
datos = requests.get(url).json()

def filtrar_evento(evento):
    # (Tu misma función de filtrado)
    clasification = evento.get("clasification") or {}
    place = evento.get("place") or {}
    eventType = evento.get("eventType") or {}
    eventItineraries = []
    for itinerario in evento.get("eventItineraries", []) or []:
        schedules = itinerario.get("schedules") or [{}]
        for horario in schedules:
            eventItineraries.append({
                "description": itinerario.get("description"),
                "date": itinerario.get("date"),
                "startTime": horario.get("startTime"),
                "endTime": horario.get("endTime"),
            })
    eventPrices = [
        {"description": (precio.get("profile") or {}).get("description"), "price": precio.get("price")}
        for precio in evento.get("eventPrices", []) or []
    ] or [{"description": "Gratis", "price": 0}]
    return {
        "uuid": evento.get("uuid"), "name": evento.get("name"), "eventType": eventType.get("description"),
        "startDate": evento.get("startDate"), "endDate": evento.get("endDate"), "clasification": clasification.get("description"),
        "eventItineraries": eventItineraries, "eventPrices": eventPrices,
        "place": {
            "name": place.get("name"), "municipalityName": place.get("municipalityName"),
            "locationLatitude": place.get("locationLatitude"), "locationLongitude": place.get("locationLongitude"),
        },
        "url": f"https://cultura.sonora.gob.mx/eventos/{evento.get('uuid')}",
    }


TZ_OFFSET = "-07:00"
def combinar_fecha_hora(fecha, hora):
    if not fecha: return None
    return f"{fecha}T{hora or '00:00'}:00{TZ_OFFSET}"

def calcular_costo_minimo(eventPrices):
    precios = [float(p.get("price")) for p in eventPrices if p.get("price") is not None]
    return min(precios) if precios else 0.0

def resumir_tarifas(eventPrices):
    return "; ".join(f"{p.get('description')}: {p.get('price')}" for p in eventPrices)

def explotar_evento(evento):
    itinerarios = evento["eventItineraries"] or [{"description": None, "date": evento["startDate"], "startTime": None, "endTime": None}]
    precio = calcular_costo_minimo(evento["eventPrices"])
    tarifas = resumir_tarifas(evento["eventPrices"])
    return [{
        "uuid": evento["uuid"], "evento": evento["name"], "actividad": itinerario.get("description") or evento["name"],
        "eventType": evento["eventType"], "clasification": evento["clasification"],
        "fecha_inicio": combinar_fecha_hora(itinerario.get("date"), itinerario.get("startTime")),
        "fecha_fin": combinar_fecha_hora(itinerario.get("date"), itinerario.get("endTime")),
        "precio": precio, "tarifas": tarifas, "lugar": evento["place"]["name"],
        "municipio": evento["place"]["municipalityName"], "latitud": evento["place"]["locationLatitude"],
        "longitud": evento["place"]["locationLongitude"], "url": evento["url"],
    } for itinerario in itinerarios]

# Procesar
eventos_filtrados = [filtrar_evento(e) for e in datos.get("data", [])]
eventos_exploded = [fila for evento in eventos_filtrados for fila in explotar_evento(evento)]
df = pd.DataFrame(eventos_exploded)

# 2. Limpieza para PostgreSQL
# Convertir fecha_inicio y fecha_fin a datetime real
df['fecha_inicio'] = pd.to_datetime(df['fecha_inicio'])
df['fecha_fin'] = pd.to_datetime(df['fecha_fin'])

# 3. Guardar en PostgreSQL
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")
DB_NAME = os.environ.get("DB_NAME")

engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# Guardamos el DataFrame en la tabla 'eventos_culturales'. 
# if_exists='replace' borra la tabla anterior y la crea de nuevo (útil para pruebas)
df.to_sql('eventos_culturales', engine, if_exists='replace', index=False)

print(f"\nSe insertaron {len(df)} registros en la tabla 'eventos_culturales'.")