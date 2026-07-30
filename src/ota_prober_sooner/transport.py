"""Minimal HTTP transport matching the original CheckinService request."""

from __future__ import annotations

import http.client
import json
from typing import Any, Mapping
from urllib.parse import urlencode, urlsplit


CONTENT_TYPE = "org/x-json; charset=UTF-8"
CONTENT_TYPE_29386 = "application/x-www-form-urlencoded"
FORM_CHARSET_29386 = "iso-8859-1"
MAX_RESPONSE_BYTES = 1024 * 1024


class TransportError(RuntimeError):
    """Raised for an HTTP, network, or response-decoding failure."""


def post_checkin(
    url: str,
    request: Mapping[str, Any],
    *,
    timeout: float = 30.0,
) -> tuple[dict[str, Any], bytes]:
    """POST a check-in and return its decoded JSON object and request bytes."""

    body = json.dumps(request, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return _post(
        url,
        body,
        content_type=CONTENT_TYPE,
        accept="org/x-json, application/json",
        timeout=timeout,
    )


def post_checkin_29386(
    url: str,
    request: Mapping[str, Any],
    *,
    timeout: float = 30.0,
) -> tuple[dict[str, Any], bytes]:
    """POST build 29386's form-wrapped JSON payload."""

    payload = json.dumps(request, separators=(",", ":"), ensure_ascii=False)
    # Commons HttpClient 3 used ISO-8859-1 as its default form charset. Its
    # encoder replaced characters outside that repertoire, which matters for
    # the Chinese weekday/month characters in this build's ro.build.date.
    body = urlencode(
        {"payload": payload},
        encoding=FORM_CHARSET_29386,
        errors="replace",
    ).encode("ascii")
    print(body)
    return _post(
        url,
        body,
        content_type=CONTENT_TYPE_29386,
        accept="application/json",
        timeout=timeout,
    )


def _post(
    url: str,
    body: bytes,
    *,
    content_type: str,
    accept: str,
    timeout: float,
) -> tuple[dict[str, Any], bytes]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise TransportError("check-in URL must use http or https")
    if not parsed.hostname:
        raise TransportError("check-in URL must contain a host")
    if parsed.username is not None or parsed.password is not None:
        raise TransportError("check-in URL must not contain credentials")
    if parsed.fragment:
        raise TransportError("check-in URL must not contain a fragment")
    if timeout <= 0:
        raise TransportError("timeout must be greater than zero")

    connection_class = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_class(parsed.hostname, parsed.port, timeout=timeout)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"

    try:
        connection.request(
            "POST",
            target,
            body=body,
            headers={
                "Content-Type": content_type,
                "Accept": accept,
            },
        )
        response = connection.getresponse()
        response_body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise TransportError(
                f"check-in response exceeds {MAX_RESPONSE_BYTES} bytes"
            )
        if response.status != 200:
            reason = response.reason or "unknown status"

            raise TransportError(f"check-in rejected: HTTP {response.status} {reason}")
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TransportError(f"check-in returned invalid UTF-8 JSON: {error}") from error
        if not isinstance(decoded, dict):
            raise TransportError("check-in response must be a JSON object")
        return decoded, body
    except (OSError, http.client.HTTPException) as error:
        raise TransportError(f"check-in request failed: {error}") from error
    finally:
        connection.close()
