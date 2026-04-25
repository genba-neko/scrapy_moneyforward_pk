"""SensitiveDataFilter: redaction of URL queries / cookies / auth headers."""

from __future__ import annotations

import logging

from moneyforward_pk.utils.log_filter import (
    SensitiveDataFilter,
    attach_sensitive_filter,
)


def _make_record(msg: str, args: object = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,  # type: ignore[arg-type]
        exc_info=None,
    )


def _apply(record: logging.LogRecord) -> str:
    SensitiveDataFilter().filter(record)
    return record.getMessage()


def test_filter_redacts_auth_query_param():
    record = _make_record("GET https://api.example.com/x?auth=secret123&id=4")
    rendered = _apply(record)
    assert "secret123" not in rendered
    assert "[REDACTED]" in rendered
    # Non-sensitive query params must survive.
    assert "id=4" in rendered


def test_filter_redacts_token_query_param():
    record = _make_record("GET https://api.example.com/x?token=abc.def.ghi")
    rendered = _apply(record)
    assert "abc.def.ghi" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_set_cookie_header():
    record = _make_record("Set-Cookie: session=opaque; Path=/")
    rendered = _apply(record)
    assert "opaque" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_cookie_header():
    record = _make_record("Cookie: SID=opaque-value")
    rendered = _apply(record)
    assert "opaque-value" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_authorization_header():
    record = _make_record("Authorization: Bearer eyJhbGciOi.JIUzI.signature")
    rendered = _apply(record)
    assert "eyJhbGciOi" not in rendered
    assert "signature" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_password_kv_in_message():
    record = _make_record("login attempt password=hunter2 user=admin")
    rendered = _apply(record)
    assert "hunter2" not in rendered
    assert "[REDACTED]" in rendered
    # Other tokens preserved.
    assert "user=admin" in rendered


def test_filter_redacts_inside_format_args():
    record = _make_record(
        "%s %s",
        ("https://x/y?token=mysecret", "Authorization: Bearer xyz"),
    )
    rendered = _apply(record)
    assert "mysecret" not in rendered
    assert "Bearer xyz" not in rendered
    assert rendered.count("[REDACTED]") >= 2


def test_filter_handles_dict_args():
    # logger.info("%(url)s", {"url": "..."}) — LogRecord constructor unwraps
    # the 1-tuple-of-mapping back to the mapping itself; record.args is the
    # bare dict by the time the filter runs.
    record = _make_record("%(url)s", ({"url": "https://x/y?auth=abc"},))
    SensitiveDataFilter().filter(record)
    rendered = record.getMessage()
    assert "abc" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_passes_through_safe_messages():
    record = _make_record("plain log line with no secrets")
    rendered = _apply(record)
    assert rendered == "plain log line with no secrets"


def test_attach_sensitive_filter_is_idempotent():
    logger = logging.getLogger("test_attach_idem")
    logger.filters.clear()
    attach_sensitive_filter(logger)
    attach_sensitive_filter(logger)
    matches = [f for f in logger.filters if isinstance(f, SensitiveDataFilter)]
    assert len(matches) == 1
    logger.filters.clear()


def test_filter_returns_true_to_keep_record():
    """The filter must always allow the record through (no dropping)."""
    record = _make_record("anything")
    assert SensitiveDataFilter().filter(record) is True


def test_filter_redacts_session_query_param():
    record = _make_record("GET https://api.example.com/x?session=opaque-sid&id=4")
    rendered = _apply(record)
    assert "opaque-sid" not in rendered
    assert "[REDACTED]" in rendered
    assert "id=4" in rendered


def test_filter_redacts_refresh_token_query_param():
    record = _make_record("GET https://api.example.com/x?refresh_token=rt-abc-123")
    rendered = _apply(record)
    assert "rt-abc-123" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_aws_signed_url_params():
    """AWS-SigV4 query params often appear in S3 presigned URL logs."""
    record = _make_record(
        "PUT https://x.s3.amazonaws.com/k?X-Amz-Signature=deadbeef&X-Amz-Credential=AKIA"
    )
    rendered = _apply(record)
    assert "deadbeef" not in rendered
    assert "AKIA" not in rendered
    assert rendered.count("[REDACTED]") >= 2


def test_filter_redacts_proxy_authorization_header():
    record = _make_record("Proxy-Authorization: Basic dXNlcjpwYXNz")
    rendered = _apply(record)
    assert "dXNlcjpwYXNz" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_x_api_key_header():
    record = _make_record("X-Api-Key: mykey-abc-123")
    rendered = _apply(record)
    assert "mykey-abc-123" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_csrf_token_header():
    record = _make_record("X-CSRF-Token: token-xyz-789")
    rendered = _apply(record)
    assert "token-xyz-789" not in rendered
    assert "[REDACTED]" in rendered


def test_filter_redacts_json_password_value():
    record = _make_record('{"username":"u","password":"hunter2","other":"keep"}')
    rendered = _apply(record)
    assert "hunter2" not in rendered
    assert "[REDACTED]" in rendered
    assert "keep" in rendered


def test_filter_redacts_json_token_value():
    record = _make_record('{"access_token":"jwt.payload.sig","kind":"Bearer"}')
    rendered = _apply(record)
    assert "jwt.payload.sig" not in rendered
    assert "[REDACTED]" in rendered
    # Non-sensitive sibling keys preserved.
    assert "Bearer" in rendered


def test_filter_redacts_otp_query_param():
    record = _make_record("POST https://x/verify?otp=123456&user=alice")
    rendered = _apply(record)
    assert "123456" not in rendered
    assert "[REDACTED]" in rendered
    assert "user=alice" in rendered


def test_filter_redacts_secret_kv():
    record = _make_record("client_secret=abc-very-secret-xyz appended")
    rendered = _apply(record)
    assert "abc-very-secret-xyz" not in rendered
    assert "[REDACTED]" in rendered
