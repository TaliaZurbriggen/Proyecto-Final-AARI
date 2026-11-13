"""Pruebas aisladas: no cargar AARI ni sus workers/conexiones externas."""

import base64
import importlib.util
import json
from email import message_from_bytes
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_module = load_script("check_gmail_api")
auth_module = load_script("authorize_gmail_api")
SCOPE = probe_module.SEND_SCOPE
CREDS = {"client_id": "fake-client", "client_secret": "fake-secret",
         "refresh_token": "fake-refresh", "token_uri": probe_module.TOKEN_URI,
         "scopes": [SCOPE]}
TOKEN = {"access_token": "fake-access", "scope": SCOPE, "token_type": "Bearer"}


def execute(handler, *, credentials=None, send=False, sender="sender@example.com"):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return probe_module.probe(CREDS if credentials is None else credentials,
                                  sender, send_to_self=send, client=client)


def test_default_only_refreshes_no_mail_or_profile_read():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=TOKEN)
    assert execute(handler) == "auth_refresh_ok"
    assert [str(request.url) for request in calls] == [probe_module.TOKEN_URI]
    assert b"grant_type=refresh_token" in calls[0].content


def test_explicit_send_only_to_same_address():
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=TOKEN)
        assert str(request.url) == probe_module.SEND_URI
        assert request.headers["Authorization"] == "Bearer fake-access"
        message = message_from_bytes(base64.urlsafe_b64decode(json.loads(request.content)["raw"]))
        assert message["To"] == message["From"] == "sender@example.com"
        assert message.get_content_type() == "text/plain"
        return httpx.Response(200, json={"id": "synthetic-id"})
    assert execute(handler, send=True) == "accepted_for_delivery"
    assert len(calls) == 2


@pytest.mark.parametrize("change", [
    {"token_uri": "https://attacker.example/token"},
    {"scopes": [SCOPE, "https://mail.google.com/"]},
    {"scopes": []}, {"refresh_token": ""}, {"client_secret": ""},
])
def test_bad_config_stops_before_network(change):
    def handler(request):
        pytest.fail("No debe haber red")
    with pytest.raises(probe_module.ProbeError):
        execute(handler, credentials={**CREDS, **change})


@pytest.mark.parametrize("sender", ["", "name <sender@example.com>",
                                    "sender@example.com\r\nBcc: other@example.com"])
def test_invalid_sender_stops_before_network(sender):
    with pytest.raises(probe_module.ProbeError):
        execute(lambda _: pytest.fail("No debe haber red"), sender=sender)


@pytest.mark.parametrize("status", [301, 400, 401, 403, 429, 500, 503])
def test_refresh_errors_never_send_or_leak_remote_body(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="private-response-fake-secret",
                              headers={"Location": "https://attacker.example/"})
    with pytest.raises(probe_module.ProbeError) as error:
        execute(handler, send=True)
    assert len(calls) == 1
    assert "private-response" not in str(error.value)
    assert "fake-secret" not in str(error.value)


@pytest.mark.parametrize("token", [{**TOKEN, "scope": SCOPE + " https://mail.google.com/"},
                                   {**TOKEN, "scope": ""}, {**TOKEN, "access_token": ""},
                                   {**TOKEN, "token_type": "Other"}])
def test_unexpected_grants_never_send(token):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=token)
    with pytest.raises(probe_module.ProbeError):
        execute(handler, send=True)
    assert len(calls) == 1


@pytest.mark.parametrize("body", ["not-json", "[]"])
def test_malformed_response(body):
    with pytest.raises(probe_module.ProbeError):
        execute(lambda _: httpx.Response(200, text=body), send=True)


@pytest.mark.parametrize("failure", ["timeout", "redirect", "error", "missing-id"])
def test_send_failures_are_not_retried(failure):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=TOKEN)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-request-data", request=request)
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "https://attacker.example/"})
        if failure == "error":
            return httpx.Response(503, text="private-response-data")
        return httpx.Response(200, json={})
    with pytest.raises(probe_module.ProbeError) as error:
        execute(handler, send=True)
    assert len(calls) == 2
    assert "private" not in str(error.value)


def test_authorization_is_send_only_local_pkce_and_exclusive(tmp_path):
    client = tmp_path / "client.json"
    output = tmp_path / "authorized.json"
    client.write_text(json.dumps({"web": {
        "client_id": "fake-client", "client_secret": "fake-secret",
        "auth_uri": auth_module.AUTH_URI, "token_uri": auth_module.TOKEN_URI,
        "redirect_uris": [auth_module.REDIRECT_URI],
    }}))
    class FakeFlow:
        @classmethod
        def from_client_config(cls, config, **kwargs):
            assert kwargs == {"scopes": [SCOPE], "autogenerate_code_verifier": True}
            return cls()
        def run_local_server(self, **kwargs):
            assert kwargs["host"] == "localhost" and kwargs["port"] == 8765
            assert kwargs["open_browser"] is False
            assert kwargs["access_type"] == "offline"
            assert kwargs["include_granted_scopes"] == "false"
            return SimpleNamespace(granted_scopes=[SCOPE], scopes=[SCOPE],
                refresh_token="fake-refresh",
                to_json=lambda strip: json.dumps(CREDS) if strip == ["token", "expiry"] else "")
    auth_module.authorize(client, output, flow_class=FakeFlow)
    assert json.loads(output.read_text()) == CREDS
    with pytest.raises(ValueError, match="Ya existe"):
        auth_module.authorize(client, output, flow_class=FakeFlow)


def test_authorization_rejects_non_google_endpoints(tmp_path):
    client = tmp_path / "client.json"
    client.write_text(json.dumps({"web": {"auth_uri": "https://attacker.example/"}}))
    with pytest.raises(ValueError, match="Cliente OAuth"):
        auth_module.authorize(client, tmp_path / "output.json")


@pytest.mark.parametrize("granted,refresh", [([SCOPE, "https://mail.google.com/"], "fake"),
                                           ([SCOPE], None)])
def test_authorization_does_not_persist_unexpected_permission(tmp_path, granted, refresh):
    client = tmp_path / "client.json"
    output = tmp_path / "output.json"
    client.write_text(json.dumps({"web": {
        "client_id": "fake-client", "client_secret": "fake-secret",
        "auth_uri": auth_module.AUTH_URI, "token_uri": auth_module.TOKEN_URI,
        "redirect_uris": [auth_module.REDIRECT_URI],
    }}))
    class FakeFlow:
        @classmethod
        def from_client_config(cls, *args, **kwargs):
            return cls()
        def run_local_server(self, **kwargs):
            return SimpleNamespace(granted_scopes=granted, scopes=[SCOPE], refresh_token=refresh)
    with pytest.raises(ValueError, match="exclusivamente"):
        auth_module.authorize(client, output, flow_class=FakeFlow)
    assert not output.exists()


def test_refresh_network_failure_never_sends():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("fake-secret", request=request)
    with pytest.raises(probe_module.ProbeError, match="no se envió correo") as error:
        execute(handler, send=True)
    assert len(calls) == 1 and "fake-secret" not in str(error.value)
