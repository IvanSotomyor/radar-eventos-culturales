-- Extensión para búsquedas de texto rápidas (ILIKE, similarity)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Tabla principal de eventos culturales
-- La clave primaria es compuesta: (uuid, fecha_inicio)
-- porque un evento puede tener varios itinerarios en fechas distintas
CREATE TABLE IF NOT EXISTS eventos_culturales (
    uuid            TEXT         NOT NULL,
    evento          TEXT,
    actividad       TEXT,
    event_type      TEXT,
    clasification   TEXT,
    fecha_inicio    TIMESTAMPTZ  NOT NULL,
    fecha_fin       TIMESTAMPTZ,
    precio          NUMERIC(10, 2),
    tarifas         TEXT,
    lugar           TEXT,
    municipio       TEXT,
    latitud         TEXT,
    longitud        TEXT,
    url             TEXT,
    actualizado_en  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (uuid, fecha_inicio)
);

-- Índices para acelerar las consultas del dashboard
CREATE INDEX IF NOT EXISTS idx_eventos_fecha_inicio ON eventos_culturales (fecha_inicio);
CREATE INDEX IF NOT EXISTS idx_eventos_municipio    ON eventos_culturales (municipio);
CREATE INDEX IF NOT EXISTS idx_eventos_tipo         ON eventos_culturales (event_type);
CREATE INDEX IF NOT EXISTS idx_eventos_clasif       ON eventos_culturales (clasification);

-- Índices de texto (aprovechan pg_trgm para ILIKE rápido)
CREATE INDEX IF NOT EXISTS idx_eventos_evento_trgm ON eventos_culturales USING gin (evento gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_eventos_lugar_trgm  ON eventos_culturales USING gin (lugar gin_trgm_ops);