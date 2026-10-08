# ✅ Paso a paso — Autorización Google Health API

**Proyecto GCP:** `analog-fastness-428900-t2`
**Meta:** poder correr `authorize_google_health.py` y `google_health_sync.py`
**Tiempo:** ~10 min · **Secretos:** nunca los compartas (ni conmigo)

---

## 1. Habilitar la API
- [ ] Abrí el link del Marketplace (ya estás en el proyecto `analog-fastness-428900-t2`)
- [ ] Clic en **Enable** / **Manage**
- [ ] Si pide cuenta de facturación, asociá una (no se cobra por estos volúmenes)
- [ ] Si aparece un botón **"Request access" / "Join waitlist"** → apretalo
      (Google dijo que no está onboarding proyectos nuevos; este es el camino)

## 2. OAuth consent screen
- [ ] Cloud Console → **APIs & Services → OAuth consent screen**
- [ ] **User type: External** → Create
- [ ] App name: `FitClub` (o lo que quieras) · Support email: el tuyo → Next
- [ ] Scopes: **dejar vacío por ahora** → Next
- [ ] Test users: **agregar tu email** (el mismo con el que usás la app
      Google Health / Fitbit) → Next → aceptar policy → Back to dashboard
- [ ] **Publishing status: "Testing"** — así está bien, no hace falta publicar

## 3. Crear el cliente (Desktop)
- [ ] **APIs & Services → Credentials → + CREATE CREDENTIALS → OAuth client ID**
- [ ] Application type: **Desktop Application**
- [ ] Name: `FitClub local` → **Create**
- [ ] Clic en **DOWNLOAD JSON** → renombrar el archivo a **`client_secret.json`**
      y guardarlo en `C:\Users\R\Desktop\projects\fitbit-personal\`
- [ ] (Desktop app **no** necesita redirect URI: localhost queda permitido solo)

## 4. Agregar los scopes al cliente
- [ ] OAuth consent screen → **Data Access** → **Add or remove scopes**
- [ ] Buscar "Google Health API" y marcar estas 3:
      - `googlehealth.activity_and_fitness.readonly`
      - `googlehealth.sleep.readonly`
      - `googlehealth.health_metrics_and_measurements.readonly`
- [ ] Update → **Save**

## 5. Instalar dependencias
```powershell
cd "C:\Users\R\Desktop\projects\fitbit-personal"
pip install google-auth google-auth-oauthlib grpcio googleapis-common-protos grpcio-tools
```

## 6. Compilar los protos (una sola vez)
```powershell
git clone --depth 1 https://github.com/googleapis/googleapis.git
cd googleapis
python -m grpc_tools.protoc --proto_path=. --python_out=. --grpc_python_out=. `
  google/devicesandservices/health/v4/data_points.proto `
  google/devicesandservices/health/v4/data_model.proto `
  google/devicesandservices/health/v4/data_source.proto `
  google/devicesandservices/health/v4/data_coordinates.proto `
  google/devicesandservices/health/v4/medical_device_info.proto
cd ..
```
> Verificá que exista `googleapis\google\devicesandservices\health\v4\data_points_pb2_grpc.py`

## 7. Autorizar (one-time)
```powershell
cd "C:\Users\R\Desktop\projects\fitbit-personal"
python authorize_google_health.py
```
- [ ] Se abre el navegador → elegí **tu cuenta test user** → **Continue** → Allow
- [ ] Se guarda **`token.json`** ✅ (access + refresh token, se renueva solo)

## 8. Probar el sync
```powershell
python google_health_sync.py
```
**Esperado:** `Actividades: +N ...` / `Métricas: +N días ...` / `Sync OK ✅`
y aparecen `actividades_google_health.jsonl` + `metricas_google_health.jsonl`

---

## Troubleshooting
| Error | Qué hacer |
|---|---|
| `PERMISSION_DENIED` / 403 al llamar la API | Google aún no habilitó proyectos nuevos. **Puente:** seguir con `fitbit_daily_sync.py` hasta el 30/10/2026 y reintentar |
| `No existe client_secret.json` | Volvé al paso 3 |
| `invalid_grant` / refresh falla | Borrá `token.json` y re-ejecutá `authorize_google_health.py` |
| `ModuleNotFoundError: google.devicesandservices...` | No compilaste los protos (paso 6) o mal `HEALTH_GOOGLEAPIS_DIR` |
| Datos vacíos | El filtro es por **civil time** (tu zona). Si cambió `HEALTH_TZ`, ajustalo |

## Checklist final
- [ ] `client_secret.json` en `fitbit-personal\`
- [ ] `token.json` generado
- [ ] `googleapis\` con los stubs compilados
- [ ] `google_health_sync.py` devuelve `Sync OK`
