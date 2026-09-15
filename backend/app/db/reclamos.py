"""Acceso a datos para el alta, notificación y clasificación de reclamos."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.schemas.reclamos import (
    AgentClassificationResult,
    ClaimHistoryItem,
    ClaimClassificationResponse,
    ClaimCreatedResponse,
    ClaimPropertyContext,
    TenantClaimDetail,
    TenantClaimListItem,
)
from app.services.claim_notifications import (
    RETRY_INTERVAL_SECONDS,
    ClaimNotificationContext,
    notification_lease_seconds,
)
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

    def list_for_tenant(
        self, *, user_id: UUID, profile_id: UUID
    ) -> list[TenantClaimListItem]:
        statement = text(
            """
            SELECT r.id, r.numero AS reclamo_numero, r.descripcion,
                   r.urgencia::text AS urgencia,
                   r.estado, r.creado_en, r.updated_at,
                   p.id AS propiedad_id, p.direccion, p.provincia, p.localidad,
                   p.barrio, p.tipo::text AS propiedad_tipo, p.piso,
                   p.numero AS propiedad_numero
            FROM reclamos r
            JOIN inquilinos i ON i.id = r.inquilino_id
            JOIN propiedades p ON p.id = r.propiedad_id
            WHERE i.id = :profile_id
              AND i.usuario_id = :user_id
            ORDER BY r.creado_en DESC, r.numero DESC
            """
        )
        with self.session_factory() as session:
            rows = session.execute(
                statement,
                {"profile_id": str(profile_id), "user_id": str(user_id)},
            ).mappings().all()
        return [self._tenant_claim_from_row(row) for row in rows]

    def get_for_tenant(
        self, *, claim_id: UUID, user_id: UUID, profile_id: UUID
    ) -> TenantClaimDetail | None:
        statement = text(
            """
            SELECT r.id, r.numero AS reclamo_numero, r.descripcion,
                   r.urgencia::text AS urgencia,
                   r.estado, r.creado_en, r.updated_at,
                   p.id AS propiedad_id, p.direccion, p.provincia, p.localidad,
                   p.barrio, p.tipo::text AS propiedad_tipo, p.piso,
                   p.numero AS propiedad_numero
            FROM reclamos r
            JOIN inquilinos i ON i.id = r.inquilino_id
            JOIN propiedades p ON p.id = r.propiedad_id
            WHERE r.id = :claim_id
              AND i.id = :profile_id
              AND i.usuario_id = :user_id
            """
        )
        history_statement = text(
            """
            SELECT estado_anterior, estado_nuevo, origen, timestamp
            FROM reclamo_historial_estados
            WHERE reclamo_id = :claim_id
            ORDER BY timestamp ASC, id ASC
            """
        )
        params = {
            "claim_id": str(claim_id),
            "profile_id": str(profile_id),
            "user_id": str(user_id),
        }
        with self.session_factory() as session:
            row = session.execute(statement, params).mappings().one_or_none()
            if row is None:
                return None
            history_rows = session.execute(
                history_statement,
                {"claim_id": str(claim_id)},
            ).mappings().all()

        summary = self._tenant_claim_from_row(row)
        return TenantClaimDetail(
            **summary.model_dump(),
            historial=[ClaimHistoryItem.model_validate(item) for item in history_rows],
        )

    @staticmethod
    def _tenant_claim_from_row(row: Mapping[str, Any]) -> TenantClaimListItem:
        return TenantClaimListItem(
            id=row["id"],
            numero=int(row["reclamo_numero"]),
            descripcion=row["descripcion"],
            urgencia=row["urgencia"],
            estado=row["estado"],
            creado_en=row["creado_en"],
            updated_at=row["updated_at"],
            propiedad=ClaimPropertyContext(
                id=row["propiedad_id"],
                direccion=row["direccion"],
                provincia=row["provincia"],
                localidad=row["localidad"],
                barrio=row["barrio"],
                tipo=row["propiedad_tipo"],
                piso=row["piso"],
                numero=row["propiedad_numero"],
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
                             destinatario_contacto, canal, asunto, mensaje,
                             estado_reclamo, estado_envio, proximo_intento_en)
                        VALUES
                            (:id, :reclamo_id, 'inquilino', :recipient,
                             'email', :subject, :message, 'Recibido',
                             'pendiente', CURRENT_TIMESTAMP)
                        """
                    ),
                    {
                        "id": str(notification_id),
                        "reclamo_id": str(claim_id),
                        "recipient": context.tenant_email,
                        "subject": (
                            f"AARI - Reclamo #{claim_number:06d} recibido"
                        ),
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

    def claim_notification(
        self, notification_id: UUID
    ) -> ClaimNotificationContext | None:
        contexts = self._claim_notifications(
            limit=1,
            notification_id=notification_id,
        )
        return contexts[0] if contexts else None

    def claim_due_notifications(
        self, *, limit: int
    ) -> list[ClaimNotificationContext]:
        return self._claim_notifications(limit=limit)

    def _claim_notifications(
        self,
        *,
        limit: int,
        notification_id: UUID | None = None,
    ) -> list[ClaimNotificationContext]:
        id_filter = "AND n.id = :notification_id" if notification_id else ""
        statement = text(
            f"""
            WITH candidates AS (
                SELECT n.id
                FROM notificaciones n
                WHERE n.intentos < 3
                  AND (
                      (
                          n.estado_envio = 'pendiente'
                          AND n.proximo_intento_en <= CURRENT_TIMESTAMP
                      )
                      OR (
                          n.estado_envio = 'procesando'
                          AND n.bloqueado_hasta <= CURRENT_TIMESTAMP
                      )
                  )
                  {id_filter}
                ORDER BY n.proximo_intento_en ASC, n.created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            )
            UPDATE notificaciones n
            SET estado_envio = 'procesando',
                intentos = n.intentos + 1,
                bloqueado_hasta = CURRENT_TIMESTAMP
                    + make_interval(secs => :lease_seconds),
                updated_at = CURRENT_TIMESTAMP
            FROM candidates c, reclamos r
            WHERE n.id = c.id
              AND r.id = n.reclamo_id
            RETURNING n.id, n.destinatario_contacto, n.canal, n.asunto,
                      n.mensaje, n.intentos, r.numero
            """
        )
        params: dict[str, object] = {
            "lease_seconds": notification_lease_seconds(),
            "limit": max(1, min(limit, 50)),
        }
        if notification_id:
            params["notification_id"] = str(notification_id)
        with self.session_factory.begin() as session:
            session.execute(
                text(
                    """
                    UPDATE notificaciones
                    SET estado_envio = 'fallido',
                        ultimo_error = COALESCE(
                            ultimo_error,
                            'La entrega se interrumpió durante el último intento.'
                        ),
                        bloqueado_hasta = NULL,
                        proximo_intento_en = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE estado_envio = 'procesando'
                      AND intentos >= 3
                      AND bloqueado_hasta <= CURRENT_TIMESTAMP
                    """
                )
            )
            rows = session.execute(statement, params).mappings().all()
        return [
            ClaimNotificationContext(
                id=UUID(str(row["id"])),
                recipient=str(row["destinatario_contacto"]),
                claim_number=int(row["numero"]),
                channel=str(row["canal"]),
                subject=str(row["asunto"]),
                message=str(row["mensaje"]),
                attempt_number=int(row["intentos"]),
            )
            for row in rows
        ]

    def mark_notification_result(
        self,
        notification_id: UUID,
        *,
        attempt_number: int,
        sent: bool,
        safe_error: str | None = None,
    ) -> bool:
        with self.session_factory.begin() as session:
            result = session.execute(
                text(
                    """
                    UPDATE notificaciones
                    SET estado_envio = CASE
                            WHEN :sent THEN 'enviado'
                            WHEN intentos >= 3 THEN 'fallido'
                            ELSE 'pendiente'
                        END,
                        ultimo_error = :safe_error,
                        enviado_en = CASE
                            WHEN :sent THEN CURRENT_TIMESTAMP
                            ELSE enviado_en
                        END,
                        proximo_intento_en = CASE
                            WHEN NOT :sent AND intentos < 3
                                THEN CURRENT_TIMESTAMP
                                     + make_interval(secs => :retry_seconds)
                            ELSE NULL
                        END,
                        bloqueado_hasta = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :notification_id
                      AND estado_envio = 'procesando'
                      AND intentos = :attempt_number
                    """
                ),
                {
                    "attempt_number": attempt_number,
                    "notification_id": str(notification_id),
                    "safe_error": safe_error,
                    "sent": sent,
                    "retry_seconds": RETRY_INTERVAL_SECONDS,
                },
            )
        return result.rowcount == 1

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
