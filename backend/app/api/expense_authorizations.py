"""Portal del propietario: no aceptar identidad o rol enviados por el cliente."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import require_roles
from app.db.expense_authorizations import SqlAlchemyExpenseAuthorizationsRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.expense_authorizations import (
    ExpenseDecisionRequest, ExpenseDecisionResult, OwnerExpenseClaim, OwnerExpenseClaimsPage,
)
from app.services.expense_authorizations_service import (
    ExpenseAuthorizationConflict, ExpenseAuthorizationForbidden, ExpenseAuthorizationNotFound,
)

router = APIRouter(tags=["autorizaciones de gastos"])
require_owner = require_roles("propietario")


def get_expense_authorizations_repository():
    return SqlAlchemyExpenseAuthorizationsRepository()


def _run(action):
    try:
        return action()
    except ExpenseAuthorizationNotFound:
        raise HTTPException(404, detail={"code": "not_found", "message": "No encontramos ese reclamo."}) from None
    except ExpenseAuthorizationForbidden:
        raise HTTPException(403, detail={"code": "forbidden", "message": "Tu cuenta no puede registrar esta decisión."}) from None
    except ExpenseAuthorizationConflict as error:
        raise HTTPException(409, detail={"code": "decision_conflict", "message": str(error)}) from error


@router.get("/propietario/reclamos", response_model=OwnerExpenseClaimsPage)
def list_expenses(page: int = Query(default=1, ge=1, le=1000000),
                  user: AuthenticatedUser = Depends(require_owner),
                  repository=Depends(get_expense_authorizations_repository)):
    return _run(lambda: repository.list(user, page=page))


@router.get("/reclamos/{claim_id}/autorizacion", response_model=OwnerExpenseClaim)
def get_expense(claim_id: UUID, user: AuthenticatedUser = Depends(require_owner),
                repository=Depends(get_expense_authorizations_repository)):
    return _run(lambda: repository.get(claim_id, user))


@router.post("/reclamos/{claim_id}/autorizar", response_model=ExpenseDecisionResult)
def authorize(claim_id: UUID, body: ExpenseDecisionRequest,
              user: AuthenticatedUser = Depends(require_owner),
              repository=Depends(get_expense_authorizations_repository)):
    return _run(lambda: repository.decide(claim_id, user, body, decision="autorizar"))


@router.post("/reclamos/{claim_id}/rechazar", response_model=ExpenseDecisionResult)
def reject(claim_id: UUID, body: ExpenseDecisionRequest,
           user: AuthenticatedUser = Depends(require_owner),
           repository=Depends(get_expense_authorizations_repository)):
    return _run(lambda: repository.decide(claim_id, user, body, decision="rechazar"))
