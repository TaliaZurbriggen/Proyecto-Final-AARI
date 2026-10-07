"""Rutas privadas de HU14 para administración y operación."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.auth import require_roles
from app.db.expensas import ExpenseNotFoundError, ExpenseNotePermissionError, SqlAlchemyExpensesRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.expensas import ExpenseDetail, ExpenseFilters, ExpenseNote, ExpenseNoteRequest, ExpensePage


router = APIRouter(prefix="/expensas", tags=["expensas"])
require_expense_reader = require_roles("administrador", "operador")


def get_expenses_repository():
    return SqlAlchemyExpensesRepository()


def missing_expense():
    return HTTPException(status_code=404, detail={"code": "expense_not_found", "message": "No encontramos ese reclamo de expensa."})


@router.get("", response_model=ExpensePage)
def list_expenses(filters: Annotated[ExpenseFilters, Query()], response: Response,
                  user: AuthenticatedUser = Depends(require_expense_reader),
                  repository=Depends(get_expenses_repository)):
    result = repository.list(filters)
    response.headers["X-Total-Count"] = str(result.total)
    return result


@router.get("/{claim_id}", response_model=ExpenseDetail)
def get_expense(claim_id: UUID, user: AuthenticatedUser = Depends(require_expense_reader),
                repository=Depends(get_expenses_repository)):
    try:
        return repository.get(claim_id)
    except ExpenseNotFoundError:
        raise missing_expense() from None


@router.post("/{claim_id}/notas", response_model=ExpenseNote, status_code=201)
def add_expense_note(claim_id: UUID, payload: ExpenseNoteRequest,
                     user: AuthenticatedUser = Depends(require_expense_reader),
                     repository=Depends(get_expenses_repository)):
    try:
        return repository.add_note(claim_id, payload.contenido, user.id)
    except ExpenseNotFoundError:
        raise missing_expense() from None
    except ExpenseNotePermissionError:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Tu cuenta no puede agregar notas."}) from None
