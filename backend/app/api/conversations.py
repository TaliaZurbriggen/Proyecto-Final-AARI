"""HU33: rutas de texto, nunca de aprobación de gasto o confirmación de visita."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import require_roles
from app.db.conversations import SqlAlchemyConversations
from app.schemas.auth import AuthenticatedUser
from app.schemas.conversations import ConversationActionRequest, ConversationMessageRequest, ConversationReadRequest
from app.services.conversations import ConversationError, conversations_enabled


def ensure_enabled():
    if not conversations_enabled():
        raise HTTPException(503, detail={'code': 'conversations_disabled', 'message': 'Las conversaciones todavía no están habilitadas.'}, headers={'Cache-Control': 'no-store'})


router = APIRouter(prefix='/conversaciones', tags=['conversaciones'], dependencies=[Depends(ensure_enabled)])
participant = require_roles('proveedor', 'inquilino', 'propietario', 'administrador', 'operador')


def get_conversations():
    return SqlAlchemyConversations()


def call(response, operation):
    response.headers['Cache-Control'] = 'no-store'
    try:
        return operation()
    except ConversationError as error:
        raise HTTPException(error.status, detail={'code': error.code, 'message': str(error)}, headers={'Cache-Control': 'no-store'}) from None
    except SQLAlchemyError:
        raise HTTPException(503, detail={'code': 'conversations_unavailable',
            'message': 'No pudimos abrir la conversación. Intentá nuevamente en unos momentos.'}, headers={'Cache-Control': 'no-store'}) from None


@router.get('/solicitudes/{request_id}')
def messages(request_id: UUID, response: Response,
             antes: int | None = Query(None, ge=1, le=9223372036854775807),
             despues: int | None = Query(None, ge=0, le=9223372036854775807),
             limite: int = Query(30, ge=1, le=50),
             user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.messages(request_id, user, before=antes, after=despues, limit=limite))


@router.post('/solicitudes/{request_id}/mensajes')
def send(request_id: UUID, payload: ConversationMessageRequest, response: Response,
         user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.send(request_id, user, payload))


@router.post('/solicitudes/{request_id}/lectura')
def read(request_id: UUID, payload: ConversationReadRequest, response: Response,
         user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.mark_read(request_id, user, payload.hasta_numero))


@router.get('/bandeja')
def inbox(response: Response, page: int = Query(1, ge=1, le=2147483647),
          page_size: int = Query(20, ge=1, le=50),
          user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.inbox(user, page=page, page_size=page_size))


@router.get('/hilos/{thread_id}')
def thread_messages(thread_id: UUID, response: Response,
                    antes: int | None = Query(None, ge=1, le=9223372036854775807),
                    despues: int | None = Query(None, ge=0, le=9223372036854775807),
                    limite: int = Query(30, ge=1, le=50),
                    user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.thread_messages(thread_id, user, before=antes, after=despues, limit=limite))


@router.post('/hilos/{thread_id}/mensajes')
def thread_send(thread_id: UUID, payload: ConversationMessageRequest, response: Response,
                user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.thread_send(thread_id, user, payload))


@router.post('/hilos/{thread_id}/lectura')
def thread_read(thread_id: UUID, payload: ConversationReadRequest, response: Response,
                user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.thread_read(thread_id, user, payload.hasta_numero))


@router.post('/solicitudes/{request_id}/consultas')
def open_questions(request_id: UUID, payload: ConversationActionRequest, response: Response,
                   user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.open_questions(request_id, user, payload))


@router.post('/hilos/{thread_id}/finalizar-consultas')
def finish_questions(thread_id: UUID, payload: ConversationActionRequest, response: Response,
                     user: AuthenticatedUser = Depends(participant), repo=Depends(get_conversations)):
    return call(response, lambda: repo.finish_questions(thread_id, user, payload))
