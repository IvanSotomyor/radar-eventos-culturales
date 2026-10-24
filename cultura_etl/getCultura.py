import os
import logging
import requests
import pandas as pd
from sqlalchemy import create_engine, text
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

API_URL = (
    "https://cultura.sonora.gob.mx/api/publico/eventos"
    "?relations%5B%5D=place&relations%5B%5D=eventDocuments.document"
    "&relations%5B%5D=eventType&relations%5B%5D=group"
    "&relations%5B%5D=eventItineraries&take=12&skip=0&free=false"
)

TZ_OFFSET = "-07:00"


# ---------- Funciones de transformación ----------
def filtrar_evento(evento):
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
        "uuid": evento.get("uuid"), "name": evento.get("name"),
        "eventType": eventType.get("description"),
        "startDate": evento.get("startDate"), "endDate": evento.get("endDate"),
        "clasification": clasification.get("description"),
        "eventItineraries": eventItineraries, "eventPrices": eventPrices,
        "place": {
            "name": place.get("name"), "municipalityName": place.get("municipalityName"),
            "locationLatitude": place.get("locationLatitude"),
            "locationLongitude": place.get("locationLongitude"),
        },
        "url": f"https://cultura.sonora.gob.mx/eventos/{evento.get('uuid')}",
    }


def combinar_fecha_hora(fecha, hora):
    if not fecha:
        return None
    return f"{fecha}T{hora or '00:00'}:00{TZ_OFFSET}"


def calcular_costo_minimo(eventPrices):
    precios = [float(p.get("price")) for p in eventPrices if p.get("price") is not None]
    return min(precios) if precios else 0.0


def resumir_tarifas(eventPrices):
    return "; ".join(f"{p.get('description')}: {p.get('price')}" for p in eventPrices)


def explotar_evento(evento):
    itinerarios = evento["eventItineraries"] or [{
        "description": None, "date": evento["startDate"],
        "startTime": None, "endTime": None,
    }]
    precio = calcular_costo_minimo(evento["eventPrices"])
    tarifas = resumir_tarifas(evento["eventPrices"])
    return [{
        "uuid": evento["uuid"], "evento": evento["name"],
        "actividad": itinerario.get("description") or evento["name"],
        "event_type": evento["eventType"],
        "clasification": evento["clasification"],
        "fecha_inicio": combinar_fecha_hora(itinerario.get("date"), itinerario.get("startTime")),
        "fecha_fin": combinar_fecha_hora(itinerario.get("date"), itinerario.get("endTime")),
        "precio": precio, "tarifas": tarifas, "lugar": evento["place"]["name"],
        "municipio": evento["place"]["municipalityName"],
        "latitud": evento["place"]["locationLatitude"],
        "longitud": evento["place"]["locationLongitude"],
        "url": evento["url"],
    } for itinerario in itinerarios]


# ---------- Función de ingesta ----------
def ejecutar_ingesta():
    logger.info("Iniciando ingesta de eventos culturales...")
    try:
        respuesta = requests.get(API_URL, timeout=60)
        respuesta.raise_for_status()
        datos = respuesta.json()

        eventos_filtrados = [filtrar_evento(e) for e in datos.get("data", [])]
        eventos_exploded = [fila for evento in eventos_filtrados for fila in explotar_evento(evento)]
        if not eventos_exploded:
            logger.warning("La API devolvió 0 eventos. Nada que insertar.")
            return

        df = pd.DataFrame(eventos_exploded)
        df["fecha_inicio"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
        df["fecha_fin"] = pd.to_datetime(df["fecha_fin"], errors="coerce")

        # Fallback: si fecha_inicio es NaT (evento sin fecha), usar NOW()
        # para que la fila tenga una clave válida y no rompa el NOT NULL de la PK
        df["fecha_inicio"] = df["fecha_inicio"].fillna(pd.Timestamp.now(tz="UTC"))

        # Deduplicación defensiva por (uuid, fecha_inicio)
        antes = len(df)
        df = df.drop_duplicates(subset=["uuid", "fecha_inicio"], keep="last")
        if len(df) < antes:
            logger.warning(
                f"Deduplicadas {antes - len(df)} filas con (uuid, fecha_inicio) repetido."
            )

        DB_USER = os.environ["DB_USER"]
        DB_PASSWORD = os.environ["DB_PASSWORD"]
        DB_HOST = os.environ["DB_HOST"]
        DB_PORT = os.environ["DB_PORT"]
        DB_NAME = os.environ["DB_NAME"]
        engine = create_engine(
            f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )

        with engine.begin() as conn:
            # 1. Insertar en tabla temporal
            df.to_sql("eventos_culturales_temp", conn, if_exists="replace", index=False)

            # 2. Upsert desde temp a la tabla real
            columnas = list(df.columns)
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in columnas if c not in ("uuid", "fecha_inicio"))
            cols_clause = ", ".join(columnas)
            conn.execute(text(f"""
                INSERT INTO eventos_culturales ({cols_clause}, actualizado_en)
                SELECT {cols_clause}, NOW() FROM eventos_culturales_temp
                ON CONFLICT (uuid, fecha_inicio) DO UPDATE SET
                    {set_clause},
                    actualizado_en = NOW()
            """))

            # 3. Limpiar temporal
            conn.execute(text("DROP TABLE eventos_culturales_temp"))

        logger.info(f"Ingesta completada. {len(df)} registros procesados.")

    except Exception as e:
        logger.error(f"Error en la ingesta: {e}", exc_info=True)


# ---------- Scheduler ----------
if __name__ == "__main__":
    logger.info("Servicio de ingesta iniciado. Ejecutando primera ingesta...")
    ejecutar_ingesta()

    scheduler = BlockingScheduler(timezone="America/Hermosillo")
    scheduler.add_job(
        ejecutar_ingesta,
        "interval",
        hours=1,
        id="ingesta_cultura",
        replace_existing=True,
    )
    logger.info("Scheduler configurado: ingesta cada 1 hora.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Servicio detenido.")