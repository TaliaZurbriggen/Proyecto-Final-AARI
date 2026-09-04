"""Acceso a datos para el alta, notificación y clasificación de reclamos."""

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.schemas.reclamos import (
    AgentClassificationResult,
    ClaimClassificationResponse,
    ClaimCreatedResponse,
    ClaimPropertyContext,
)
from app.services.claim_notifications import ClaimNotificationContext
from app.services.classification_service import ClaimForClassification
from app.services.claims_creation_service import (
    ActiveClaimExistsError,
    PersistedClaim,
    StoredClaimPhoto,
    TenantClaimContext,
)


class SqlAlchemyClaimsRepository:
    """Implementación PostgreSQL de los puertos de reclamos."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def get_creation_context(
        self, *, user_id: UUID, profile_id: UUID
    ) -> TenantClaimContext | None:
        statement = text(
            """
            SELECT i.id AS inquilino_id, i.nombre_completo, i.email,
                   p.id AS propiedad_id, p.direccion, p.provincia, p.localidad,
                   p.barrio, CAST(p.tipo AS TEXT) AS tipo, p.piso, p.numero
            FROM inquilinos i
            JOIN propiedades p ON p.id = i.propiedad_id
            WHERE i.id = :profile_id
              AND i.usuario_id = :user_id
              AND i.estado = 'activo'
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement,
                {"profile_id": str(profile_id), "user_id": str(user_id)},
            ).mappings().one_or_none()
        if row is None:
            return None
        return TenantClaimContext(
            tenant_id=UUID(str(row["inquilino_id"])),
            tenant_name=str(row["nombre_completo"]),
            tenant_email=str(row["email"]),
            property=ClaimPropertyContext(
                id=row["propiedad_id"],
                direccion=row["direccion"],
                provincia=row["provincia"],
                localidad=row["localidad"],
                barrio=row["barrio"],
                tipo=row["tipo"],
                piso=row["piso"],
                numero=row["numero"],
            ),
        )

    def has_active_claim(self, *, tenant_id: UUID, property_id: UUID) -> bool:
        statement = text(
            """
            SELECT 1
            FROM reclamos
            WHERE inquilino_id = :tenant_id
              AND propiedad_id = :property_id
              AND estado NOT IN ('Resuelto', 'Resuelto (sin confirmación)')
            LIMIT 1
            """
        )
        with self.session_factory() as session:
            return (
                session.execute(
                    statement,
                    {
                        "tenant_id": str(tenant_id),
                        "property_id": str(property_id),
                    },
                ).scalar_one_or_none()
                is not None
            )

    def create_claim(
        self,
        *,
        claim_id: UUID,
        context: TenantClaimContext,
        description: str,
        urgency: str,
        photos: list[StoredClaimPhoto],
        user_id: UUID,
    ) -> PersistedClaim:
        notification_id = uuid4()
        try:
            with self.session_factory.begin() as session:
                row = session.execute(
                    text(
                        """
                        INSERT INTO reclamos
                            (id, descripcion, urgencia, inquilino_id, propiedad_id)
                        VALUES
                            (:id, :descripcion, CAST(:urgencia AS urgencia_reclamo),
                             :inquilino_id, :propiedad_id)
                        RETURNING id, numero, estado, creado_en
                        """
                    ),
                    {
                        "id": str(claim_id),
                        "descripcion": description,
                        "urgencia": urgency,
                        "inquilino_id": str(context.tenant_id),
                        "propiedad_id": str(context.property.id),
                    },
                ).mappings().one()

                for photo in photos:
                    session.execute(
                        text(
                            """
                            INSERT INTO reclamo_fotos
                                (id, reclamo_id, url, formato, tamanio_bytes)
                            VALUES
                                (:id, :reclamo_id, :url, :formato, :tamanio_bytes)
                            """
                        ),
                        {
                            "id": str(photo.id),
                            "reclamo_id": str(claim_id),
                            "url": photo.path,
                            "formato": photo.format,
                            "tamanio_bytes": photo.size_bytes,
                        },
                    )

                session.execute(
                    text(
                        """
                        INSERT INTO reclamo_historial_estados
                            (id, reclamo_id, estado_anterior, estado_nuevo,
                             origen, usuario_id)
                        VALUES
                            (:id, :reclamo_id, NULL, 'Recibido',
                             'inquilino', :usuario_id)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "reclamo_id": str(claim_id),
                        "usuario_id": str(user_id),
                    },
                )

                claim_number = int(row["numero"])
                message = self._confirmation_message(
                    context=context,
                    claim_number=claim_number,
                    description=description,
                    urgency=urgency,
                )
                session.execute(
                    text(
                        """
                        INSERT INTO notificaciones
                            (id, reclamo_id, destinatario_tipo,
                             destinatario_contacto, canal, mensaje, estado_envio)
                        VALUES
                            (:id, :reclamo_id, 'inquilino', :recipient,
                             'email', :message, 'pendiente')
                        """
                    ),
                    {
                        "id": str(notification_id),
                        "reclamo_id": str(claim_id),
                        "recipient": context.tenant_email,
                        "message": message,
                    },
                )
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            constraint = getattr(diagnostic, "constraint_name", "") or ""
            message = str(error.orig).lower()
            if (
                constraint == "uq_reclamos_inquilino_propiedad_activo"
                or "uq_reclamos_inquilino_propiedad_activo" in message
            ):
                raise ActiveClaimExistsError from error
            raise

        return PersistedClaim(
            response=ClaimCreatedResponse(
                id=row["id"],
                numero=int(row["numero"]),
                estado=row["estado"],
                creado_en=row["creado_en"],
                fotos_adjuntas=len(photos),
            ),
            notification_id=notification_id,
        )

    @classmethod
    def _confirmation_message(
        cls,
        *,
        context: TenantClaimContext,
        claim_number: int,
        description: str,
        urgency: str,
    ) -> str:
        return "\n".join(
            [
                f"Hola {context.tenant_name},",
                "",
                f"Recibimos tu reclamo AARI #{claim_number:06d}.",
                f"Unidad: {cls._property_label(context.property)}",
                f"Urgencia informada: {urgency}.",
                f"Descripción: {description}",
                "",
                "Estado inicial: Recibido.",
                "Podrás seguir su evolución desde AARI.",
            ]
        )

    @staticmethod
    def _property_label(property_context: ClaimPropertyContext) -> str:
        details: list[str] = [property_context.direccion]
        if property_context.tipo == "departamento":
            if property_context.piso is not None:
                details.append(
                    "PB"
                    if property_context.piso == 0
                    else f"Piso {property_context.piso}"
                )
            if property_context.numero:
                details.append(f"Unidad {property_context.numero}")
        details.extend([property_context.localidad, property_context.provincia])
        return " · ".join(details)

    def get_notification_context(
        self, notification_id: UUID
    ) -> ClaimNotificationContext | None:
        statement = text(
            """
            SELECT n.destinatario_contacto, n.mensaje, r.numero
            FROM notificaciones n
            JOIN reclamos r ON r.id = n.reclamo_id
            WHERE n.id = :notification_id
              AND n.canal = 'email'
              AND n.estado_envio IN ('pendiente', 'fallido')
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement,
                {"notification_id": str(notification_id)},
            ).mappings().one_or_none()
        if row is None:
            return None
        return ClaimNotificationContext(
            recipient=str(row["destinatario_contacto"]),
            claim_number=int(row["numero"]),
            message=str(row["mensaje"]),
        )

    def mark_notification_result(
        self,
        notification_id: UUID,
        *,
        sent: bool,
        safe_error: str | None = None,
    ) -> None:
        with self.session_factory.begin() as session:
            session.execute(
                text(
                    """
                    UPDATE notificaciones
                    SET estado_envio = :status,
                        intentos = intentos + 1,
                        ultimo_error = :safe_error,
                        enviado_en = CASE
                            WHEN :sent THEN CURRENT_TIMESTAMP
                            ELSE enviado_en
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :notification_id
                    """
                ),
                {
                    "notification_id": str(notification_id),
                    "status": "enviado" if sent else "fallido",
                    "safe_error": safe_error,
                    "sent": sent,
                },
            )

    def get_for_classification(self, reclamo_id: UUID) -> ClaimForClassification | None:
        statement = text(
            """
            SELECT r.id, r.descripcion, r.urgencia::text AS urgencia,
                   e.nombre AS rubro_declarado
            FROM reclamos r
            LEFT JOIN especialidades e ON e.id = r.tipo_id
            WHERE r.id = :reclamo_id
            """
        )
        with self.session_factory() as session:
            row = session.execute(
                statement, {"reclamo_id": str(reclamo_id)}
            ).mappings().one_or_none()

        if row is None:
            return None
        return ClaimForClassification(
            reclamo_id=row["id"],
            descripcion=row["descripcion"],
            urgencia=row["urgencia"],
            rubro_declarado=row["rubro_declarado"],
            clausulas_contrato=[],
        )

    def persist_classification(
        self,
        reclamo_id: UUID,
        result: AgentClassificationResult,
    ) -> ClaimClassificationResponse:
        estado = "Escalado" if result.debe_escalar else "Clasificado"
        statement = text(
            """
            UPDATE reclamos
            SET estado = :estado,
                tipo_gasto = CAST(:tipo_gasto AS tipo_gasto_reclamo),
                confianza_clasificacion = :confianza,
                fundamento_clasificacion = :fundamento,
                motivo_escalado = :motivo_escalado,
                origen_clasificacion = 'agente',
                clasificado_en = now()
            WHERE id = :reclamo_id
            RETURNING id, estado, tipo_gasto::text AS tipo_gasto,
                      confianza_clasificacion, fundamento_clasificacion,
                      motivo_escalado
            """
        )
        params = {
            "estado": estado,
            "tipo_gasto": result.tipo_gasto,
            "confianza": result.confianza,
            "fundamento": result.fundamento,
            "motivo_escalado": result.motivo_escalado,
            "reclamo_id": str(reclamo_id),
        }
        with self.session_factory.begin() as session:
            session.execute(
                text("SELECT set_config('app.origen_reclamo', 'agente', true)")
            )
            row = session.execute(statement, params).mappings().one_or_none()

        if row is None:
            raise RuntimeError("El reclamo desapareció antes de persistir su clasificación.")
        return ClaimClassificationResponse(
            reclamo_id=row["id"],
            estado=row["estado"],
            tipo_gasto=row["tipo_gasto"],
            confianza=float(row["confianza_clasificacion"])
            if row["confianza_clasificacion"] is not None
            else None,
            fundamento=row["fundamento_clasificacion"],
            debe_escalar=result.debe_escalar,
            motivo_escalado=row["motivo_escalado"],
        )
