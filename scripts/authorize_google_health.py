"""
authorize_google_health.py — OAuth2 ONE-TIME para la Google Health API.

══════════ SETUP (una sola vez, ~10 min) ══════════
1. Google Cloud Console → crear proyecto
2. APIs & Services → Library → buscar "Google Health API" → ENABLE
3. APIs & Services → OAuth consent screen:
   - User type: External → Create
   - App name, soporte email → Next
   - Contact info (tu email) → Next → aceptar policy → Create
4. APIs & Services → Credentials → + CREATE CREDENTIALS → OAuth client ID
   - Application type: **Desktop Application**
   - Create → **DOWNLOAD JSON** → renombrar a `client_secret.json`
   (Desktop app no necesita redirect URI: localhost queda permitido)

   ⚠️ Si el cliente es tipo **Web application** (clave "web" en el JSON,
   no "installed"), este script igual funciona: InstalledAppFlow
   .from_client_secrets_file acepta AMBOS tipos (revisa "web" primero,
   según google_auth_oauthlib/flow.py). Pero como run_local_server()
   levanta un server en http://localhost:<puerto>/, tenés que agregar
   **http://127.0.0.1** en "Authorized redirect URIs" del cliente
   (Google Cloud Console → Credentials → tu OAuth client → Edit).
   Google permite cualquier puerto en loopback (RFC 8252) y trata
   localhost y 127.0.0.1 como equivalentes. Si igual te da
   redirect_uri_mismatch, agregá también http://localhost.
5. OAuth consent screen → Data Access → Add or remove scopes:
   - googlehealth.activity_and_fitness.readonly
   - googlehealth.sleep.readonly
   - googlehealth.health_metrics_and_measurements.readonly
6. OAuth consent screen → Test users → + ADD USERS → tu email
   (el mismo con el que entrás a la app Google Health)

══════════ DEPENDENCIAS ══════════
pip install google-auth google-auth-oauthlib

══════════ EJECUCIÓN ══════════
python authorize_google_health.py

Abre el navegador, autorizás, y guarda **token.json**
(access + refresh token; se refresca solo).

⚠️ Nota importante: Google dice que "no está onboardando proyectos
nuevos por ahora". Si al autorizar o al llamar la API recibís
PERMISSION_DENIED / 403, es que el acceso no se habilitó todavía.
Mientras tanto, la Fitbit Web API (fitbit_daily_sync.py) sigue
funcionando hasta el 30/10/2026.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from google_auth_oauthlib.flow import InstalledAppFlow
from src.paths import SECRETS_DIR

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
]
CLIENT_SECRETS_FILE = os.environ.get("CLIENT_SECRETS_FILE", os.path.join(SECRETS_DIR, "client_secret.json"))
TOKEN_FILE = os.environ.get("HEALTH_TOKEN_FILE", os.path.join(SECRETS_DIR, "token.json"))


def main():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        raise SystemExit(
            f"No existe {CLIENT_SECRETS_FILE}. Descargá el OAuth client ID "
            "(Desktop Application) desde Google Cloud Console."
        )

    # from_client_secrets_file acepta clientes "installed" Y "web" (revisa
    # "web" primero). Si el tuyo es "web", verificá que http://127.0.0.1
    # figure en Authorized redirect URIs (ver nota en el docstring).
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, SCOPES
    )
    # run_local_server: abre el navegador y levanta un server en localhost
    creds = flow.run_local_server(port=0)

    data = creds.to_json()
    # Escritura atómica: escribe a .tmp y reemplaza. Evita el PermissionError
    # al truncar token.json si otro proceso lo tiene memory-mapped.
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    for intento in range(5):
        try:
            os.replace(tmp, TOKEN_FILE)
            break
        except PermissionError:
            if intento == 4:
                raise
            time.sleep(0.6)

    print(f"✅ Token guardado en {TOKEN_FILE}")
    print("   Incluye refresh token: se renueva automáticamente.")


if __name__ == "__main__":
    main()
