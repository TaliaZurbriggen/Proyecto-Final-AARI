"""Autorización local y explícita HU35. No envía correos ni inicia AARI."""

import argparse
import json
import os
from pathlib import Path

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
REDIRECT_URI = "http://localhost:8765/"
AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


def authorize(client_path: Path, output_path: Path, *, flow_class=None):
    """Usa state/PKCE de la biblioteca oficial; nunca imprime las credenciales."""
    if output_path.exists():
        raise ValueError("Ya existe una autorización; no se reemplazó.")
    config = json.loads(client_path.read_text(encoding="utf-8"))
    client = config.get("web", {})
    if (
        client.get("auth_uri") != AUTH_URI
        or client.get("token_uri") != TOKEN_URI
        or REDIRECT_URI not in client.get("redirect_uris", [])
        or not client.get("client_id")
        or not client.get("client_secret")
    ):
        raise ValueError("Cliente OAuth no válido para esta prueba local.")
    if flow_class is None:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow_class = InstalledAppFlow
    flow = flow_class.from_client_config(
        config, scopes=[SEND_SCOPE], autogenerate_code_verifier=True
    )
    credentials = flow.run_local_server(
        host="localhost", port=8765,
        open_browser=False, timeout_seconds=600,
        authorization_prompt_message="Autorizá AARI en este enlace: {url}",
        success_message="Autorización recibida. Podés volver a AARI.",
        access_type="offline", prompt="consent", include_granted_scopes="false",
    )
    scopes = credentials.granted_scopes or credentials.scopes
    if set(scopes or ()) != {SEND_SCOPE} or not credentials.refresh_token:
        raise ValueError("Google no otorgó exclusivamente envío con renovación.")
    # No persistir el access token: la prueba fuerza una renovación independiente.
    data = json.loads(credentials.to_json(strip=["token", "expiry"]))
    data["scopes"] = [SEND_SCOPE]
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(data, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        authorize(args.client, args.output)
    except Exception:
        # Los errores OAuth pueden incluir códigos/credenciales: no imprimirlos.
        print("No se guardó la autorización. Revisá el consentimiento y la configuración.")
        return 1
    print("Autorización de envío guardada localmente; no se envió ningún correo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
