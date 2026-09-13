"""Persistencia contractual con permisos por participantes y escrituras serializadas."""

from contextlib import contextmanager
from datetime import date
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.services.contract_errors import ContractError


SELECT_CONTRACT = """
    SELECT c.*, i.nombre_completo AS inquilino_nombre,
           o.nombre_completo AS propietario_nombre,
           p.direccion, p.localidad, p.provincia
    FROM contratos c
    JOIN inquilinos i ON i.id = c.inquilino_id
    JOIN propietarios o ON o.id = c.propietario_id
    JOIN propiedades p ON p.id = c.propiedad_id
"""


def as_date(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


class SqlAlchemyContractsRepository:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    @staticmethod
    def _scope(user):
        if user.rol == "administrador":
            return "1=1", {}
        if user.rol not in {"inquilino", "propietario"}:
            return "1=0", {}
        alias = "i" if user.rol == "inquilino" else "o"
        return f"c.estado <> 'borrador' AND {alias}.usuario_id = :actor", {"actor": str(user.id)}

    def list(self, user, *, page=1, page_size=10, inquilino_id=None,
             propiedad_id=None, search=""):
        scope, params = self._scope(user)
        clauses = [scope]
        for key, value in (("inquilino_id", inquilino_id), ("propiedad_id", propiedad_id)):
            if value:
                clauses.append(f"c.{key} = :{key}")
                params[key] = str(value)
        if search.strip():
            clauses.append("(lower(i.nombre_completo) LIKE :search OR lower(o.nombre_completo) LIKE :search OR lower(p.direccion) LIKE :search)")
            params["search"] = f"%{search.strip().lower()}%"
        where = " WHERE " + " AND ".join(clauses)
        with self.session_factory() as s:
            total = s.execute(text("SELECT count(*) FROM (" + SELECT_CONTRACT + where + ") q"), params).scalar_one()
            rows = s.execute(text(SELECT_CONTRACT + where +
                                  " ORDER BY c.fecha_inicio DESC, c.created_at DESC, c.id "
                                  "LIMIT :limit OFFSET :offset"),
                             {**params, "limit": page_size, "offset": (page - 1) * page_size}).mappings().all()
        return [dict(r) for r in rows], int(total)

    def get(self, contract_id, user):
        scope, params = self._scope(user)
        with self.session_factory() as s:
            row = s.execute(text(SELECT_CONTRACT + f" WHERE c.id = :id AND ({scope})"),
                            {**params, "id": str(contract_id)}).mappings().one_or_none()
            if row is None:
                raise ContractError("No encontramos el contrato solicitado.", code="contract_not_found", status=404)
            result = dict(row)
            condition = "" if user.rol == "administrador" else " AND firmado = true"
            result["documentos"] = [dict(d) for d in s.execute(
                text("SELECT * FROM contrato_documentos WHERE contrato_id = :id" +
                     condition + " ORDER BY version DESC"), {"id": str(contract_id)}).mappings()]
            return result

    @staticmethod
    def _lock_suffix(session):
        return " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""

    @contextmanager
    def _write(self):
        try:
            with self.session_factory.begin() as s:
                yield s
        except IntegrityError as error:
            code = getattr(error.orig, "pgcode", None)
            if code == "23P01":
                raise ContractError("Ya existe un contrato firmado para esa propiedad en ese período.",
                                    code="contract_overlap", status=409) from error
            raise ContractError("Los datos cambiaron o entran en conflicto. Actualizá la pantalla e intentá nuevamente.",
                                code="contract_conflict", status=409) from error

    @staticmethod
    def _event(s, contract_id, actor, action, revision):
        s.execute(text("INSERT INTO contrato_eventos (id, contrato_id, accion, revision, actor_id) "
                       "VALUES (:id, :contract_id, :action, :revision, :actor)"),
                  {"id": str(uuid4()), "contract_id": str(contract_id), "actor": str(actor),
                   "action": action, "revision": revision})

    def create(self, payload, actor):
        data = payload.model_dump(mode="json")
        contract_id = str(uuid4())
        with self._write() as s:
            p = s.execute(text("SELECT id, propietario_id FROM propiedades WHERE id = :id" + self._lock_suffix(s)),
                          {"id": data["propiedad_id"]}).mappings().one_or_none()
            i = s.execute(text("SELECT id, propiedad_id FROM inquilinos WHERE id = :id" + self._lock_suffix(s)),
                          {"id": data["inquilino_id"]}).mappings().one_or_none()
            if p is None or i is None:
                raise ContractError("Seleccioná un inquilino y una propiedad existentes.", field="inquilino_id")
            if str(i["propiedad_id"]) != str(p["id"]):
                raise ContractError("La propiedad no está asociada al inquilino seleccionado.", field="propiedad_id")
            if data["contrato_anterior_id"]:
                previous = s.execute(text("SELECT * FROM contratos WHERE id = :id"),
                                     {"id": data["contrato_anterior_id"]}).mappings().one_or_none()
                if (previous is None or previous["estado"] == "borrador"
                    or str(previous["inquilino_id"]) != data["inquilino_id"]
                    or str(previous["propiedad_id"]) != data["propiedad_id"]):
                    raise ContractError("La renovación debe corresponder al mismo inquilino y propiedad.",
                                        field="contrato_anterior_id")
                if payload.fecha_inicio <= as_date(previous["fecha_finalizacion"] or previous["fecha_fin"]):
                    raise ContractError("La renovación debe comenzar después del contrato anterior.",
                                        field="fecha_inicio")
            s.execute(text("""
                INSERT INTO contratos (id, inquilino_id, propietario_id, propiedad_id,
                    contrato_anterior_id, fecha_inicio, fecha_fin, creado_por)
                VALUES (:id, :inquilino_id, :propietario_id, :propiedad_id,
                    :contrato_anterior_id, :fecha_inicio, :fecha_fin, :actor)
            """), {**data, "id": contract_id, "propietario_id": str(p["propietario_id"]), "actor": str(actor)})
            self._event(s, contract_id, actor, "creado", 1)
        return contract_id

    def _locked(self, s, contract_id, revision):
        row = s.execute(text("SELECT * FROM contratos WHERE id = :id" + self._lock_suffix(s)),
                        {"id": str(contract_id)}).mappings().one_or_none()
        if row is None:
            raise ContractError("No encontramos el contrato solicitado.", status=404)
        if row["revision"] != revision:
            raise ContractError("Otra operación actualizó el contrato. Recargá la pantalla antes de continuar.",
                                code="contract_stale", status=409)
        return row

    def update(self, contract_id, payload, actor):
        with self._write() as s:
            row = self._locked(s, contract_id, payload.revision)
            if row["estado"] != "borrador":
                raise ContractError("Las fechas de un contrato firmado se conservan. Registrá una renovación.",
                                    code="contract_immutable", status=409)
            if row["contrato_anterior_id"]:
                previous = s.execute(text("SELECT fecha_fin, fecha_finalizacion FROM contratos WHERE id = :id"),
                                     {"id": str(row["contrato_anterior_id"])}).mappings().one()
                if payload.fecha_inicio <= as_date(previous["fecha_finalizacion"] or previous["fecha_fin"]):
                    raise ContractError("La renovación debe comenzar después del contrato anterior.",
                                        field="fecha_inicio")
            s.execute(text("UPDATE contratos SET fecha_inicio=:fecha_inicio, fecha_fin=:fecha_fin, "
                           "revision=revision+1, updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                      {**payload.model_dump(mode="json"), "id": str(contract_id)})
            self._event(s, contract_id, actor, "editado", row["revision"] + 1)

    def save_document(self, contract_id, document, signed, revision, actor):
        with self._write() as s:
            row = self._locked(s, contract_id, revision)
            if row["estado"] == "finalizado" or (row["estado"] == "firmado" and not signed):
                raise ContractError("Un contrato confirmado solo admite nuevas versiones firmadas mientras no esté finalizado.",
                                    code="contract_immutable", status=409)
            if signed and row["estado"] == "borrador":
                # La exclusión SQL protege también contra escrituras concurrentes.
                collision = s.execute(text("""
                    SELECT id FROM contratos WHERE propiedad_id=:property_id
                        AND id<>:id AND estado<>'borrador'
                        AND fecha_inicio<=:end
                        AND coalesce(fecha_finalizacion, fecha_fin)>=:start
                    LIMIT 1
                """), {"property_id": str(row["propiedad_id"]), "id": str(contract_id),
                       "start": row["fecha_inicio"], "end": row["fecha_fin"]}).first()
                if collision:
                    raise ContractError("Ya existe un contrato firmado para esa propiedad en ese período.",
                                        code="contract_overlap", status=409)
            version = s.execute(text("SELECT coalesce(max(version), 0)+1 FROM contrato_documentos WHERE contrato_id=:id"),
                                {"id": str(contract_id)}).scalar_one()
            s.execute(text("""
                INSERT INTO contrato_documentos
                    (id, contrato_id, version, storage_path, nombre_archivo, tamano, sha256, firmado, creado_por)
                VALUES (:id, :contrato_id, :version, :storage_path, :nombre_archivo, :tamano, :sha256, :firmado, :actor)
            """), {**document, "contrato_id": str(contract_id), "version": version,
                   "firmado": signed, "actor": str(actor)})
            s.execute(text("UPDATE contratos SET estado=:state, revision=revision+1, "
                           "updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                      {"state": "firmado" if signed else row["estado"], "id": str(contract_id)})
            self._event(s, contract_id, actor,
                        "confirmado" if signed and row["estado"] == "borrador" else "documento",
                        revision + 1)

    def document_exists(self, document_id):
        with self.session_factory() as s:
            return s.execute(text("SELECT id FROM contrato_documentos WHERE id=:id"),
                             {"id": str(document_id)}).first() is not None

    def end(self, contract_id, payload, actor, today):
        with self._write() as s:
            row = self._locked(s, contract_id, payload.revision)
            if row["estado"] != "firmado":
                raise ContractError("Solo se puede finalizar un contrato firmado.", status=409)
            if not as_date(row["fecha_inicio"]) <= payload.fecha_finalizacion <= min(as_date(row["fecha_fin"]), today):
                raise ContractError("La finalización debe estar dentro de la vigencia y no puede ser futura.",
                                    field="fecha_finalizacion")
            s.execute(text("UPDATE contratos SET estado='finalizado', fecha_finalizacion=:end, "
                           "revision=revision+1, updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                      {"end": payload.fecha_finalizacion.isoformat(), "id": str(contract_id)})
            self._event(s, contract_id, actor, "finalizado", row["revision"] + 1)
