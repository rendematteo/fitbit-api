"""
authorize_fitbit.py — Flujo OAuth2 ONE-TIME de Fitbit (modo local).

Requisitos previos (crear una sola vez):
  1. Google Cloud Console → APIs & Services → Library → habilitar "Fitbit API"
  2. OAuth consent screen: External + tu email como test user
  3. Credentials → OAuth Client ID (Web application)
     Redirect URI: http://localhost:8080/callback
  4. Pegar en el entorno (o un .env):
       FITBIT_CLIENT_ID=...
       FITBIT_CLIENT_SECRET=...

Ejecución:
  pip install requests
  python authorize_fitbit.py

Abre el navegador, autorizás, y guarda fitbit_tokens.json con:
access_token, refresh_token, scope, user_id. Ese archivo es el ÚNICO
secreto que necesita el sync diario — guardalo bien.
"""
import base64
import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode

import requests

CLIENT_ID = os.environ.get("FITBIT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("FITBIT_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "activity heartrate sleep profile weight"
AUTH_URL = "https://www.fitbit.com/oauth2/authorize"
TOKEN_URL = "https://api.fitbit.com/oauth2/token"
SECRETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".secrets")  # hermano: projects/.secrets
OUT = os.environ.get("FITBIT_TOKENS_FILE", os.path.join(SECRETS, "fitbit_tokens.json"))


class CallbackHandler(BaseHTTPRequestHandler):
    code = None

    def do_GET(self):
        qs = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        CallbackHandler.code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            "<h2>✅ Autorizacion OK — ya podes cerrar esta pestanya</h2>".encode("utf-8")
        )
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *args):
        pass


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise SystemExit(
            "Faltan FITBIT_CLIENT_ID / FITBIT_CLIENT_SECRET en el ambiente"
        )

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": os.urandom(8).hex(),
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    print("Abriendo el navegador para autorizar la app...")
    webbrowser.open(url)

    server = HTTPServer(("127.0.0.1", 8080), CallbackHandler)
    server.handle_request()  # espera el unico request: el callback

    if not CallbackHandler.code:
        raise SystemExit("No se recibio el codigo de autorizacion")

    auth_header = base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    ).decode()
    resp = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": CallbackHandler.code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)

    print(f"✅ Tokens guardados en {OUT}")
    print("   Guarda ese archivo: es el unico secreto que necesita el sync diario.")


if __name__ == "__main__":
    main()
