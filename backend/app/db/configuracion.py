"""Acceso acotado al destinatario de reportes; no expone otras configuraciones."""

from sqlalchemy import text

from app.db.database import SessionLocal
from app.schemas.expensas import AgencyEmailResponse
from app.services.expense_notifications import agency_email


class SqlAlchemyAgencyConfigurationRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def get(self) -> AgencyEmailResponse:
        with self.session_factory() as session:
            row = session.execute(text("""
                SELECT valor, updated_at FROM configuracion_sistema
                WHERE clave='correo_contacto_inmobiliaria'
            """)).mappings().one_or_none()
        email = agency_email(row["valor"]) if row else None
        return AgencyEmailResponse(email=email, configurado=email is not None,
                                   updated_at=row["updated_at"] if row else None)

    def update(self, email: str) -> AgencyEmailResponse:
        with self.session_factory.begin() as session:
            row = session.execute(text("""
                INSERT INTO configuracion_sistema (clave, valor, descripcion)
                VALUES ('correo_contacto_inmobiliaria', :email, 'Contacto para reportes de expensas')
                ON CONFLICT (clave) DO UPDATE
                SET valor=excluded.valor, updated_at=CURRENT_TIMESTAMP
                RETURNING valor, updated_at
            """), {"email": email}).mappings().one()
        return AgencyEmailResponse(email=row["valor"], configurado=True, updated_at=row["updated_at"])
