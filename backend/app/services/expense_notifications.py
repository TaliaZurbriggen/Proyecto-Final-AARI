"""Reporte y plantillas de expensa, sin llamadas externas ni secretos."""

import os
from typing import Mapping, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.schemas.expensas import ExpenseReport


EMAIL = TypeAdapter(EmailStr)
CONFIGURATION_ERROR = "Configurá un correo válido de contacto de la inmobiliaria."


def agency_email(value: object) -> str | None:
    try:
        return str(EMAIL.validate_python(str(value).strip())).lower() if value else None
    except ValidationError:
        return None


def expense_report(context: Mapping[str, Any], result, property_context, *, origin="agente") -> ExpenseReport:
    return ExpenseReport(
        reclamo_id=context["id"], numero=context["numero"],
        ingresado_en=context["creado_en"], clasificado_en=context["clasificado_en"],
        propiedad=property_context,
        inquilino={"nombre": context["inquilino_nombre"], "email": context["inquilino_email"]},
        descripcion=context["descripcion"], urgencia=context["urgencia"],
        fundamento=result.fundamento, origen=origin,
        confianza=result.confianza if origin == "agente" else None,
    )


def expense_subject(report: ExpenseReport) -> str:
    return f"AARI - Reporte de expensa #{report.numero:06d}"


def expense_message(report: ExpenseReport) -> str:
    property_data = report.propiedad
    unit = " · ".join(str(value) for value in (
        property_data.direccion,
        f"Piso {property_data.piso}" if property_data.piso is not None else None,
        f"Unidad {property_data.numero}" if property_data.numero else None,
        property_data.localidad, property_data.provincia,
    ) if value)
    base = urlsplit(os.getenv("APP_LOGIN_URL", "http://localhost:5173/login"))
    # Ni userinfo, query ni fragmento de la configuración pasan al correo.
    authority = base.netloc.rsplit("@", 1)[-1]
    if base.scheme not in {"http", "https"} or not authority:
        base = urlsplit("http://localhost:5173/login")
        authority = base.netloc
    detail_url = urlunsplit((base.scheme, authority, f"/expensas/{report.reclamo_id}", "", ""))
    confidence = f"{report.confianza:.0%}" if report.confianza is not None else "No corresponde (decisión humana)"
    return "\n".join([
        "Hola, equipo de la inmobiliaria:", "",
        "Hay un reclamo clasificado como expensa para evaluar.",
        f"Reclamo: AARI #{report.numero:06d}", f"Identificador: {report.reclamo_id}",
        f"Unidad: {unit}", f"Ingresado: {report.ingresado_en.isoformat()}",
        f"Clasificado: {report.clasificado_en.isoformat()}",
        f"Inquilino: {report.inquilino.nombre}", f"Contacto: {report.inquilino.email}",
        f"Urgencia informada: {report.urgencia}", f"Descripción: {report.descripcion}",
        "Tipo de gasto: expensa", f"Fundamento: {report.fundamento}",
        f"Origen: {report.origen}", f"Confianza: {confidence}", "",
        "Este reporte solicita evaluación: no autoriza gastos, no asigna proveedor",
        "ni confirma que el problema esté resuelto.",
        f"Detalle privado (requiere iniciar sesión): {detail_url}",
    ])
