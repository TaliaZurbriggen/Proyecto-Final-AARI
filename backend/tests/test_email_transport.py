"""HU35: todos los canales HTTP/SMTP son dobles, nunca correos reales."""

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime
from uuid import UUID

import httpx
import pytest

from app.services import email_transport as mail


FAKE_SETTINGS = mail.GmailSettings("AARI <sender@example.com>", "fake-client", "fake-secret", "fake-refresh")
TOKEN = {"access_token": "fake-access", "token_type": "Bearer", "expires_in": 3600,
         "scope": mail.SEND_SCOPE}


@pytest.fixture(autouse=True)
def isolated_email_config(monkeypatch):
    for name in ("EMAIL_PROVIDER", "EMAIL_FROM", "GMAIL_CREDENTIALS_FILE", "GMAIL_CLIENT_ID",
                 "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "SMTP_HOST", "SMTP_FROM"):
        monkeypatch.delenv(name, raising=False)
    mail._gmail_transport.cache_clear()
    yield
    mail._gmail_transport.cache_clear()


def transport(handler, **kwargs):
    return mail.GmailApiEmailTransport(FAKE_SETTINGS, client_factory=lambda: httpx.Client(
        transport=httpx.MockTransport(handler)), **kwargs)


def deliver(sender):
    sender.send(recipient="recipient@example.com", subject="Aviso sintético", body="Texto sin datos reales.")


def test_https_and_mime_are_exact_and_do_not_touch_profile():
    calls = []
    def handler(request):
        calls.append(request)
        if str(request.url) == mail.TOKEN_URL:
            assert request.headers.get("authorization") is None
            assert b"grant_type=refresh_token" in request.content
            return httpx.Response(200, json=TOKEN)
        assert str(request.url) == mail.SEND_URL
        assert request.headers["authorization"] == "Bearer fake-access"
        msg = message_from_bytes(base64.urlsafe_b64decode(json.loads(request.content)["raw"]), policy=policy.default)
        assert msg["From"] == "AARI <sender@example.com>"
        assert msg["To"] == "recipient@example.com"
        assert msg["Subject"] == "Aviso sintético"
        assert msg["Date"] and msg["Message-ID"]
        assert msg.get_content().strip() == "Texto sin datos reales."
        return httpx.Response(200, json={"id": "synthetic"})
    deliver(transport(handler))
    assert len(calls) == 2
    assert all(request.url.scheme == "https" for request in calls)


@pytest.mark.parametrize("sender", ["sender@example.com", "AARI <sender@example.com>"])
def test_common_mime_has_valid_utc_date_and_private_unique_message_id(sender):
    before = datetime.now(UTC).replace(microsecond=0)
    messages = [mail._message(sender, "recipient@example.com", "Invitación", "Texto")
                for _ in range(30)]
    after = datetime.now(UTC) + timedelta(seconds=1)
    ids = set()
    for message in messages:
        parsed = message_from_bytes(message.as_bytes(), policy=policy.default)
        assert not parsed.defects
        assert len(parsed.get_all("Date")) == len(parsed.get_all("Message-ID")) == 1
        date = parsedate_to_datetime(str(parsed["Date"]))
        assert date.utcoffset() == timedelta(0) and before <= date <= after
        message_id = str(parsed["Message-ID"])
        unique, suffix = message_id[1:-1].split(".", 1)
        assert UUID(unique).version == 4 and suffix == "aari@example.com"
        assert "recipient" not in message_id and "sender" not in message_id
        ids.add(message_id)
    assert len(ids) == len(messages)


def test_token_is_cached_then_refreshed_before_expiration():
    calls, now = [], [0.0]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=TOKEN if str(request.url) == mail.TOKEN_URL else {"id": "ok"})
    sender = transport(handler, clock=lambda: now[0])
    deliver(sender)
    now[0] = 3500
    deliver(sender)
    now[0] = 3541
    deliver(sender)
    assert calls.count(mail.TOKEN_URL) == 2 and calls.count(mail.SEND_URL) == 3


def test_parallel_routes_share_one_refresh_without_losing_messages():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=TOKEN if str(request.url) == mail.TOKEN_URL else {"id": "ok"})
    sender = transport(handler)
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda _: deliver(sender), range(30)))
    assert calls.count(mail.TOKEN_URL) == 1 and calls.count(mail.SEND_URL) == 30


@pytest.mark.parametrize("data", [
    {**TOKEN, "scope": mail.SEND_SCOPE + " https://mail.google.com/"},
    {**TOKEN, "scope": ""}, {**TOKEN, "expires_in": 0}, {**TOKEN, "expires_in": "3600"},
    {**TOKEN, "expires_in": True}, {**TOKEN, "token_type": 12},
    {**TOKEN, "access_token": ""}, {**TOKEN, "access_token": "bad\r\nheader"}, [],
])
def test_invalid_grant_response_never_sends_or_leaks(data):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=data)
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(handler))
    assert len(calls) == 1 and not error.value.retryable
    assert "fake" not in str(error.value)


@pytest.mark.parametrize("status,retryable", [(400, False), (401, False), (403, False),
                                              (429, True), (503, True), (302, False)])
def test_failed_refresh_never_sends_or_follows_redirect(status, retryable):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "private-fake-secret"},
                              headers={"Location": "https://other.example/token"})
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(handler))
    assert len(calls) == 1 and error.value.retryable is retryable
    assert "private" not in str(error.value)


def test_expired_weekly_authorization_reports_reauthorization_no_send():
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(lambda _: httpx.Response(400, json={"error": "invalid_grant",
                                       "error_description": "private-user-or-secret"})))
    assert error.value.code == "gmail_reauthorization_required"
    assert "Volvé a autorizar" in str(error.value)
    assert not error.value.retryable and not error.value.uncertain
    assert "private" not in str(error.value)


@pytest.mark.parametrize("status,retryable,uncertain", [
    (400, False, False), (401, True, False), (403, False, False), (429, True, False),
    (500, False, True), (503, False, True), (307, False, False),
])
def test_send_error_policy_never_resends_in_same_attempt(status, retryable, uncertain):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=TOKEN) if str(request.url) == mail.TOKEN_URL else httpx.Response(
            status, json={"error": {"message": "private-fake-secret"}},
            headers={"Location": "https://other.example/send"})
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(handler))
    assert calls == [mail.TOKEN_URL, mail.SEND_URL]
    assert error.value.retryable is retryable and error.value.uncertain is uncertain
    assert "private" not in str(error.value)


@pytest.mark.parametrize("reason,retryable", [("rateLimitExceeded", True),
    ("userRateLimitExceeded", True), ("insufficientPermissions", False), ("domainPolicy", False)])
def test_403_only_known_temporary_rejections_can_retry(reason, retryable):
    def handler(request):
        if str(request.url) == mail.TOKEN_URL:
            return httpx.Response(200, json=TOKEN)
        return httpx.Response(403, json={"error": {"errors": [{"reason": reason}]}})
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(handler))
    assert error.value.retryable is retryable


@pytest.mark.parametrize("phase,error_type,retryable,uncertain", [
    ("token", httpx.ReadTimeout, True, False), ("send", httpx.ConnectTimeout, True, False),
    ("send", httpx.ConnectError, True, False), ("send", httpx.ReadTimeout, False, True),
    ("send", httpx.WriteTimeout, False, True), ("send", httpx.RemoteProtocolError, False, True),
])
def test_network_errors_are_safe_and_do_not_trigger_hidden_retries(phase, error_type, retryable, uncertain):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if phase == "token" or str(request.url) == mail.SEND_URL:
            raise error_type("private-fake-secret", request=request)
        return httpx.Response(200, json=TOKEN)
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(handler))
    assert len(calls) == (1 if phase == "token" else 2)
    assert error.value.retryable is retryable and error.value.uncertain is uncertain
    assert "private" not in str(error.value)


@pytest.mark.parametrize("response", ["not-json", "[]", "{}", '{"id":123}'])
def test_unconfirmable_success_never_retries(response):
    def handler(request):
        return (httpx.Response(200, json=TOKEN) if str(request.url) == mail.TOKEN_URL
                else httpx.Response(200, text=response))
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(handler))
    assert error.value.uncertain and not error.value.retryable


def test_invalid_access_token_is_invalidated_for_next_attempt_not_resubmitted_now():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if str(request.url) == mail.TOKEN_URL:
            return httpx.Response(200, json=TOKEN)
        return httpx.Response(401, json={}) if calls.count(mail.SEND_URL) == 1 else httpx.Response(200, json={"id": "ok"})
    sender = transport(handler)
    with pytest.raises(mail.EmailDeliveryError):
        deliver(sender)
    assert len(calls) == 2
    deliver(sender)
    assert calls == [mail.TOKEN_URL, mail.SEND_URL] * 2


@pytest.mark.parametrize("kwargs", [{"recipient": "a@example.com,b@example.com"},
    {"subject": "Aviso\nBcc: other@example.com"}, {"recipient": "a@example.com\r\nother"},
    {"body": "x" * mail.MAX_MESSAGE_BYTES}])
def test_bad_or_oversized_message_stops_before_network(kwargs):
    sender = transport(lambda _: pytest.fail("No debe haber red"))
    with pytest.raises(mail.EmailDeliveryError):
        sender.send(**{"recipient": "recipient@example.com", "subject": "Aviso", "body": "Texto", **kwargs})


def test_secret_config_file_is_exact_scope_and_not_visible_in_repr(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    data = {"client_id": "fake-client", "client_secret": "fake-secret", "refresh_token": "fake-refresh",
            "token_uri": mail.TOKEN_URL, "scopes": [mail.SEND_SCOPE]}
    path.write_text(json.dumps(data))
    monkeypatch.setenv("EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("GMAIL_CREDENTIALS_FILE", str(path))
    settings = mail.GmailSettings.from_environment()
    assert settings.refresh_token == "fake-refresh" and "fake" not in repr(settings)
    assert "sender@example.com" not in repr(settings)
    path.write_text(json.dumps({**data, "scopes": [mail.SEND_SCOPE, "https://mail.google.com/"]}))
    with pytest.raises(mail.EmailDeliveryError):
        mail.GmailSettings.from_environment()


def test_cloud_secrets_supported_but_no_mixed_sources(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail_api")
    monkeypatch.setenv("EMAIL_FROM", "sender@example.com")
    for key, value in zip(("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"),
                          ("fake-client", "fake-secret", "fake-refresh")):
        monkeypatch.setenv(key, value)
    first = mail.get_email_transport()
    assert first is mail.get_email_transport()
    monkeypatch.setenv("GMAIL_REFRESH_TOKEN", "fake-rotated")
    assert first is not mail.get_email_transport()
    monkeypatch.setenv("GMAIL_CREDENTIALS_FILE", str(tmp_path / "private.json"))
    with pytest.raises(mail.EmailDeliveryError):
        mail.get_email_transport()


@pytest.mark.parametrize("provider", ["unknown", "gmail_api", ""])
def test_configuration_error_never_falls_back_to_smtp(monkeypatch, provider):
    monkeypatch.setenv("EMAIL_PROVIDER", provider)
    monkeypatch.setattr(mail.smtplib, "SMTP", lambda *a, **k: pytest.fail("No debe haber SMTP"))
    with pytest.raises(mail.EmailDeliveryError):
        mail.send_email(recipient="recipient@example.com", subject="Aviso", body="Texto")


def test_unexpected_exception_is_not_exposed_or_logged(monkeypatch, caplog):
    class Broken:
        def send(self, **kwargs):
            raise RuntimeError("private-secret-token-body")
    monkeypatch.setattr(mail, "get_email_transport", lambda: Broken())
    with pytest.raises(mail.EmailDeliveryError) as error:
        mail.send_email(recipient="recipient@example.com", subject="Aviso", body="Texto")
    assert "private" not in str(error.value) and "private" not in caplog.text
    assert error.value.uncertain and not error.value.retryable


def test_smtp_remains_opt_in_compatible_and_closes_connection(monkeypatch):
    events = []
    class SMTP:
        def __init__(self, *args, **kwargs): events.append("open")
        def __enter__(self): return self
        def __exit__(self, *args): events.append("close")
        def quit(self): events.append("quit")
        def close(self): events.append("close")
        def starttls(self): events.append("tls")
        def login(self, *args): events.append("login")
        def send_message(self, message):
            assert message["Date"] and message["Message-ID"]
            events.append(message["Subject"])
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    mail.send_email(recipient="recipient@example.com", subject="Aviso", body="Texto")
    assert events == ["open", "tls", "login", "Aviso", "quit", "close"]


def smtp_double(monkeypatch, *, failure_at=None, failure=None, quit_error=None, close_error=None, refused=None):
    """Incluye el cierre del context manager para reproducir la regresión previa."""
    events = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            events.append("connect")
            if failure_at == "connect":
                raise failure

        def __enter__(self):
            return self

        def __exit__(self, *args):
            try:
                self.quit()
            finally:
                self.close()

        def starttls(self):
            events.append("tls")
            if failure_at == "tls":
                raise failure

        def login(self, *args):
            events.append("login")
            if failure_at == "login":
                raise failure

        def send_message(self, message):
            events.append("send")
            if failure_at == "send":
                raise failure
            if refused:
                return refused
            events.append("accepted")
            return {}

        def quit(self):
            events.append("quit")
            if quit_error:
                raise quit_error

        def close(self):
            events.append("close")
            if close_error:
                raise close_error

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_STARTTLS", "true")
    monkeypatch.setattr(mail.smtplib, "SMTP", SMTP)
    return events


@pytest.mark.parametrize("error", [mail.smtplib.SMTPResponseException(421, b"private-close"),
    mail.smtplib.SMTPServerDisconnected("private-close"), TimeoutError("private-close")])
def test_smtp_accepted_message_is_not_failed_by_quit(monkeypatch, error, caplog):
    events = smtp_double(monkeypatch, quit_error=error)
    deliver(mail.SmtpEmailTransport())
    assert events == ["connect", "tls", "login", "send", "accepted", "quit", "close"]
    assert "private" not in caplog.text


def test_smtp_accepted_message_is_not_failed_by_socket_cleanup(monkeypatch):
    events = smtp_double(monkeypatch, close_error=OSError("private-close"))
    deliver(mail.SmtpEmailTransport())
    assert events.count("accepted") == events.count("close") == 1


@pytest.mark.parametrize("error", [mail.smtplib.SMTPServerDisconnected("private-send"),
    TimeoutError("private-send"), OSError("private-send")])
def test_smtp_lost_send_response_is_uncertain_and_cleanup_cannot_replace_it(monkeypatch, error, caplog):
    events = smtp_double(monkeypatch, failure_at="send", failure=error,
                         quit_error=mail.smtplib.SMTPResponseException(421, b"private-quit"))
    with pytest.raises(mail.EmailDeliveryError) as caught:
        deliver(mail.SmtpEmailTransport())
    assert caught.value.uncertain and not caught.value.retryable
    assert events.count("send") == events.count("quit") == events.count("close") == 1
    assert "accepted" not in events
    assert "private" not in str(caught.value) and "private" not in caplog.text


@pytest.mark.parametrize("error,retryable", [
    (mail.smtplib.SMTPDataError(450, b"private-data"), True),
    (mail.smtplib.SMTPDataError(550, b"private-data"), False),
    (mail.smtplib.SMTPSenderRefused(450, b"private-sender", "sender@example.com"), True),
    (mail.smtplib.SMTPSenderRefused(550, b"private-sender", "sender@example.com"), False),
    (mail.smtplib.SMTPRecipientsRefused({"recipient@example.com": (450, b"private-recipient")}), True),
    (mail.smtplib.SMTPRecipientsRefused({"recipient@example.com": (550, b"private-recipient")}), False),
])
def test_smtp_explicit_rejection_keeps_its_policy_even_if_quit_fails(monkeypatch, error, retryable):
    events = smtp_double(monkeypatch, failure_at="send", failure=error,
                         quit_error=mail.smtplib.SMTPResponseException(421, b"private-quit"))
    with pytest.raises(mail.EmailDeliveryError) as caught:
        deliver(mail.SmtpEmailTransport())
    assert caught.value.retryable is retryable and not caught.value.uncertain
    assert "private" not in str(caught.value)
    assert events.count("send") == events.count("quit") == events.count("close") == 1


@pytest.mark.parametrize("code,retryable", [(450, True), (550, False)])
def test_smtp_refused_recipient_return_value_is_not_acceptance(monkeypatch, code, retryable):
    events = smtp_double(monkeypatch, refused={"recipient@example.com": (code, b"private-rejection")})
    with pytest.raises(mail.EmailDeliveryError) as caught:
        deliver(mail.SmtpEmailTransport())
    assert caught.value.retryable is retryable and not caught.value.uncertain
    assert "accepted" not in events and events.count("send") == 1
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("phase,error,retryable", [
    ("connect", OSError("private-connect"), True),
    ("tls", mail.smtplib.SMTPNotSupportedError("private-tls"), False),
    ("login", mail.smtplib.SMTPAuthenticationError(435, b"private-auth"), True),
    ("login", mail.smtplib.SMTPAuthenticationError(535, b"private-auth"), False),
])
def test_smtp_failure_before_send_is_not_an_uncertain_delivery(monkeypatch, phase, error, retryable):
    events = smtp_double(monkeypatch, failure_at=phase, failure=error)
    with pytest.raises(mail.EmailDeliveryError) as caught:
        deliver(mail.SmtpEmailTransport())
    assert caught.value.retryable is retryable and not caught.value.uncertain
    assert "private" not in str(caught.value) and "send" not in events
    assert events.count("close") == (0 if phase == "connect" else 1)


def test_gmail_default_http_client_keeps_tls_and_does_not_use_ambient_proxy(monkeypatch):
    calls = []
    monkeypatch.setattr(mail.httpx, "Client", lambda **kwargs: calls.append(kwargs))
    sender = mail.GmailApiEmailTransport(FAKE_SETTINGS)
    sender._client_factory()
    assert calls == [{"timeout": mail.HTTP_TIMEOUT, "follow_redirects": False, "trust_env": False}]
    assert "verify" not in calls[0]  # httpx verifica certificados por defecto.


def test_client_settings_are_shared_when_routes_start_together(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail_api")
    monkeypatch.setattr(mail.GmailSettings, "from_environment", lambda: FAKE_SETTINGS)
    with ThreadPoolExecutor(max_workers=20) as pool:
        senders = list(pool.map(lambda _: mail.get_email_transport(), range(50)))
    assert len({id(sender) for sender in senders}) == 1


@pytest.mark.parametrize("phase", ["token", "send"])
def test_oversized_response_stops_safely(phase):
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if phase == "token" or str(request.url) == mail.SEND_URL:
            return httpx.Response(200, content=b"x" * (mail.MAX_RESPONSE_BYTES + 1))
        return httpx.Response(200, json=TOKEN)
    with pytest.raises(mail.EmailDeliveryError) as error:
        deliver(transport(handler))
    assert not error.value.retryable
    assert error.value.uncertain is (phase == "send")
    assert len(calls) == (1 if phase == "token" else 2)


def test_expired_budget_after_authorization_does_not_start_send():
    now, calls = [0.0], []
    def handler(request):
        calls.append(str(request.url))
        now[0] = mail.DELIVERY_BUDGET + 1
        return httpx.Response(200, json=TOKEN)
    with pytest.raises(mail.EmailDeliveryError):
        deliver(transport(handler, clock=lambda: now[0]))
    assert calls == [mail.TOKEN_URL]
