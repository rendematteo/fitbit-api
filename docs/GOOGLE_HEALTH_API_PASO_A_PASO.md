# 📖 Guía paso a paso — Google Health API (guía genérica)

> Para cualquier persona que quiera leer sus datos de salud/fitness
> (ex-Fitbit) con Python. Sin dependencias personales.
>
> ⚠️ **Contexto:** la **Fitbit Web API se apagó el 30/10/2026**.
> Todo migró a la **Google Health API**. Esta guía usa la API nueva.

---

## 0. Documentación oficial (links)

| Recurso | Link |
|---|---|
| **Referencia REST** (API explorer) | https://developers.google.com/health/reference/rest |
| **Referencia gRPC** | https://developers.google.com/health/reference/rpc |
| Setup (Google Cloud + OAuth) | https://developers.google.com/health/setup |
| Get started | https://developers.google.com/health/get-started |
| **Scopes** | https://developers.google.com/health/scopes |
| **Data types** (tipos de dato) | https://developers.google.com/health/data-types |
| Workouts | https://developers.google.com/health/data-types/workouts |
| Sleep | https://developers.google.com/health/data-types/sleep |
| Steps | https://developers.google.com/health/data-types/steps |
| Filtros (sintaxis) | https://developers.google.com/health/filters |
| Rate limits | https://developers.google.com/health/rate-limits |
| Endpoints | https://developers.google.com/health/endpoints |
| Client libraries | https://developers.google.com/health/libraries |
| Webhooks | https://developers.google.com/health/webhooks |
| Migración desde Fitbit | https://developers.google.com/health/migration |
| Codelab: primera llamada gRPC | https://developers.google.com/health/codelabs/make-your-first-api-call-using-grpc |

---

## 1. Crear proyecto y habilitar la API

1. Ir a https://console.cloud.google.com → **Select a project → New Project**
2. Nombre → Create → seleccionar el proyecto
3. Menú → **APIs & Services → Library** → buscar **"Google Health API"** → **Enable**
4. Si el Marketplace pide cuenta de facturación, asociar una
5. Si aparece **"Request access" / waitlist**: apretarlo
   (Google informa que *no está onboarding proyectos nuevos*; el acceso
   se abre por etapas — ver https://developers.google.com/health/about)

## 2. OAuth consent screen

1. **APIs & Services → OAuth consent screen**
2. **User type: External** → Create
3. App name + email de soporte → Next
4. Scopes: dejar vacío (se agregan en el paso 4) → Next
5. **Test users → Add users** → el email de la cuenta que usa la app
   **Google Health** (la misma donde vive la data de Fitbit) → Save
6. Aceptar las políticas → Back to dashboard
7. Dejar el estado en **"Testing"** (no hace falta publicar)

## 3. Crear el cliente OAuth (Desktop)

1. **APIs & Services → Credentials → + CREATE CREDENTIALS → OAuth client ID**
2. Application type: **Desktop Application**
   - Un cliente Desktop **no requiere redirect URI**: los loopback
     `http://localhost` / `http://127.0.0.1` en cualquier puerto
     quedan permitidos automáticamente
3. Name → **Create** → **DOWNLOAD JSON**
4. Renombrar el archivo a **`client_secret.json`**

## 4. Agregar los scopes

OAuth consent screen → **Data Access** → **Add or remove scopes** →
buscar "Google Health API" y marcar los que necesites:

| Scope | Data types cubiertos |
|---|---|
| `googlehealth.activity_and_fitness.readonly` | exercise, steps, distance, floors, active-zone-minutes, active-minutes, sedentary-period, activity-level, energía, hidratación |
| `googlehealth.sleep.readonly` | sleep, temperatura de sueño, respiratory rate de sueño |
| `googlehealth.health_metrics_and_measurements.readonly` | heart-rate, daily-resting-heart-rate, HRV, daily-vo2-max, vo2-max, weight, body-fat, oxygen saturation, core body temperature, ECG |
| `googlehealth.location.readonly` | rutas GPS (para `exportExerciseTcx`) |
| `googlehealth.nutrition.writeonly` | nutrition-log, food, hydration-log (solo escritura) |

→ **Update** → **Save**

## 5. Instalar dependencias

```bash
# OAuth + gRPC
pip install google-auth google-auth-oauthlib grpcio grpcio-tools googleapis-common-protos
```

## 6. (gRPC) Compilar los protos

La API es **gRPC-first**; hay que generar los stubs desde los protos públicos:

```bash
git clone --depth 1 https://github.com/googleapis/googleapis.git
cd googleapis
python -m grpc_tools.protoc \
  --proto_path=. \
  --python_out=. \
  --grpc_python_out=. \
  google/devicesandservices/health/v4/data_points.proto \
  google/devicesandservices/health/v4/data_model.proto \
  google/devicesandservices/health/v4/data_source.proto \
  google/devicesandservices/health/v4/data_coordinates.proto \
  google/devicesandservices/health/v4/medical_device_info.proto
cd ..
```

> El servicio es `DataPointsService`, host default `health.googleapis.com`,
> puerto 443. Métodos principales: `ListDataPoints`, `GetDataPoint`,
> `CreateDataPoint`, `UpdateDataPoint`, `BatchDeleteDataPoints`,
> `ReconcileDataPoints`, `RollUpDataPoints`, `DailyRollUpDataPoints`,
> `ExportExerciseTcx`.

## 7. Autorizar (one-time)

Con `client_secret.json` en el directorio de trabajo:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)   # abre el navegador
with open("token.json", "w") as f:
    f.write(creds.to_json())            # access + refresh token
```

Después, en cada ejecución, el token se refresca solo:

```python
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

with open("token.json") as f:
    creds = Credentials.from_authorized_user_info(json.load(f), SCOPES)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
```

## 8. Primera llamada

**Opción A — REST** (curl; útil para probar):

```bash
curl -H "Authorization: Bearer $(python -c \
  'import json; from google.oauth2.credentials import Credentials; \
   from google.auth.transport.requests import Request; \
   c=Credentials.from_authorized_user_info(json.load(open("token.json"))); \
   c.refresh(Request()); print(c.token)')' \
  "https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints?pageSize=25"
```

**Opción B — gRPC** (recomendado):

```python
import grpc
from google.auth.transport.grpc import secure_authorized_channel
from google.auth.transport.requests import Request
from google.devicesandservices.health.v4 import data_points_pb2, data_points_pb2_grpc

channel = secure_authorized_channel(creds, Request(), "health.googleapis.com:443")
stub = data_points_pb2_grpc.DataPointsServiceStub(channel)

req = data_points_pb2.ListDataPointsRequest(
    parent="users/me/dataTypes/exercise",
    page_size=25,
    filter='exercise.interval.civil_start_time >= "2026-10-01" '
           'AND exercise.interval.civil_start_time < "2026-10-02"',
)
for dp in stub.ListDataPoints(req).data_points:
    print(dp.name, dp.exercise.display_name,
          dp.exercise.metrics_summary.distance_millimeters)
```

## 9. Filtros útiles (sintaxis AIP-160)

| Qué | Filtro |
|---|---|
| Sesiones por día (hora local) | `exercise.interval.civil_start_time >= "YYYY-MM-DD" AND exercise.interval.civil_start_time < "YYYY-MM-DD"` |
| Sueño (se filtra por **fin**) | `sleep.interval.civil_end_time >= "..." AND sleep.interval.civil_end_time < "..."` |
| Resumen diario | `daily_resting_heart_rate.date >= "..."` · `daily_vo2_max.date >= "..."` |
| Muestras por hora civil | `weight.sample_time.civil_time >= "..."` |
| Telemetría cruda | `heart_rate.sample_time.physical_time >= "2026-10-01T00:00:00Z"` |

> `page_size` máx **25** para `exercise` y `sleep` (paginar con
> `next_page_token`); 10 000 para el resto. Respuestas ordenadas por
> `interval.start_time` **descendente**.

## 10. Campos clave de `exercise.metricsSummary`

| Campo | Unidad |
|---|---|
| `caloriesKcal` | kcal |
| `distanceMillimeters` | mm (÷1e6 = km) |
| `steps` | pasos |
| `averageHeartRateBeatsPerMinute` | bpm |
| `averagePaceSecondsPerMeter` | s/m (×60 = min/km) |
| `averageSpeedMillimetersPerSecond` | mm/s |
| `activeZoneMinutes` | minutos |
| `runVo2Max` | ml/kg/min |

## Notas

- **Onboarding:** Google no está habilitando proyectos nuevos por ahora.
  Si recibís `PERMISSION_DENIED` (403), es eso — reintentar después.
- **Legacy:** la Fitbit Web API dejó de funcionar el **30/10/2026**
  (soporte terminó 30/09/2026). Ver la guía de migración:
  https://developers.google.com/health/migration
- **Webhooks:** para sync casi en vivo, suscribirse al data type:
  https://developers.google.com/health/webhooks
- **Rate limits:** https://developers.google.com/health/rate-limits

## Archivos típicos en el directorio de trabajo

```
.
├── client_secret.json   # OAuth client (Desktop) — secreto
├── token.json           # access + refresh token — secreto
├── googleapis/          # repo con protos compilados
└── tu_script.py
```
