"""HU32: identidad e invitaciones atómicas en PostgreSQL privado."""

import secrets
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.services.provider_access_service import InvitationDelivery, ProviderAccessError


def _not_found():
    return ProviderAccessError("No encontramos ese proveedor.", code="provider_not_found", status=404)


def _invalid_invitation():
    return ProviderAccessError(
        "La invitación no es válida, venció o ya fue utilizada. Pedí una nueva a la inmobiliaria.",
        code="invalid_provider_invitation", status=400,
    )


class SqlAlchemyProviderAccessRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def get_access(self, provider_id, *, now):
        with self.session_factory() as s:
            row = s.execute(text("""
                SELECT p.id, p.email, p.usuario_id, p.activo AS proveedor_activo,
                       u.activo AS usuario_activo, u.primer_ingreso
                FROM proveedores p LEFT JOIN usuarios u ON u.id=p.usuario_id
                WHERE p.id=:id
            """), {"id": str(provider_id)}).mappings().one_or_none()
            if row is None:
                raise _not_found()
            invitation = s.execute(text("""
                SELECT vence_en, envio_estado, ultimo_error
                FROM proveedor_invitaciones WHERE proveedor_id=:id
                ORDER BY (revocado_en IS NULL) DESC, creado_en DESC, id DESC LIMIT 1
            """), {"id": str(provider_id)}).mappings().one_or_none()
        activated = bool(row["usuario_id"]) and not bool(row["primer_ingreso"])
        if row["usuario_id"] is None:
            state = "sin_acceso"
        elif not row["proveedor_activo"] or (activated and not row["usuario_activo"]):
            state = "desactivado"
        elif activated:
            state = "activo"
        elif invitation and invitation["vence_en"] <= now:
            state = "vencido"
        else:
            state = "pendiente"
        return {
            "proveedor_id": row["id"], "email": row["email"], "estado": state,
            "envio_estado": invitation["envio_estado"] if invitation else None,
            "vence_en": invitation["vence_en"] if invitation and not activated else None,
            "ultimo_error": invitation["ultimo_error"] if invitation else None,
            "puede_invitar": bool(row["proveedor_activo"]) and not activated,
        }

    def prepare_invitation(self, provider_id, *, email, request_id, token_hash, now, expires, token):
        try:
            with self.session_factory.begin() as s:
                provider = s.execute(text("SELECT * FROM proveedores WHERE id=:id FOR UPDATE"),
                                     {"id": str(provider_id)}).mappings().one_or_none()
                if provider is None:
                    raise _not_found()
                if not provider["activo"]:
                    raise ProviderAccessError("Primero reactivá al proveedor.", code="provider_inactive")
                previous = s.execute(text("""
                    SELECT proveedor_id, email FROM proveedor_invitaciones WHERE request_id=:request
                """), {"request": str(request_id)}).mappings().one_or_none()
                if previous:
                    if str(previous["proveedor_id"]) != str(provider_id) or previous["email"] != email:
                        raise ProviderAccessError("La operación no coincide con la solicitud anterior.", code="request_conflict")
                    return None  # replay: no rotar token ni repetir envío
                user_id = provider["usuario_id"]
                if user_id:
                    user = s.execute(text("SELECT * FROM usuarios WHERE id=:id FOR UPDATE"),
                                     {"id": str(user_id)}).mappings().one()
                    if str(user["rol"]) != "proveedor" or not user["primer_ingreso"]:
                        raise ProviderAccessError("La cuenta ya fue activada. No se puede cambiar su correo desde esta acción.",
                                                  code="provider_already_activated", field_name="email")
                other = s.execute(text("""
                    SELECT id FROM usuarios WHERE lower(email)=:email
                    AND (CAST(:user_id AS uuid) IS NULL OR id<>CAST(:user_id AS uuid))
                """), {"email": email, "user_id": str(user_id) if user_id else None}).first()
                if other:
                    raise ProviderAccessError("Ese correo ya está utilizado por otra cuenta.",
                                              code="duplicate_email", field_name="email")
                if user_id is None:
                    user_id = str(uuid4())
                    s.execute(text("""
                        INSERT INTO usuarios (id,email,password_hash,rol,primer_ingreso,activo)
                        VALUES (:id,:email,crypt(:unusable,gen_salt('bf')),'proveedor',true,false)
                    """), {"id": user_id, "email": email, "unusable": secrets.token_urlsafe(48)})
                else:
                    s.execute(text("UPDATE usuarios SET email=:email, updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                              {"id": str(user_id), "email": email})
                s.execute(text("UPDATE proveedores SET email=:email, usuario_id=:user WHERE id=:id"),
                          {"email": email, "user": str(user_id), "id": str(provider_id)})
                s.execute(text("""
                    UPDATE proveedor_invitaciones SET revocado_en=:now
                    WHERE proveedor_id=:id AND usado_en IS NULL AND revocado_en IS NULL
                """), {"id": str(provider_id), "now": now})
                invitation_id = str(uuid4())
                s.execute(text("""
                    INSERT INTO proveedor_invitaciones
                        (id,request_id,proveedor_id,usuario_id,email,token_hash,creado_en,vence_en)
                    VALUES (:id,:request,:provider,:user,:email,:hash,:now,:expires)
                """), {"id": invitation_id, "request": str(request_id), "provider": str(provider_id),
                         "user": str(user_id), "email": email, "hash": token_hash, "now": now, "expires": expires})
                name = provider["nombre_razon_social"]
        except IntegrityError:
            # No propagar SQL/parámetros (contienen correo/hash).
            raise ProviderAccessError("El correo o la operación ya están registrados. Actualizá el estado antes de reintentar.",
                                      code="duplicate_email", field_name="email") from None
        return InvitationDelivery(invitation_id, email, name, token)

    def record_delivery(self, invitation_id, *, sent):
        with self.session_factory.begin() as s:
            s.execute(text("""
                UPDATE proveedor_invitaciones SET envio_estado=:state, ultimo_error=:error,
                    enviado_en=CASE WHEN :sent THEN CURRENT_TIMESTAMP ELSE enviado_en END
                WHERE id=:id
            """), {"id": str(invitation_id), "state": "enviado" if sent else "fallido", "sent": sent,
                     "error": None if sent else "No se pudo enviar la invitación. Podés generar una nueva."})

    def activate(self, token_hash, password, *, now):
        with self.session_factory.begin() as s:
            invitation = s.execute(text("SELECT id,proveedor_id FROM proveedor_invitaciones WHERE token_hash=:hash"),
                                   {"hash": token_hash}).mappings().one_or_none()
            if not invitation:
                raise _invalid_invitation()
            # Mismo orden de locks que reenviar: proveedor -> invitación -> usuario.
            provider = s.execute(text("SELECT * FROM proveedores WHERE id=:id FOR UPDATE"),
                                 {"id": str(invitation["proveedor_id"])}).mappings().one()
            row = s.execute(text("SELECT * FROM proveedor_invitaciones WHERE id=:id FOR UPDATE"),
                            {"id": str(invitation["id"])}).mappings().one()
            if (not provider["activo"] or row["usado_en"] or row["revocado_en"] or row["vence_en"] <= now
                    or str(provider["usuario_id"]) != str(row["usuario_id"]) or provider["email"] != row["email"]):
                raise _invalid_invitation()
            result = s.execute(text("""
                UPDATE usuarios SET password_hash=crypt(:password,gen_salt('bf')),
                    primer_ingreso=false, activo=true, intentos_fallidos=0, bloqueado_hasta=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=:id AND rol::text='proveedor' AND primer_ingreso AND email=:email
            """), {"password": password, "id": str(row["usuario_id"]), "email": row["email"]})
            if result.rowcount != 1:
                raise _invalid_invitation()
            s.execute(text("UPDATE proveedor_invitaciones SET usado_en=:now WHERE id=:id"),
                      {"now": now, "id": str(row["id"])})

    def profile(self, user):
        with self.session_factory() as s:
            row = s.execute(text("""
                SELECT p.id AS proveedor_id, p.nombre_razon_social, p.email
                FROM proveedores p JOIN usuarios u ON u.id=p.usuario_id
                WHERE p.id=:provider AND u.id=:user AND u.rol::text='proveedor'
                    AND u.activo AND NOT u.primer_ingreso AND p.activo
            """), {"provider": str(user.perfil_id), "user": str(user.id)}).mappings().one_or_none()
        if row is None:
            raise ProviderAccessError("No tenés acceso a este perfil de proveedor.", code="provider_forbidden", status=403)
        return dict(row)
