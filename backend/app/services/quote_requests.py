"""Solicitudes HU19: preparar no es enviar, contratar ni crear un presupuesto."""

import asyncio
import hashlib
import json
import logging
import os
import re

from app.core.whatsapp import WhatsAppConfigurationError, canonical_recipient
from app.services.whatsapp_sender import WhatsAppSendError


TEMPLATE_VERSION = "hu19_presupuesto_v1"


def request_content(row):
    """Huella de los datos divulgados y del ciclo autorizado, sin secretos."""
    address = ", ".join(str(row[key]) for key in ("direccion", "localidad", "provincia") if row[key])
    if row["piso"] is not None:
        address += f" · Piso {row['piso']}"
    if row["unidad"]:
        address += f" · Unidad {row['unidad']}"
    data = {"version": TEMPLATE_VERSION, "descripcion": row["descripcion"], "ubicacion": address,
            "especialidad_id": str(row["tipo_id"]) if row["tipo_id"] else None,
            "provincia": row["provincia"], "localidad": row["localidad"], "barrio": row["barrio"],
            "propiedad_id": str(row["propiedad_id"]), "inquilino_id": str(row["inquilino_id"]),
            "propietario_id": str(row["propietario_id"]), "actor_id": str(row["usuario_id"]),
            "tipo_gasto": row["tipo_gasto"]}
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return data, digest


def quote_message(reference, content):
    parameters = (str(reference), content["descripcion"], content["ubicacion"], "24 horas")
    if any(not value or len(value) > 4096 or "\x00" in value
           or any(0xD800 <= ord(char) <= 0xDFFF for char in value) for value in parameters):
        raise ValueError("Datos incompletos para solicitar presupuesto.")
    message = (f"AARI · Solicitud {parameters[0]}\nProblema: {parameters[1]}\n"
               f"Ubicación: {parameters[2]}\nPlazo de respuesta: {parameters[3]}.\n"
               "Respondé a este mensaje indicando importe, moneda y descripción del trabajo. "
               "Esta solicitud no confirma una contratación ni una visita.")
    return parameters, message


class QuoteRequestsWorker:
    def __init__(self, repository, sender, *, settings, template_name="", language="es_AR"):
        self.repository, self.sender, self.settings = repository, sender, settings
        self.template_name, self.language = template_name, language

    def ready_to_send(self):
        if not self.settings.outbound_enabled:
            return False
        try:
            self.settings.validate_sending()
        except WhatsAppConfigurationError:
            return False
        return bool(re.fullmatch(r"[a-z0-9_]{1,512}", self.template_name)
                    and re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", self.language))

    def tick(self):
        # Incluso sin canal se puede preparar/auditar con el worker explícitamente activo.
        prepared = self.repository.discover(limit=20)
        self.repository.recover_expired(limit=20)
        if not self.ready_to_send():
            return prepared
        recipients = tuple(canonical_recipient(value) for value in self.settings.test_recipients)
        job = self.repository.reserve_one(recipients=recipients)
        if job is None:
            return prepared
        # Revalidación + marca durable ANTES de invocar HTTP. Reserva de uno en uno.
        if not self.repository.begin_send(job, template_name=self.template_name, language=self.language,
                                          waba_id=self.settings.waba_id, phone_id=self.settings.phone_number_id):
            return prepared
        try:
            receipt = self.sender.send_template(recipient=job.recipient, template_name=self.template_name,
                                                language=self.language, parameters=job.parameters)
        except WhatsAppSendError as error:
            outcome = "rechazada" if error.outcome in {"not_sent", "rejected"} else "desconocida"
            self.repository.finish(job, outcome=outcome)
        except Exception:
            # Un fallo inesperado también pudo ocurrir después de salir el mensaje.
            self.repository.finish(job, outcome="desconocida")
        else:
            self.repository.finish(job, outcome="aceptada", message_id=receipt.message_id)
        return prepared + 1


def build_quote_requests_worker():
    from app.core.whatsapp import WhatsAppSettings
    from app.db.quote_requests import SqlAlchemyQuoteRequests
    from app.services.whatsapp_sender import MetaWhatsAppSender
    settings = WhatsAppSettings.from_env()
    return QuoteRequestsWorker(SqlAlchemyQuoteRequests(), MetaWhatsAppSender(settings), settings=settings,
        template_name=os.getenv("QUOTE_REQUEST_TEMPLATE_NAME", ""),
        language=os.getenv("QUOTE_REQUEST_TEMPLATE_LANGUAGE", "es_AR"))


async def run_quote_requests_worker(worker, stop_event, *, poll_seconds=5):
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(worker.tick)
        except Exception:
            logging.getLogger(__name__).error("No se pudo procesar la solicitud de presupuesto.")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
