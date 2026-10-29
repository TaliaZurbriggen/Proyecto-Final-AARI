"""HU33 HTTP y validación pura; no red externa ni base compartida."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.api.auth import get_current_user
from app.api.conversations import get_conversations
from app.main import app
from app.schemas.auth import AuthenticatedUser
from app.schemas.conversations import ConversationActionRequest, ConversationMessageRequest, ConversationReadRequest
from app.services.conversations import ConversationError, budget_write_reason


@pytest.mark.parametrize('value', ['', '   ', 'x' * 2001, 'texto\x00inválido', '\ud800', 123, True])
def test_message_validation(value):
    with pytest.raises(ValidationError):
        ConversationMessageRequest(request_id=uuid4(), texto=value)


@pytest.mark.parametrize('extra', ['autor_id', 'origen', 'finalidad', 'rol', 'creado_en'])
def test_client_cannot_choose_identity_origin_or_stage(extra):
    with pytest.raises(ValidationError):
        ConversationMessageRequest(request_id=uuid4(), texto='Consulta válida', **{extra: 'agente'})


def test_text_is_not_interpreted_as_approval_and_newlines_are_canonical():
    body = ConversationMessageRequest(request_id=uuid4(), texto='  Acepto $10000\r\nmartes a las 10.  ')
    assert body.texto == 'Acepto $10000\nmartes a las 10.'


@pytest.mark.parametrize('value', [-1, 1.2, True, '5', 9223372036854775808])
def test_read_positions_are_explicit_integers(value):
    with pytest.raises(ValidationError): ConversationReadRequest(hasta_numero=value)


def test_answered_quote_can_be_clarified_after_budget_deadline():
    now = datetime.now(timezone.utc)
    row = {'ronda_estado': 'disponibles', 'cerrada_en': now, 'vence_en': now - timedelta(hours=1),
           'presupuesto_id': uuid4(), 'proveedor_seleccionado_id': None, 'presupuesto_seleccionado_id': None}
    assert budget_write_reason(row, now, current=True) is None
    assert budget_write_reason({**row, 'presupuesto_id': None}, now, current=True)
    assert budget_write_reason({**row, 'ronda_estado': 'cancelada'}, now, current=True)
    assert budget_write_reason({**row, 'proveedor_seleccionado_id': uuid4()}, now, current=True)
    assert budget_write_reason(row, now, current=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'true')
    user = AuthenticatedUser(id=uuid4(), email='provider@example.com', rol='proveedor',
                             primer_ingreso=False, perfil_id=uuid4())
    calls = []
    repo = SimpleNamespace(
        messages=lambda *args, **kwargs: calls.append(('get', args, kwargs)) or {'items': []},
        send=lambda *args: calls.append(('send', args)) or {'repetido': False},
        mark_read=lambda *args: calls.append(('read', args)) or {'leido_hasta': args[-1]},
    )
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_conversations] = lambda: repo
    with TestClient(app) as http: yield http, user, repo, calls
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_conversations, None)


@pytest.mark.parametrize('role', ['proveedor', 'inquilino', 'propietario', 'administrador', 'operador'])
def test_session_identity_forwarded_and_no_store(client, role):
    http, user, _, calls = client
    account = user.model_copy(update={'rol': role})
    app.dependency_overrides[get_current_user] = lambda: account
    rid = uuid4()
    result = http.get(f'/conversaciones/solicitudes/{rid}?despues=3&limite=10')
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert calls[0] == ('get', (rid, account), {'after': 3, 'before': None, 'limit': 10})


@pytest.mark.parametrize('query', ['limite=0', 'limite=51', 'antes=0', 'despues=-1', 'despues=bad'])
def test_bad_pagination_never_queries_repository(client, query):
    http, _, _, calls = client
    assert http.get(f'/conversaciones/solicitudes/{uuid4()}?{query}').status_code == 422
    assert not calls


def test_post_and_read_use_session_and_typed_payload(client):
    http, user, _, calls = client
    rid, key = uuid4(), uuid4()
    assert http.post(f'/conversaciones/solicitudes/{rid}/mensajes', json={'request_id': str(key), 'texto': 'Una consulta'}).status_code == 200
    assert calls[-1][1][1] is user and calls[-1][1][2].request_id == key
    assert http.post(f'/conversaciones/solicitudes/{rid}/lectura', json={'hasta_numero': 2}).json() == {'leido_hasta': 2}


def test_disabled_feature_and_first_login_do_not_query(client, monkeypatch):
    http, user, _, calls = client
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'false')
    assert http.get(f'/conversaciones/solicitudes/{uuid4()}').status_code == 503
    monkeypatch.setenv('AARI_CONVERSATIONS_ENABLED', 'true')
    app.dependency_overrides[get_current_user] = lambda: user.model_copy(update={'primer_ingreso': True})
    assert http.get(f'/conversaciones/solicitudes/{uuid4()}').status_code == 403
    assert not calls


def test_anonymous_requires_session(client):
    app.dependency_overrides.pop(get_current_user)
    assert client[0].get(f'/conversaciones/solicitudes/{uuid4()}').status_code == 401


@pytest.mark.parametrize('kind', ['not_found', 'storage'])
def test_errors_are_controlled_and_do_not_expose_database_details(client, kind):
    def fail(*_args, **_kwargs):
        if kind == 'not_found':
            raise ConversationError('No encontramos esa conversación.', status=404, code='conversation_not_found')
        raise OperationalError('private SQL', {}, Exception('private connection'))
    client[2].messages = fail
    result = client[0].get(f'/conversaciones/solicitudes/{uuid4()}')
    assert result.status_code == (404 if kind == 'not_found' else 503)
    assert 'private' not in result.text


@pytest.mark.parametrize('extra', ['usuario_id', 'inquilino_id', 'finalidad', 'estado'])
def test_consultation_action_never_accepts_arbitrary_participants(extra):
    with pytest.raises(ValidationError):
        ConversationActionRequest(request_id=uuid4(), **{extra: str(uuid4())})


@pytest.mark.parametrize('query', ['page=0', 'page=2147483648', 'page_size=0', 'page_size=51'])
def test_inbox_invalid_pagination_stops_before_repository(client, query):
    http, _, _, calls = client
    assert http.get('/conversaciones/bandeja?' + query).status_code == 422
    assert not calls


def test_thread_and_inbox_routes_use_authenticated_identity(client):
    http, user, repo, calls = client
    tid = uuid4()
    repo.inbox = lambda account, **kwargs: calls.append(('inbox', account, kwargs)) or {'items': []}
    repo.thread_messages = lambda thread, account, **kwargs: calls.append(('thread', thread, account, kwargs)) or {'items': []}
    repo.thread_send = lambda thread, account, body: calls.append(('post', thread, account, body)) or {'repetido': False}
    repo.thread_read = lambda thread, account, through: {'leido_hasta': through}
    assert http.get('/conversaciones/bandeja?page=2&page_size=5').status_code == 200
    assert calls[-1] == ('inbox', user, {'page': 2, 'page_size': 5})
    result = http.get(f'/conversaciones/hilos/{tid}?antes=20')
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert calls[-1][1:3] == (tid, user)
    assert http.post(f'/conversaciones/hilos/{tid}/mensajes', json={'request_id': str(uuid4()), 'texto': 'Consulta técnica'}).status_code == 200
    assert calls[-1][2] is user
    assert http.post(f'/conversaciones/hilos/{tid}/lectura', json={'hasta_numero': 3}).json()['leido_hasta'] == 3


def test_consultation_lifecycle_has_explicit_deduplication_keys(client):
    http, user, repo, calls = client
    rid, tid, key = uuid4(), uuid4(), uuid4()
    repo.open_questions = lambda request, account, body: calls.append(('open', request, account, body)) or {'id': str(tid)}
    repo.finish_questions = lambda thread, account, body: calls.append(('finish', thread, account, body)) or {'id': str(tid)}
    assert http.post(f'/conversaciones/solicitudes/{rid}/consultas', json={'request_id': str(key)}).status_code == 200
    assert calls[-1][1:3] == (rid, user) and calls[-1][3].request_id == key
    assert http.post(f'/conversaciones/hilos/{tid}/finalizar-consultas', json={'request_id': str(key)}).status_code == 200
    assert calls[-1][1:3] == (tid, user)
    assert http.post(f'/conversaciones/solicitudes/{rid}/consultas', json={'request_id': str(key), 'inquilino_id': str(user.id)}).status_code == 422
