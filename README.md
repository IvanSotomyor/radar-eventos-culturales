# Radar de Eventos Culturales de Sonora

Tablero web de consulta de eventos culturales de Sonora. El proyecto obtiene información de una API pública, la transforma con Python, la almacena en PostgreSQL y muestra una gráfica interactiva por municipio con Dash y Plotly. **Docker Compose** permite ejecutar los tres componentes sin instalar Python ni PostgreSQL directamente en el equipo.

> **Estado del repositorio analizado:** es un prototipo funcional en su diseño, pero contiene una incidencia en `init.sql` y una condición de arranque entre el ETL y el tablero. Sigue las instrucciones de **Primer arranque** para evitar esos problemas. Esta documentación describe el código incluido en el ZIP; no se verificó una ejecución completa de los contenedores.

## 1. Arquitectura y flujo de datos

```text
API pública de Cultura Sonora
  https://cultura.sonora.gob.mx/api/publico/eventos
                 |
                 v
      etl_cultura (Python 3.12)
      requests -> pandas -> SQLAlchemy
                 |
                 v
        postgres (PostgreSQL 16)
        tabla: eventos_culturales
                 ^
                 |
         dash (Dash + Plotly)
         consulta SQL agrupada
                 |
                 v
   Navegador: http://localhost:8050
```

**Qué hace cada componente:**

| Servicio en Compose | Tecnología | Responsabilidad |
| --- | --- | --- |
| `postgres` | `postgres:16-alpine` | Almacena la tabla `eventos_culturales` en un volumen persistente. |
| `etl_cultura` | Python 3.12, requests, pandas y SQLAlchemy | Consulta la API, transforma los eventos y reemplaza la tabla en PostgreSQL. Es una tarea que termina cuando finaliza su ejecución. |
| `dash` | Dash, Plotly, pandas, Gunicorn | Lee la tabla, agrupa registros por municipio y presenta una gráfica de barras. |

Los contenedores se comunican por la red interna de Compose: ambos servicios Python usan `DB_HOST=postgres` y `DB_PORT=5432`. El puerto `5433` es para acceder a PostgreSQL **desde Windows/host**, no desde otro contenedor.

## 2. Estructura del repositorio

```text
radar-eventos-culturales/
├── compose.yaml                   # Define y conecta los 3 servicios
├── init.sql                       # Inicialización de PostgreSQL
├── cultura_etl/
│   ├── Dockerfile                 # Imagen del ETL
│   ├── getCultura.py              # Extracción, transformación y carga
│   └── requirements.txt          # Dependencias del ETL
├── dash_app/
│   ├── Dockerfile                 # Imagen del tablero
│   ├── app.py                     # Consulta SQL y visualización
│   └── requirements.txt          # Dependencias del tablero
└── .gitignore
```

## 3. Requisitos previos

- Docker Desktop instalado y **abierto** (en Windows, con contenedores Linux / backend WSL 2).
- Docker Compose V2 (incluido normalmente en Docker Desktop).
- Git, si vas a obtener el proyecto desde su repositorio remoto.
- Acceso a Internet para descargar las imágenes, las dependencias de Python y consultar la API de Cultura Sonora.
- Puertos **8050** y **5433** libres en el equipo.

Verifica desde PowerShell:

```powershell
docker --version
docker compose version
docker info
```

## 4. Primer arranque desde cero (Windows / PowerShell)

### Paso 1. Obtener el repositorio y entrar en su carpeta

Si ya lo tienes descargado o clonado, abre PowerShell en la carpeta que contiene `compose.yaml`. Si tienes acceso a un repositorio Git, clónalo con la URL real de tu organización:

```powershell
git clone <URL-DEL-REPOSITORIO>
cd radar-eventos-culturales
```

> `<URL-DEL-REPOSITORIO>` es un marcador: el ZIP analizado no se utiliza para garantizar cuál es la URL remota que debe usar cada colaborador.


### Paso 1. Configurar credenciales (recomendado)

En la raíz, crea un archivo `.env` (al lado de `compose.yaml`):

```env
DB_USER=cultura_user
DB_PASSWORD=cambia_esta_contrasena_local
DB_NAME=cultura_db
```

El `compose.yaml` contiene valores predeterminados para estas variables; el `.env` permite sustituirlos. Evita compartir contraseñas reales en Git. Si vas a subir este archivo al repositorio, añade `.env` a `.gitignore`.

**Importante:** cambiar estas variables después de crear el volumen de PostgreSQL **no cambia automáticamente** el usuario, la contraseña ni la base de datos ya inicializados. Para conservar datos, modifica las credenciales en PostgreSQL; para reiniciar desde cero, consulta la sección de volúmenes.

### Paso 3. Construir las imágenes

```powershell
docker compose build
```

Esto construye las imágenes de `etl_cultura` y `dash` a partir de sus Dockerfiles. PostgreSQL utiliza la imagen `postgres:16-alpine`.

### Paso 4. Iniciar únicamente PostgreSQL

```powershell
docker compose up -d postgres
```

Comprueba que está listo:

```powershell
docker compose ps
docker compose logs --tail=50 postgres
```

El servicio tiene un `healthcheck` con `pg_isready`.

### Paso 5. Ejecutar el ETL y esperar a que termine correctamente

```powershell
docker compose run --rm etl_cultura
```

Deberías ver un mensaje como:

```text
Se insertaron N registros en la tabla 'eventos_culturales'.
```

`N` depende de los datos que devuelva la API. **Si aparece un error, no continúes al tablero todavía.** Revisa la conectividad con la API y la base de datos.

### Paso 6. Levantar el tablero

```powershell
docker compose up -d dash
```

Abre en el navegador:

**http://localhost:8050**

La aplicación muestra una gráfica de barras con los registros por municipio.

### Paso 7. Verificar los servicios

```powershell
docker compose ps
docker compose logs --tail=100 dash
```

Para seguir los logs en vivo:

```powershell
docker compose logs -f dash
```

**Por qué no recomendamos `docker compose up -d` como primer paso:** `dash` espera a que PostgreSQL esté saludable, **no** a que `etl_cultura` haya creado `eventos_culturales`. Si Dash arranca primero, la consulta SQL ejecutada al importar `app.py` puede fallar porque todavía no existe la tabla.

## 5. ¿Cómo funciona el ETL?

Archivo: `cultura_etl/getCultura.py`.

1. **Extracción:** `requests.get(url).json()` solicita eventos a `https://cultura.sonora.gob.mx/api/publico/eventos`. La URL fija incluye relaciones con lugares, tipos e itinerarios, además de parámetros `take=12`, `skip=0` y `free=false`.
2. **Selección de campos:** `filtrar_evento()` conserva UUID, nombre, tipo, clasificación, fechas, itinerarios, precios, lugar, municipio, coordenadas y URL pública del evento.
3. **Normalización:** `explotar_evento()` convierte cada combinación de evento e itinerario/horario en una fila. Un evento puede originar **más de una fila**.
4. **Precios:** `calcular_costo_minimo()` obtiene el mínimo entre los precios disponibles; si no hay precios, el código usa `0`. `resumir_tarifas()` reúne las tarifas en texto.
5. **Fechas:** `combinar_fecha_hora()` genera cadenas con desplazamiento `-07:00`, y `pd.to_datetime()` convierte las columnas a valores de fecha y hora.
6. **Carga:** `df.to_sql('eventos_culturales', engine, if_exists='replace', index=False)` **reemplaza la tabla completa** en cada ejecución del ETL.

**Columnas que genera:** `uuid`, `evento`, `actividad`, `eventType`, `clasification`, `fecha_inicio`, `fecha_fin`, `precio`, `tarifas`, `lugar`, `municipio`, `latitud`, `longitud`, `url`.

**Limitaciones importantes del código actual:** no hay paginación para recuperar todos los eventos; `take=12` limita el tamaño de página solicitado (el número efectivo depende de la API). No hay validación de estado HTTP (`raise_for_status`), control de reintentos ni manejo explícito de respuestas vacías. El ETL **no está programado** para ejecutarse periódicamente: se ejecuta al invocarlo.

## 6. ¿Cómo funciona el tablero?

Archivo: `dash_app/app.py`.

Al iniciar, el módulo crea la conexión a PostgreSQL y ejecuta:

```sql
SELECT municipio, count(*) as total_eventos
FROM eventos_culturales
GROUP BY municipio
ORDER BY total_eventos DESC;
```

Con el resultado, Plotly Express crea una gráfica de barras por municipio. Dash la presenta en una página titulada **Radar de Eventos Culturales**. Gunicorn expone el servicio en el puerto `8050` dentro del contenedor.

**Interpretación de la métrica:** `count(*)` cuenta **filas** de la tabla. Como un evento con varios itinerarios puede producir varias filas, **no representa necesariamente el número de eventos únicos**. Para contar eventos distintos se podría cambiar a `COUNT(DISTINCT uuid)`; eso sería una mejora futura, no el comportamiento actual.

**Actualización:** la consulta se ejecuta al cargar el módulo `app.py`, no en cada visita a la página. Si vuelves a ejecutar el ETL, el tablero puede seguir mostrando datos antiguos hasta que reinicies el servicio Dash:

```powershell
docker compose run --rm etl_cultura
docker compose restart dash
```

## 7. Configuración de Docker y puertos

En `compose.yaml`:

| Recurso | Configuración | Significado |
| --- | --- | --- |
| `postgres` | `postgres:16-alpine` | Imagen oficial de PostgreSQL 16. |
| `etl_cultura` | `build: ./cultura_etl` | Construye el contenedor de ETL con Python 3.12. |
| `dash` | `build: ./dash_app` | Construye el contenedor web con Python 3.12 y Gunicorn. |
| PostgreSQL | `127.0.0.1:5433:5432` | Acceso local desde el host en el puerto 5433. |
| Dash | `127.0.0.1:8050:8050` | Tablero accesible desde el host en el puerto 8050. |
| `postgres_data` | Volumen nombrado | Persiste la base de datos al detener o recrear contenedores. |
| `depends_on` | `service_healthy` para PostgreSQL | ETL y Dash esperan a que la base esté saludable, pero **no** entre sí. |

Los puertos se publican solo en `127.0.0.1`; por defecto no están expuestos a otros equipos de la red.

### ¿Qué hace cada Dockerfile?

- `cultura_etl/Dockerfile`: parte de `python:3.12-slim`, instala `requirements.txt`, copia `getCultura.py` y ejecuta `python getCultura.py`.
- `dash_app/Dockerfile`: parte de `python:3.12-slim`, instala dependencias, copia `app.py`, expone `8050` y ejecuta Gunicorn con dos workers.

### Volúmenes y persistencia

`docker compose down` elimina los contenedores y la red, pero **conserva** el volumen `postgres_data`.

```powershell
docker compose down
```

Para borrar **también la base de datos y todos sus registros**:

```powershell
docker compose down -v
```

**Precaución:** `down -v` destruye los datos del volumen del proyecto. Úsalo solo si deseas reinicializar la base y puedes volver a cargarla desde el ETL.

## 8. Comandos de operación cotidiana

Desde la carpeta del proyecto:

```powershell
# Ver estado
docker compose ps

# Ver logs
docker compose logs --tail=100 postgres
docker compose logs --tail=100 dash

# Volver a obtener datos y actualizar la gráfica
docker compose run --rm etl_cultura
docker compose restart dash

# Reconstruir tras cambios en código o dependencias
docker compose up -d --build dash

# Detener el proyecto sin borrar la base de datos
docker compose down
```

### Consultar PostgreSQL manualmente

Desde PowerShell, si el servicio está levantado:

```powershell
docker compose exec postgres psql -U cultura_user -d cultura_db
```

Si personalizaste usuario y base en `.env`, reemplaza `cultura_user` y `cultura_db` por tus valores.

Dentro de `psql`:

```sql
SELECT COUNT(*) FROM eventos_culturales;
SELECT municipio, COUNT(*) AS registros
FROM eventos_culturales
GROUP BY municipio
ORDER BY registros DESC;
```

Para salir: `\q`.
