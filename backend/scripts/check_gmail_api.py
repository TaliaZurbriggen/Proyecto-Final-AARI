"""Prueba HU35: renovar autorización y, sólo con bandera, enviar un correo a sí mismo."""

import argparse
import base64
import json
import os
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path

import httpx

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class ProbeError(Exception):
    """Mensaje seguro, sin cuerpo remoto ni datos de autenticación."""


def _response_json(response, stage):
    if not 200 <= response.status_code < 300:
        raise ProbeError(f"{stage}: HTTP {response.status_code}; sin reintentos.")
    try:
        data = response.json()
    except ValueError:
        raise ProbeError(f"{stage}: respuesta no válida.") from None
    if not isinstance(data, dict):
        raise ProbeError(f"{stage}: respuesta no válida.")
    return data


def probe(credentials, sender, *, send_to_self=False, client):
    """Sin consulta a bandeja/perfil, redirecciones, fallback SMTP ni reintentos."""
    if credentials.get("token_uri") != TOKEN_URI:
        raise ProbeError("Destino OAuth no permitido.")
    if set(credentials.get("scopes", [])) != {SEND_SCOPE}:
        raise ProbeError("La autorización debe tener solamente gmail.send.")
    if not all(isinstance(credentials.get(key), str) and credentials[key].strip()
               for key in ("client_id", "client_secret", "refresh_token")):
        raise ProbeError("Faltan credenciales locales.")
    if "\r" in sender or "\n" in sender or parseaddr(sender)[1] != sender or "@" not in sender:
        raise ProbeError("Remitente no válido.")
    try:
        response = client.post(TOKEN_URI, data={
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "refresh_token": credentials["refresh_token"],
            "grant_type": "refresh_token",
        }, follow_redirects=False)
    except httpx.HTTPError:
        raise ProbeError("No se pudo renovar la autorización; no se envió correo.") from None
    token = _response_json(response, "Renovación")
    if set(str(token.get("scope", "")).split()) != {SEND_SCOPE}:
        raise ProbeError("Google no confirmó el permiso exclusivo de envío.")
    if token.get("token_type", "").lower() != "bearer" or not token.get("access_token"):
        raise ProbeError("Respuesta de autorización incompleta.")
    if not send_to_self:
        return "auth_refresh_ok"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = sender
    message["Subject"] = "AARI - Prueba HU35 de correo HTTPS"
    message.set_content("Prueba ficticia de envío de AARI mediante Gmail API. "
                        "No contiene reclamos, contraseñas ni datos de proveedores.")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        response = client.post(SEND_URI,
            headers={"Authorization": f"Bearer {token['access_token']}"},
            json={"raw": raw}, follow_redirects=False)
    except httpx.HTTPError:
        raise ProbeError("Resultado de envío incierto; no repetir automáticamente.") from None
    data = _response_json(response, "Envío")
    if not isinstance(data.get("id"), str) or not data["id"]:
        raise ProbeError("Resultado de envío no confirmable; no repetir automáticamente.")
    return "accepted_for_delivery"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", required=True, type=Path)
    parser.add_argument("--send-to-self", action="store_true")
    args = parser.parse_args()
    try:
        credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
        sender = os.environ.get("AARI_GMAIL_PROBE_SENDER", "")
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            result = probe(credentials, sender, send_to_self=args.send_to_self, client=client)
    except ProbeError as error:
        print(str(error))
        return 1
    except Exception:
        print("La prueba no pudo completarse; no se muestran datos privados.")
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
